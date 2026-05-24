from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
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
    resolve_knowledge_db_path,
    source_vetting,
    stable_hash,
    write_json,
)
from knowledge_db import actor_context_pack, connect, manifest, record_turn_memory, seed_database


ACTOR_ROLES = ["Intel", "Blue", "Red", "White"]
GEMINI_LAUNCH_MODES = {"auto", "terminal_bridge", "popen_headless", "pty_interactive", "mcp"}
V45_CORE_ACTORS = {
    "Blue": ["US", "IL", "SA", "AE"],
    "Red": ["IR", "HOUTHIS", "HEZBOLLAH"],
}
PROMPT_FILES = {
    "Blue": "blue_actor.md",
    "Red": "red_actor.md",
    "White": "white_actor.md",
    "Intel": "intel_fusion.md",
}


def _skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_prompt(actor_id: str) -> str:
    prompt_file = PROMPT_FILES.get(actor_id)
    if not prompt_file:
        if "red" in actor_id.lower() or "coercive" in actor_id.lower():
            prompt_file = "red_actor.md"
        elif "white" in actor_id.lower() or "control" in actor_id.lower():
            prompt_file = "white_actor.md"
        elif "intel" in actor_id.lower() or "fusion" in actor_id.lower():
            prompt_file = "intel_fusion.md"
        else:
            prompt_file = "blue_actor.md"
    path = _skill_dir() / "assets" / "prompts" / prompt_file
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
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    decoder = json.JSONDecoder()
    for start in [match.start() for match in re.finditer(r"\{", text)]:
        try:
            payload, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("Gemini actor response did not contain a JSON object.")


def _actor_role(actor_id: str, context_pack: dict[str, Any]) -> str:
    if actor_id in {"Intel", "White"}:
        return actor_id
    return str(context_pack.get("scenario_role") or actor_id)


def _mock_actor_response(actor_id: str, context_pack: dict[str, Any], state: dict[str, float], turn_id: int, seed: int) -> dict[str, Any]:
    rng = make_rng(seed, turn_id, f"gemini-mock:{actor_id}")
    top_dimensions = sorted(state, key=lambda key: float(state.get(key, 0.0)), reverse=True)[:3]
    role = _actor_role(actor_id, context_pack)
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
    if role in {"Blue", "Red", "Neutral", "Non-state"}:
        direction = 1.0 if role in {"Blue", "Neutral"} else -1.0
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
            action = "stabilize" if role in {"Blue", "Neutral"} else "pressure"
            actions.append(
                {
                    "subagent": f"{actor_id}-{concrete_actor_id}-{dimension}",
                    "dimension": dimension,
                    "action": f"{str(concrete_actor_id).lower()}_{dimension.lower()}_{action}",
                    "severity": severity,
                    "confidence": round(0.58 + rng.uniform(0.0, 0.18), 2),
                    "rationale": f"{actor_id} is a concrete {role} actor mapped to {concrete_actor_id}; action uses seeded V4.5 world context.",
                    "expected_delta": delta,
                    "db_refs": [f"pmesii_indicators:{dimension}", f"actor_doctrine:{actor_id}:{dimension}", f"world_actors:{concrete_actor_id}"],
                    "capability_refs": [cap.get("capability_id", f"CAP_UNKNOWN_{dimension}")],
                    "platform_refs": [platform.get("platform_id", f"PLATFORM_UNKNOWN_{dimension}")],
                }
            )
            expected_effect.append({"dimension": dimension, "delta": delta})
        return {
            "actor_id": actor_id,
            "scenario_role": role,
            "turn_id": turn_id,
            "intent": "stabilize_regional_posture" if role in {"Blue", "Neutral"} else "raise_cost_and_pressure",
            "action_bundle": [{"dimension": row["dimension"], "action": row["action"], "severity": row["severity"]} for row in actions],
            "subagent_actions": actions,
            "resource_cost": round(sum(row["severity"] for row in actions) * 3.0, 2),
            "expected_effect": expected_effect,
            "confidence": round(sum(row["confidence"] for row in actions) / max(1, len(actions)), 2),
            "constraints_considered": ["C_PUBLIC_ONLY", "C_STRATEGIC_LEVEL", "C_JSON_CONTRACT"],
            "dissent_or_uncertainty": ["效果依賴對手是否把訊號解讀為有限壓力。"],
            "concrete_actor_id": concrete_actor_id,
            "risk_acceptance": round(0.35 + rng.uniform(0.0, 0.45), 2),
            "redlines": [f"{concrete_actor_id} rejects uncontrolled escalation beyond stated political authorization."],
            "coordination_preferences": [f"Coordinate with {', '.join(context_pack.get('alliance_peers', [])[:3]) or 'role peers'} before crossing escalation thresholds."],
            "dissent_from_bloc": [f"{concrete_actor_id} may resist bloc consensus if domestic or infrastructure exposure rises."] if rng.random() > 0.58 else [],
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
    role = _actor_role(actor_id, context_pack or {})
    if role in {"Blue", "Red", "Neutral", "Non-state"}:
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
    role = _actor_role(actor_id, context_pack)
    prompt_key = role if role in PROMPT_FILES else actor_id
    template = _read_prompt(prompt_key)
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


def _resolve_language_server() -> Path:
    user_profile = os.environ.get("USERPROFILE", "C:\\Users\\a0953041880")
    ls_bin = Path(user_profile) / "AppData" / "Local" / "Programs" / "Antigravity" / "resources" / "bin" / "language_server.exe"
    if not ls_bin.exists():
        ls_bin = Path(user_profile) / ".gemini" / "antigravity" / "bin" / "agentapi.bat"
        if not ls_bin.exists():
            raise FileNotFoundError("Could not find language_server.exe or agentapi.bat")
    return ls_bin


def _map_model(gemini_model: str | None) -> str:
    if not gemini_model:
        return "flash"
    lower = gemini_model.lower()
    if "flash_lite" in lower or "flash-lite" in lower:
        return "flash_lite"
    if "pro" in lower:
        return "pro"
    return "flash"


def _run_subagent(prompt: str, model_name: str = "flash", timeout_sec: int = 180) -> str:
    ls_bin = _resolve_language_server()
    cmd = [str(ls_bin), "agentapi", "new-conversation", f"--model={model_name}", prompt]
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    try:
        payload = json.loads(result.stdout)
        convo_id = payload["response"]["newConversation"]["conversationId"]
    except Exception as e:
        raise RuntimeError(f"Failed to start subagent. stdout: {result.stdout}, stderr: {result.stderr}") from e
        
    user_profile = os.environ.get("USERPROFILE", "C:\\Users\\a0953041880")
    transcript_path = Path(user_profile) / ".gemini" / "antigravity" / "brain" / convo_id / ".system_generated" / "logs" / "transcript.jsonl"
    
    start_time = time.time()
    final_response = None
    
    while time.time() - start_time < timeout_sec:
        if not transcript_path.exists():
            time.sleep(1)
            continue
            
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except IOError:
            time.sleep(0.5)
            continue
            
        parsed_steps = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                parsed_steps.append(json.loads(line))
            except Exception:
                pass
                
        if parsed_steps:
            last_step = parsed_steps[-1]
            if last_step.get("type") == "PLANNER_RESPONSE":
                content = last_step.get("content")
                tool_calls = last_step.get("tool_calls")
                if content and not tool_calls:
                    final_response = content
                    break
                    
        time.sleep(1.5)
        
    if final_response is None:
        raise TimeoutError(f"Subagent did not produce a final response within {timeout_sec} seconds")
        
    return final_response


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
    timeout_sec: int = 180,
    launch_mode: str = "auto",
    gemini_model: str | None = None,
) -> dict[str, Any]:
    target = Path(call_dir)
    target.mkdir(parents=True, exist_ok=True)
    prompt_path = target / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    validation: dict[str, Any] = {
        "actor_id": actor_id,
        "mock": mock,
        "parser": "json_object",
        "requested_launch_mode": launch_mode,
        "gemini_model": gemini_model,
        "auth_mode": "native-subagent",
        "node_options": "native",
    }
    if mock:
        parsed = _mock_actor_response(actor_id, context_pack, state, turn_id, seed)
        raw = json.dumps(parsed, ensure_ascii=False, indent=2)
    else:
        mapped_model = _map_model(gemini_model)
        started = time.monotonic()
        try:
            raw = _run_subagent(prompt, mapped_model, timeout_sec)
            elapsed = round(time.monotonic() - started, 3)
            parsed = _extract_json(raw)
            validation["mock"] = False
            validation["live_ok"] = True
            validation["launch_mode"] = "native-subagent"
            validation["launch_method"] = "language_server_agentapi"
            validation["returncode"] = 0
            validation["elapsed_sec"] = elapsed
        except Exception as exc:
            parsed = _mock_actor_response(actor_id, context_pack, state, turn_id, seed)
            raw = str(exc)
            validation["mock"] = True
            validation["live_ok"] = False
            validation["fallback"] = "mock_after_subagent_failure"
            validation["fallback_kind"] = "subagent_failure"
            validation["fallback_reason"] = raw[:1000]
            
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


def _scenario_role_rows(db_path: str | Path) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT role, actor_id FROM actor_bloc_roles WHERE scenario_id='current' ORDER BY role, actor_id"
            ).fetchall()
        ]
    finally:
        conn.close()


def build_concrete_actor_plan(db_path: str | Path, actor_scope: str = "core") -> list[dict[str, str]]:
    by_role: dict[str, list[str]] = {}
    for row in _scenario_role_rows(db_path):
        by_role.setdefault(str(row["role"]), []).append(str(row["actor_id"]))
    plan: list[dict[str, str]] = []
    if actor_scope == "core":
        for role, actor_ids in V45_CORE_ACTORS.items():
            available = by_role.get(role, [])
            for actor_id in actor_ids:
                if actor_id in available:
                    plan.append({"actor_id": actor_id, "scenario_role": role, "call_id": f"{actor_id}_{role}"})
        if len(plan) == sum(len(actor_ids) for actor_ids in V45_CORE_ACTORS.values()):
            return plan
        plan = []
    roles = ["Blue", "Red"] if actor_scope == "expanded" else ["Blue", "Red", "Neutral", "Non-state"]
    for role in roles:
        for actor_id in by_role.get(role, []):
            plan.append({"actor_id": actor_id, "scenario_role": role, "call_id": f"{actor_id}_{role}"})
    return plan


def synthesize_multi_actor(actor_payloads: dict[str, dict[str, Any]], actor_plan: list[dict[str, str]]) -> dict[str, Any]:
    plan_by_call = {row["call_id"]: row for row in actor_plan}
    bloc_actions: dict[str, list[dict[str, Any]]] = {"Blue": [], "Red": [], "Neutral": [], "Non-state": []}
    summaries = []
    for call_id, envelope in actor_payloads.items():
        parsed = envelope.get("parsed", {})
        plan = plan_by_call.get(call_id, {})
        role = str(parsed.get("scenario_role") or plan.get("scenario_role") or "Unknown")
        concrete_actor_id = str(parsed.get("concrete_actor_id") or plan.get("actor_id") or call_id)
        actions = parsed.get("subagent_actions", [])
        if isinstance(actions, list):
            bloc_actions.setdefault(role, []).extend(actions)
        summaries.append(
            {
                "call_id": call_id,
                "actor_id": concrete_actor_id,
                "scenario_role": role,
                "intent": parsed.get("intent", ""),
                "risk_acceptance": parsed.get("risk_acceptance"),
                "dissent_from_bloc": parsed.get("dissent_from_bloc", []),
                "action_count": len(actions) if isinstance(actions, list) else 0,
                "validation": envelope.get("validation", {}),
            }
        )
    return {
        "actor_count": len(actor_payloads),
        "actor_summaries": summaries,
        "bloc_action_counts": {role: len(actions) for role, actions in bloc_actions.items()},
        "bloc_actions": bloc_actions,
    }


def detect_alliance_dissent(synthesis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for summary in synthesis.get("actor_summaries", []):
        dissent = summary.get("dissent_from_bloc") or []
        risk = summary.get("risk_acceptance")
        if dissent or (isinstance(risk, (int, float)) and risk >= 0.72):
            rows.append(
                {
                    "actor_id": summary.get("actor_id"),
                    "scenario_role": summary.get("scenario_role"),
                    "risk_acceptance": risk,
                    "dissent": dissent,
                    "assessment": "Potential intra-bloc friction should be considered before aggregating COA.",
                }
            )
    return rows


def detect_proxy_autonomy_risk(synthesis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for summary in synthesis.get("actor_summaries", []):
        actor_id = str(summary.get("actor_id", ""))
        if actor_id in {"HOUTHIS", "HEZBOLLAH"}:
            risk = float(summary.get("risk_acceptance") or 0.5)
            rows.append(
                {
                    "actor_id": actor_id,
                    "principal_actor": "IR",
                    "risk_score": round(min(0.95, max(0.35, risk + 0.12)), 2),
                    "assessment": "Proxy actor may create escalation faster than principal decision cycle.",
                }
            )
    return rows


def aggregate_bloc_coa(role: str, synthesis: dict[str, Any], actor_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    actions = list(synthesis.get("bloc_actions", {}).get(role, []))
    expected_effect: list[dict[str, Any]] = []
    confidence_values: list[float] = []
    resource_cost = 0.0
    for envelope in actor_payloads.values():
        parsed = envelope.get("parsed", {})
        if parsed.get("scenario_role") != role:
            continue
        for effect in parsed.get("expected_effect", []) if isinstance(parsed.get("expected_effect"), list) else []:
            if isinstance(effect, dict):
                expected_effect.append(effect)
        try:
            confidence_values.append(float(parsed.get("confidence", 0.55)))
            resource_cost += float(parsed.get("resource_cost", 0.0))
        except (TypeError, ValueError):
            pass
    intent = "stabilize_regional_posture" if role == "Blue" else "raise_cost_and_pressure"
    return {
        "actor_id": role.lower(),
        "intent": f"v45_concrete_{intent}",
        "action_bundle": [{"dimension": row.get("dimension"), "action": row.get("action"), "severity": row.get("severity", 0.5)} for row in actions],
        "subagent_actions": actions,
        "resource_cost": round(resource_cost, 2),
        "expected_effect": expected_effect,
        "confidence": round(sum(confidence_values) / max(1, len(confidence_values)), 2),
        "engine": "gemini_actor_v45_concrete",
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
    actor_execution: str = "v45_concrete",
    actor_scope: str = "core",
    gemini_timeout: int = 180,
    gemini_launch_mode: str = "auto",
    gemini_model: str | None = None,
) -> TurnResult:
    working_dir = Path(mission.get("working_dir", "."))
    replay_dir = working_dir / "replay_bundle"
    run_id = str(mission.get("run_id", stable_hash({"topic": mission.get("topic"), "seed": seed})[:12]))
    knowledge_db_path = resolve_knowledge_db_path(mission.get("knowledge_db_path"))
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
    support_responses: dict[str, dict[str, Any]] = {}
    actor_plan: list[dict[str, str]] = []
    multi_actor_synthesis: dict[str, Any] = {}
    alliance_dissent: list[dict[str, Any]] = []
    proxy_autonomy_risk: list[dict[str, Any]] = []
    call_root = replay_dir / f"turn_{turn_id:02d}_actor_calls"
    legacy_call_root = replay_dir / f"turn_{turn_id:02d}_gemini_calls"
    decision_questions = [str(row) for row in mission.get("decision_questions", [])]
    if actor_execution == "v45_concrete":
        actor_plan = build_concrete_actor_plan(knowledge_db_path, actor_scope)
        for row in actor_plan:
            call_id = row["call_id"]
            context_pack = actor_context_pack(
                knowledge_db_path,
                row["actor_id"],
                turn_id,
                state,
                decision_questions=decision_questions,
                scenario_role=row["scenario_role"],
            )
            context_packs[call_id] = context_pack
            prompt = render_actor_prompt(call_id, context_pack, base_turn_packet, scenario)
            actor_responses[call_id] = call_gemini_actor(
                call_id,
                prompt,
                call_root / call_id.lower(),
                mock=mock_gemini,
                context_pack=context_pack,
                state=state,
                turn_id=turn_id,
                seed=seed,
                timeout_sec=gemini_timeout,
                launch_mode=gemini_launch_mode,
                gemini_model=gemini_model,
            )
        for support_id in ["Intel", "White"]:
            context_pack = actor_context_pack(
                knowledge_db_path,
                support_id,
                turn_id,
                state,
                decision_questions=decision_questions,
            )
            context_packs[support_id] = context_pack
            prompt = render_actor_prompt(support_id, context_pack, base_turn_packet, scenario)
            support_responses[support_id] = call_gemini_actor(
                support_id,
                prompt,
                call_root / f"{support_id.lower()}_support",
                mock=mock_gemini,
                context_pack=context_pack,
                state=state,
                turn_id=turn_id,
                seed=seed,
                timeout_sec=gemini_timeout,
                launch_mode=gemini_launch_mode,
                gemini_model=gemini_model,
            )
        multi_actor_synthesis = synthesize_multi_actor(actor_responses, actor_plan)
        alliance_dissent = detect_alliance_dissent(multi_actor_synthesis)
        proxy_autonomy_risk = detect_proxy_autonomy_risk(multi_actor_synthesis)
    else:
        for actor_id in ACTOR_ROLES:
            context_pack = actor_context_pack(
                knowledge_db_path,
                actor_id,
                turn_id,
                state,
                decision_questions=decision_questions,
            )
            context_packs[actor_id] = context_pack
            prompt = render_actor_prompt(actor_id, context_pack, base_turn_packet, scenario)
            actor_responses[actor_id] = call_gemini_actor(
                actor_id,
                prompt,
                legacy_call_root / actor_id.lower(),
                mock=mock_gemini,
                context_pack=context_pack,
                state=state,
                turn_id=turn_id,
                seed=seed,
                timeout_sec=gemini_timeout,
                launch_mode=gemini_launch_mode,
                gemini_model=gemini_model,
            )
        support_responses = {key: actor_responses[key] for key in ["Intel", "White"]}

    write_json(replay_dir / f"turn_{turn_id:02d}_actor_context_pack.json", context_packs)
    if actor_execution == "v45_concrete":
        write_json(replay_dir / f"turn_{turn_id:02d}_actor_plan.json", actor_plan)
        write_json(replay_dir / f"turn_{turn_id:02d}_multi_actor_synthesis.json", multi_actor_synthesis)
        write_json(replay_dir / f"turn_{turn_id:02d}_alliance_dissent.json", alliance_dissent)
        write_json(replay_dir / f"turn_{turn_id:02d}_proxy_autonomy_risk.json", proxy_autonomy_risk)
    controller_inputs = {**actor_responses, **support_responses}
    controller = controller_decision(controller_inputs, state)
    if actor_execution == "v45_concrete":
        controller["actor_execution"] = actor_execution
        controller["actor_scope"] = actor_scope
        controller["alliance_dissent_count"] = len(alliance_dissent)
        controller["proxy_autonomy_risk_count"] = len(proxy_autonomy_risk)
    write_json(replay_dir / f"turn_{turn_id:02d}_controller_decision.json", controller)
    write_json(replay_dir / f"turn_{turn_id:02d}_violations.json", controller["violations"])

    if actor_execution == "v45_concrete":
        blue_coa = aggregate_bloc_coa("Blue", multi_actor_synthesis, actor_responses)
        red_coa = aggregate_bloc_coa("Red", multi_actor_synthesis, actor_responses)
    else:
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
        database_path=knowledge_db_path,
        commit_ammo_deduction=False,
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
    white_payload = support_responses["White"]["parsed"]
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
        database_path=knowledge_db_path,
        commit_ammo_deduction=controller.get("accepted", True),
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
    expert_review["multi_actor_synthesis"] = multi_actor_synthesis
    expert_review["alliance_dissent"] = alliance_dissent
    expert_review["proxy_autonomy_risk"] = proxy_autonomy_risk
    adjudication = apply_ai_review_to_adjudication(adjudication, expert_review)
    indicators = indicator_from_state(next_state)

    record_turn_memory(knowledge_db_path, run_id, turn_id, "Blue", blue_coa, blue_coa.get("expected_effect", {}), controller["rationale"], controller["violations"])
    record_turn_memory(knowledge_db_path, run_id, turn_id, "Red", red_coa, red_coa.get("expected_effect", {}), controller["rationale"], controller["violations"])
    for call_id, envelope in actor_responses.items():
        parsed = envelope.get("parsed", {})
        record_turn_memory(knowledge_db_path, run_id, turn_id, str(parsed.get("concrete_actor_id") or call_id), parsed, parsed.get("expected_effect", {}), controller["rationale"], controller["violations"])
    record_turn_memory(knowledge_db_path, run_id, turn_id, "White", white_payload, {}, controller["rationale"], controller["violations"])
    write_json(working_dir / "knowledge_db_manifest.json", manifest(knowledge_db_path))

    agent_log = {
        "turn_id": turn_id,
        "engine": "gemini_actor",
        "mock_gemini": mock_gemini,
        "actor_execution": actor_execution,
        "actor_scope": actor_scope,
        "gemini_launch_mode": gemini_launch_mode,
        "gemini_model": gemini_model,
        "gemini_timeout": gemini_timeout,
        "gemini_call_dir": str(call_root.resolve()),
        "actor_context_pack": str((replay_dir / f"turn_{turn_id:02d}_actor_context_pack.json").resolve()),
        "controller_decision": controller,
        "blue_subagents": blue_coa.get("subagent_actions", []),
        "red_subagents": red_coa.get("subagent_actions", []),
        "actor_plan": actor_plan,
        "multi_actor_synthesis": multi_actor_synthesis,
        "support_call_summaries": {
            key: {"validation": value.get("validation", {}), "actor_id": key}
            for key, value in support_responses.items()
        },
        "alliance_dissent": alliance_dissent,
        "proxy_autonomy_risk": proxy_autonomy_risk,
        "intel_fusion": support_responses["Intel"]["parsed"],
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
