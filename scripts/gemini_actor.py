from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from common import (
    TurnResult,
    adjudicate_turn,
    ai_expert_review_cell,
    apply_ai_review_to_adjudication,
    attach_event_metadata_to_evidence,
    build_turn_event_ledger,
    clamp_state,
    collect_intel_bundle,
    compare_events_with_baseline,
    fuse_evidence,
    indicator_from_state,
    make_rng,
    source_vetting,
    stable_hash,
    write_json,
)
from knowledge_db import actor_context_pack, manifest, record_turn_memory, seed_database

ACTOR_ROLES = ["Intel", "Blue", "Red", "White"]
PROMPT_FILES = {
    "Blue": "blue_actor.md",
    "Red": "red_actor.md",
    "White": "white_actor.md",
    "Intel": "intel_fusion.md",
}


def _skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_prompt(actor_id: str) -> str:
    path = _skill_dir() / "assets" / "prompts" / PROMPT_FILES[actor_id]
    return path.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("Gemini actor response did not contain a JSON object.")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Gemini actor response JSON must be an object.")
    return payload


def _mock_actor_response(actor_id: str, context_pack: dict[str, Any], state: dict[str, float], turn_id: int, seed: int) -> dict[str, Any]:
    rng = make_rng(seed, turn_id, f"gemini-mock:{actor_id}")
    top_dimensions = sorted(state, key=lambda key: float(state.get(key, 0.0)), reverse=True)[:3]
    if actor_id == "Intel":
        return {
            "actor_id": "Intel",
            "turn_id": turn_id,
            "assessment": "來源顯示軍事與資訊壓力仍是主要觀察軸，外交降溫訊號不足以單獨翻轉判斷。",
            "claims": [
                {"claim": f"{dimension} pressure requires actor attention", "dimension": dimension, "confidence": 0.68}
                for dimension in top_dimensions
            ],
            "source_ids": [row.get("source_id", row.get("source_name", "SRC_UNKNOWN")) for row in context_pack.get("sources", [])[:3]],
            "uncertainties": ["公開來源可能低估非公開溝通。"],
        }
    if actor_id in {"Blue", "Red"}:
        direction = 1.0 if actor_id == "Blue" else -1.0
        actions = []
        expected_effect = []
        concrete = context_pack.get("concrete_actor_context") or {}
        concrete_actor_id = context_pack.get("concrete_actor_id") or actor_id
        cap_rules = concrete.get("capability_rules") or []
        platforms = concrete.get("military_platforms") or []
        for dimension in top_dimensions:
            cap = cap_rules[len(actions) % len(cap_rules)] if cap_rules else {}
            platform = platforms[len(actions) % len(platforms)] if platforms else {}
            severity = round(max(0.2, min(0.9, 0.42 + abs(float(state[dimension]) - 50.0) / 120.0 + rng.uniform(-0.05, 0.08))), 2)
            delta = round(direction * severity * rng.uniform(0.8, 2.4), 2)
            action = "stabilize" if actor_id == "Blue" else "pressure"
            actions.append(
                {
                    "subagent": f"{actor_id}-{concrete_actor_id}-{dimension}",
                    "dimension": dimension,
                    "action": f"{str(concrete_actor_id).lower()}_{dimension.lower()}_{action}",
                    "severity": severity,
                    "confidence": round(0.58 + rng.uniform(0.0, 0.18), 2),
                    "rationale": f"{actor_id} slot is mapped to {concrete_actor_id}; action uses seeded V4 world context.",
                    "expected_delta": delta,
                    "db_refs": [f"pmesii_indicators:{dimension}", f"actor_doctrine:{actor_id}:{dimension}", f"world_actors:{concrete_actor_id}"],
                    "capability_refs": [cap.get("capability_id", f"CAP_UNKNOWN_{dimension}")],
                    "platform_refs": [platform.get("platform_id", f"PLATFORM_UNKNOWN_{dimension}")],
                }
            )
            expected_effect.append({"dimension": dimension, "delta": delta})
        return {
            "actor_id": actor_id,
            "turn_id": turn_id,
            "intent": "stabilize_regional_posture" if actor_id == "Blue" else "raise_cost_and_pressure",
            "action_bundle": [{"dimension": row["dimension"], "action": row["action"], "severity": row["severity"]} for row in actions],
            "subagent_actions": actions,
            "resource_cost": round(sum(row["severity"] for row in actions) * 3.0, 2),
            "expected_effect": expected_effect,
            "confidence": round(sum(row["confidence"] for row in actions) / max(1, len(actions)), 2),
            "constraints_considered": ["C_PUBLIC_ONLY", "C_STRATEGIC_LEVEL", "C_JSON_CONTRACT"],
            "dissent_or_uncertainty": ["效果依賴對手是否把訊號解讀為有限壓力。"],
            "concrete_actor_id": concrete_actor_id,
        }
    return {
        "actor_id": "White",
        "turn_id": turn_id,
        "assessment": "行動具 PMESII 關聯，但仍需保留來源獨立性與升級外溢的不確定性。",
        "rule_fires": [{"rule_id": "V3_ACTOR_GROUNDED", "message": "Actor output cites database context and PMESII dimensions."}],
        "dissent": ["White requires one explicit uncertainty: public-source evidence may lag actor intent."],
        "confidence_adjustment": -0.03,
        "violations": [],
    }


def validate_actor_response(actor_id: str, payload: dict[str, Any], context_pack: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if str(payload.get("actor_id", "")).lower() != actor_id.lower():
        violations.append({"rule_id": "ACTOR_ID_MISMATCH", "severity": "high", "message": f"Expected {actor_id} actor_id."})
    if actor_id in {"Blue", "Red"}:
        actions = payload.get("subagent_actions", [])
        if not isinstance(actions, list) or not actions:
            violations.append({"rule_id": "ACTOR_ACTIONS_REQUIRED", "severity": "high", "message": "Actor COA requires subagent_actions."})
        for action in actions if isinstance(actions, list) else []:
            if action.get("dimension") not in {"P", "M", "E", "S", "I", "Infra"}:
                violations.append({"rule_id": "PMESII_DIMENSION_REQUIRED", "severity": "high", "message": "Every actor action must bind to a PMESII dimension."})
            if not action.get("db_refs"):
                violations.append({"rule_id": "DB_REF_REQUIRED", "severity": "medium", "message": "Actor action should cite database context."})
            if context_pack:
                concrete = context_pack.get("concrete_actor_context") or {}
                available_caps = {
                    str(row.get("capability_id"))
                    for row in concrete.get("capability_rules", [])
                    if row.get("capability_id")
                }
                available_platforms = {
                    str(row.get("platform_id"))
                    for row in concrete.get("military_platforms", [])
                    if row.get("platform_id")
                }
                cap_refs = [str(row) for row in action.get("capability_refs", [])]
                platform_refs = [str(row) for row in action.get("platform_refs", [])]
                if available_caps and not any(ref in available_caps for ref in cap_refs):
                    violations.append({"rule_id": "CAPABILITY_NOT_SEEDED", "severity": "high", "message": "Actor action references no capability available to the concrete actor."})
                if available_platforms and platform_refs and not any(ref in available_platforms for ref in platform_refs):
                    violations.append({"rule_id": "PLATFORM_NOT_SEEDED", "severity": "high", "message": "Actor action references platform outside concrete actor inventory."})
        if not payload.get("constraints_considered"):
            violations.append({"rule_id": "CONSTRAINTS_REQUIRED", "severity": "medium", "message": "Actor must state constraints considered."})
    if actor_id == "White":
        if not payload.get("dissent"):
            violations.append({"rule_id": "WHITE_DISSENT_REQUIRED", "severity": "medium", "message": "White actor must provide dissent or uncertainty."})
    if actor_id == "Intel":
        if not payload.get("claims") and not payload.get("assessment"):
            violations.append({"rule_id": "INTEL_DIGEST_REQUIRED", "severity": "medium", "message": "Intel actor must provide claims or assessment."})
    return violations


def render_actor_prompt(actor_id: str, context_pack: dict[str, Any], turn_packet: dict[str, Any], scenario: dict[str, Any]) -> str:
    template = _read_prompt(actor_id)
    payload = {
        "actor_id": actor_id,
        "context_pack": context_pack,
        "turn_packet": turn_packet,
        "scenario_constraints": {
            "baseline": scenario.get("baseline", ""),
            "termination_conditions": scenario.get("termination_conditions", []),
            "assumption_tree": scenario.get("assumption_tree", []),
        },
    }
    return template.replace("{{payload_json}}", json.dumps(payload, ensure_ascii=False, indent=2))


def call_gemini_actor(
    actor_id: str,
    prompt: str,
    call_dir: str | Path,
    *,
    mock: bool,
    context_pack: dict[str, Any],
    state: dict[str, float],
    turn_id: int,
    seed: int,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    target = Path(call_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "prompt.md").write_text(prompt, encoding="utf-8")
    validation: dict[str, Any] = {"actor_id": actor_id, "mock": mock, "parser": "json_object"}
    if mock:
        parsed = _mock_actor_response(actor_id, context_pack, state, turn_id, seed)
        raw = json.dumps(parsed, ensure_ascii=False, indent=2)
    else:
        command = ["gemini", "-p", prompt]
        proc = subprocess.run(command, text=True, encoding="utf-8", capture_output=True, timeout=timeout_sec)
        raw = proc.stdout if proc.returncode == 0 else proc.stdout + "\n" + proc.stderr
        validation["returncode"] = proc.returncode
        if proc.returncode != 0:
            parsed = _mock_actor_response(actor_id, context_pack, state, turn_id, seed)
            validation["fallback"] = "mock_after_gemini_cli_failure"
        else:
            parsed = _extract_json(raw)
    violations = validate_actor_response(actor_id, parsed, context_pack)
    validation["violations"] = violations
    (target / "raw_response.txt").write_text(raw, encoding="utf-8")
    write_json(target / "parsed.json", parsed)
    write_json(target / "validation.json", validation)
    return {"parsed": parsed, "raw": raw, "validation": validation}


def _coa_from_actor(actor_id: str, response: dict[str, Any]) -> dict[str, Any]:
    actions = response.get("subagent_actions", [])
    if not isinstance(actions, list):
        actions = []
    return {
        "actor_id": actor_id.lower(),
        "intent": str(response.get("intent", "stabilize_regional_posture" if actor_id == "Blue" else "raise_cost_and_pressure")),
        "action_bundle": response.get("action_bundle", []),
        "subagent_actions": actions,
        "resource_cost": float(response.get("resource_cost", 0.0)),
        "expected_effect": response.get("expected_effect", []),
        "confidence": float(response.get("confidence", 0.55)),
        "engine": "gemini_actor",
    }


def controller_decision(actor_responses: dict[str, dict[str, Any]], state: dict[str, float]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    for actor_id, row in actor_responses.items():
        for violation in row.get("validation", {}).get("violations", []):
            violations.append({"actor_id": actor_id, **violation})
    blocked = any(row.get("severity") == "high" for row in violations)
    rationale = "Controller accepted Gemini actor outputs with PMESII and database grounding."
    if blocked:
        rationale = "Controller blocked direct state transition because high-severity actor contract violations were present."
    return {
        "controller_role": "Codex observer/controller/judge",
        "accepted": not blocked,
        "rationale": rationale,
        "violations": violations,
        "state_transition_policy": "use validated actor COA plus local adjudication; freeze state on high violation",
        "state_hash": stable_hash(state),
    }


def execute_gemini_actor_turn(
    mission: dict[str, Any],
    scenario: dict[str, Any],
    actor_config: dict[str, Any],
    state: dict[str, float],
    turn_id: int,
    seed: int,
    collection_plan: dict[str, Any] | None = None,
    existing_turn_packet: dict[str, Any] | None = None,
    *,
    mock_gemini: bool = False,
) -> TurnResult:
    working_dir = Path(mission.get("working_dir", "."))
    replay_dir = working_dir / "replay_bundle"
    run_id = str(mission.get("run_id", stable_hash({"topic": mission.get("topic"), "seed": seed})[:12]))
    knowledge_db_path = Path(mission.get("knowledge_db_path") or working_dir / "wargame_knowledge.sqlite")
    manifest_payload = seed_database(
        knowledge_db_path,
        mission=mission,
        scenario=scenario,
        actor_config=actor_config,
        collection_plan=collection_plan or {},
        references_dir=_skill_dir() / "references",
    )
    write_json(working_dir / "knowledge_db_manifest.json", manifest_payload)

    prior_hash = stable_hash(state)
    if existing_turn_packet and existing_turn_packet.get("captured_evidence"):
        raw_evidence = list(existing_turn_packet.get("captured_evidence", []))
        source_capture_manifest = list(existing_turn_packet.get("source_capture_manifest", []))
        claim_registry = list(existing_turn_packet.get("claim_registry", []))
        evidence_clusters = list(existing_turn_packet.get("evidence_clusters", []))
    else:
        intel_bundle = collect_intel_bundle(mission, scenario, turn_id, collection_plan, seed)
        raw_evidence = intel_bundle["evidence"]
        source_capture_manifest = intel_bundle["source_capture_manifest"]
        claim_registry = intel_bundle["claim_registry"]
        evidence_clusters = intel_bundle["evidence_clusters"]
    vetted_evidence = source_vetting(raw_evidence)
    fused_evidence = fuse_evidence(vetted_evidence)

    base_turn_packet = existing_turn_packet or {
        "turn_id": turn_id,
        "prior_state_hash": prior_hash,
        "intel_digest": [{"evidence_id": row["evidence_id"], "claim": row["claim"]} for row in fused_evidence[:10]],
        "constraints": ["public-source-only", "strategic-level", "gemini-actor-json-contract", "codex-controller-review"],
        "tasking": {
            "intel": "compress evidence and expose source gaps",
            "blue": "produce PMESII-aligned stabilization COA as JSON",
            "red": "produce PMESII-aligned coercive COA as JSON",
            "white": "review actor outputs, dissent, and rule violations as JSON",
        },
        "captured_evidence": fused_evidence,
        "source_capture_manifest": source_capture_manifest,
        "claim_registry": claim_registry,
        "evidence_clusters": evidence_clusters,
    }

    actor_responses: dict[str, dict[str, Any]] = {}
    context_packs: dict[str, dict[str, Any]] = {}
    call_root = replay_dir / f"turn_{turn_id:02d}_gemini_calls"
    for actor_id in ACTOR_ROLES:
        context_pack = actor_context_pack(
            knowledge_db_path,
            actor_id,
            turn_id,
            state,
            decision_questions=[str(row) for row in mission.get("decision_questions", [])],
        )
        context_packs[actor_id] = context_pack
        prompt = render_actor_prompt(actor_id, context_pack, base_turn_packet, scenario)
        actor_responses[actor_id] = call_gemini_actor(
            actor_id,
            prompt,
            call_root / actor_id.lower(),
            mock=mock_gemini,
            context_pack=context_pack,
            state=state,
            turn_id=turn_id,
            seed=seed,
        )

    write_json(replay_dir / f"turn_{turn_id:02d}_actor_context_pack.json", context_packs)
    controller = controller_decision(actor_responses, state)
    write_json(replay_dir / f"turn_{turn_id:02d}_controller_decision.json", controller)
    write_json(replay_dir / f"turn_{turn_id:02d}_violations.json", controller["violations"])

    blue_coa = _coa_from_actor("Blue", actor_responses["Blue"]["parsed"])
    red_coa = _coa_from_actor("Red", actor_responses["Red"]["parsed"])
    if not controller["accepted"]:
        blue_coa["expected_effect"] = []
        red_coa["expected_effect"] = []
        blue_coa["subagent_actions"] = []
        red_coa["subagent_actions"] = []

    provisional_event_ledger = build_turn_event_ledger(
        mission=mission,
        scenario=scenario,
        turn_id=turn_id,
        state_before=state,
        state_after=state,
        blue_coa=blue_coa,
        red_coa=red_coa,
        evidence_rows=fused_evidence,
        seed=seed,
    )
    fused_evidence = attach_event_metadata_to_evidence(fused_evidence, provisional_event_ledger)
    adjudication, next_state = adjudicate_turn(
        mission,
        base_turn_packet,
        state,
        blue_coa,
        red_coa,
        fused_evidence,
        seed,
        event_ledger=provisional_event_ledger,
        baseline_deviation_score=0.0,
    )
    if not controller["accepted"]:
        next_state = clamp_state(state)
        adjudication["override_note"] = "State frozen by V3 controller because actor contract violations were present."
    white_payload = actor_responses["White"]["parsed"]
    if white_payload.get("rule_fires"):
        adjudication.setdefault("rule_fires", []).extend(white_payload.get("rule_fires", []))
    if white_payload.get("dissent"):
        adjudication["expert_dissent"] = [{"expert_role": "Gemini White", "dissent_reason": str(row)} for row in white_payload.get("dissent", [])]

    event_ledger = build_turn_event_ledger(
        mission=mission,
        scenario=scenario,
        turn_id=turn_id,
        state_before=state,
        state_after=next_state,
        blue_coa=blue_coa,
        red_coa=red_coa,
        evidence_rows=fused_evidence,
        seed=seed,
    )
    fused_evidence = attach_event_metadata_to_evidence(fused_evidence, event_ledger)
    baseline_db_path = mission.get("baseline_db_path") or str(working_dir / "actor_baseline_db.sqlite")
    from common import ensure_actor_baseline_db

    ensure_actor_baseline_db(baseline_db_path, mission, collection_plan)
    baseline_deviations, baseline_deviation_score = compare_events_with_baseline(
        db_path=baseline_db_path,
        turn_id=turn_id,
        event_ledger=event_ledger,
        state_after=next_state,
    )
    adjudication["baseline_deviation_score"] = round(baseline_deviation_score, 3)
    adjudication["event_ids"] = [str(row.get("event_id", "")) for row in event_ledger[:12]]
    expert_review = ai_expert_review_cell(mission, base_turn_packet, fused_evidence, adjudication, event_ledger, seed)
    expert_review["gemini_white_review"] = white_payload
    expert_review["controller_decision"] = controller
    adjudication = apply_ai_review_to_adjudication(adjudication, expert_review)
    indicators = indicator_from_state(next_state)

    record_turn_memory(knowledge_db_path, run_id, turn_id, "Blue", blue_coa, blue_coa.get("expected_effect", {}), controller["rationale"], controller["violations"])
    record_turn_memory(knowledge_db_path, run_id, turn_id, "Red", red_coa, red_coa.get("expected_effect", {}), controller["rationale"], controller["violations"])
    record_turn_memory(knowledge_db_path, run_id, turn_id, "White", white_payload, {}, controller["rationale"], controller["violations"])
    write_json(working_dir / "knowledge_db_manifest.json", manifest(knowledge_db_path))

    agent_log = {
        "turn_id": turn_id,
        "engine": "gemini_actor",
        "mock_gemini": mock_gemini,
        "gemini_call_dir": str(call_root.resolve()),
        "actor_context_pack": str((replay_dir / f"turn_{turn_id:02d}_actor_context_pack.json").resolve()),
        "controller_decision": controller,
        "blue_subagents": blue_coa.get("subagent_actions", []),
        "red_subagents": red_coa.get("subagent_actions", []),
        "intel_fusion": actor_responses["Intel"]["parsed"],
        "white_review": white_payload,
        "white_rule_fires": adjudication.get("rule_fires", []),
        "white_decision_rationale": adjudication.get("decision_rationale", []),
        "counterdeception_findings": adjudication.get("counterdeception_findings", []),
        "expert_review": expert_review,
        "event_ledger": event_ledger,
        "baseline_deviation_score": round(baseline_deviation_score, 3),
        "knowledge_db_path": str(knowledge_db_path.resolve()),
    }
    return TurnResult(
        turn_id=turn_id,
        turn_packet=base_turn_packet,
        blue_coa=blue_coa,
        red_coa=red_coa,
        adjudication=adjudication,
        state_before=state,
        state_after=next_state,
        indicators=indicators,
        evidence=fused_evidence,
        source_capture_manifest=source_capture_manifest,
        claim_registry=claim_registry,
        evidence_clusters=evidence_clusters,
        event_ledger=event_ledger,
        baseline_deviations=baseline_deviations,
        baseline_deviation_score=baseline_deviation_score,
        expert_review=expert_review,
        adjudication_dissent=expert_review.get("structured_dissent", []),
        agent_log=agent_log,
    )
