from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import (
    _ach_summary_from_detail,
    build_ach_matrix,
    build_dashboard,
    build_report_metrics,
    collect_quality_gate_warnings,
    derive_key_judgments,
    ensure_actor_baseline_db,
    evaluate_length_policy,
    execute_turn,
    export_schemas,
    get_turn_count,
    load_actor_config,
    load_json,
    merge_initial_state,
    render_analyst_report_markdown,
    render_exec_report_markdown,
    render_event_timeline,
    render_terms_and_parameters,
    render_turn_timeline,
    run_sensitivity,
    stable_hash,
    turn_story_cards,
    validate_mission,
    validate_scenario,
    verify_quality_gates,
    write_json,
    write_jsonl,
)


def _build_event_rows(turn_result) -> list[dict]:
    rows: list[dict] = []
    turn_id = turn_result.turn_id
    rows.append(
        {
            "turn_id": turn_id,
            "who": "blue_command",
            "why": turn_result.blue_coa["intent"],
            "input_hash": turn_result.turn_packet["prior_state_hash"],
            "output_hash": stable_hash(turn_result.blue_coa),
            "rule_id": "",
        }
    )
    rows.append(
        {
            "turn_id": turn_id,
            "who": "red_command",
            "why": turn_result.red_coa["intent"],
            "input_hash": turn_result.turn_packet["prior_state_hash"],
            "output_hash": stable_hash(turn_result.red_coa),
            "rule_id": "",
        }
    )
    for rule in turn_result.adjudication.get("rule_fires", []):
        rows.append(
            {
                "turn_id": turn_id,
                "who": "white_cell",
                "why": rule.get("message", "rule fire"),
                "input_hash": stable_hash(
                    {
                        "blue_coa": turn_result.blue_coa,
                        "red_coa": turn_result.red_coa,
                        "evidence_ids": turn_result.adjudication.get("evidence_ids", []),
                    }
                ),
                "output_hash": stable_hash(turn_result.adjudication),
                "rule_id": rule.get("rule_id", ""),
            }
        )
    for event in turn_result.event_ledger:
        rows.append(
            {
                "turn_id": turn_id,
                "who": f"{str(event.get('actor', 'unknown')).lower()}_event_engine",
                "why": event.get("action_detail", ""),
                "input_hash": stable_hash(
                    {
                        "event_id": event.get("event_id", ""),
                        "evidence_ids": event.get("evidence_ids", []),
                    }
                ),
                "output_hash": stable_hash(event),
                "rule_id": event.get("event_type", ""),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full PMESII campaign with V2 reporting and ACH.")
    parser.add_argument("--mission", required=True, help="MissionSpec JSON path")
    parser.add_argument("--scenario", required=True, help="ScenarioPack JSON path")
    parser.add_argument("--actor-config", default=None, help="Actor config JSON path")
    parser.add_argument("--collection-plan", default=None, help="Collection plan JSON path")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--turns", type=int, default=None, help="Override number of turns")
    parser.add_argument("--report-profile", default=None, help="Override report profile: dual_layer|technical_full|exec_only")
    parser.add_argument("--ach-profile", default=None, help="Override ach profile: full|mid|graph")
    parser.add_argument("--term-annotation", default=None, help="Override term annotation: inline_glossary|appendix_only|repeat")
    parser.add_argument("--strict-kj-threshold", type=int, default=None, help="Override high-confidence KJ strict threshold")
    parser.add_argument("--narrative-mode", default=None, help="Override narrative mode: battle_report|event_cards|commander_log")
    parser.add_argument("--baseline-mode", default=None, help="Override baseline mode: public_auto")
    parser.add_argument("--event-granularity", default=None, help="Override event granularity: semi_tactical")
    parser.add_argument("--fidelity-guardrail", default=None, help="Override fidelity guardrail: enabled|disabled")
    parser.add_argument("--length-policy", default=None, help="Override length policy: warn|strict|autofill")
    parser.add_argument("--min-chars-exec", type=int, default=None, help="Override exec report minimum units")
    parser.add_argument("--min-chars-analyst", type=int, default=None, help="Override analyst report minimum units")
    parser.add_argument("--length-counting", default=None, help="Override length counting mode: cjk_chars|all_chars|words")
    args = parser.parse_args()

    mission = load_json(args.mission)
    scenario = load_json(args.scenario)
    actor_config = load_actor_config(args.actor_config)
    collection_plan = load_json(args.collection_plan) if args.collection_plan else {}
    if not isinstance(mission, dict) or not isinstance(scenario, dict) or not isinstance(collection_plan, dict):
        raise SystemExit("mission/scenario/collection-plan must be JSON objects.")

    if args.report_profile:
        mission["report_profile"] = args.report_profile
    if args.ach_profile:
        mission["ach_profile"] = args.ach_profile
    if args.term_annotation:
        mission["term_annotation"] = args.term_annotation
    if args.strict_kj_threshold is not None:
        mission["strict_kj_threshold"] = int(args.strict_kj_threshold)
    if args.narrative_mode:
        mission["narrative_mode"] = args.narrative_mode
    if args.baseline_mode:
        mission["baseline_mode"] = args.baseline_mode
    if args.event_granularity:
        mission["event_granularity"] = args.event_granularity
    if args.fidelity_guardrail:
        mission["fidelity_guardrail"] = args.fidelity_guardrail
    if args.length_policy:
        mission["length_policy"] = args.length_policy
    if args.min_chars_exec is not None:
        mission["min_chars_exec"] = int(args.min_chars_exec)
    if args.min_chars_analyst is not None:
        mission["min_chars_analyst"] = int(args.min_chars_analyst)
    if args.length_counting:
        mission["length_counting"] = args.length_counting

    validate_mission(mission)
    validate_scenario(scenario)

    seed = int(mission.get("seed", 20260305))
    turns = get_turn_count(mission, args.turns)

    out_dir = Path(args.out)
    replay_dir = out_dir / "replay_bundle"
    out_dir.mkdir(parents=True, exist_ok=True)
    replay_dir.mkdir(parents=True, exist_ok=True)
    mission["working_dir"] = str(out_dir)
    mission["baseline_db_path"] = str(out_dir / "actor_baseline_db.sqlite")
    baseline_meta = ensure_actor_baseline_db(mission["baseline_db_path"], mission, collection_plan)

    skill_dir = Path(__file__).resolve().parent.parent
    export_schemas(skill_dir / "assets" / "schemas")

    state = merge_initial_state(scenario)
    all_evidence: list[dict] = []
    run_log_rows: list[dict] = []
    turn_results = []
    story_cards_by_turn: dict[int, list[dict]] = {}
    baseline_deviation_rows: list[dict] = []
    event_rows: list[dict] = []
    source_capture_manifest_rows: list[dict] = []
    claim_registry_rows: list[dict] = []
    evidence_cluster_rows: list[dict] = []
    expert_review_rows: list[dict] = []
    adjudication_dissent_rows: list[dict] = []
    last_indicators: dict = {"leading": [], "significant": [], "confirmatory": []}

    write_json(replay_dir / "turn_00_state.json", state)

    for turn_id in range(1, turns + 1):
        turn_result = execute_turn(
            mission=mission,
            scenario=scenario,
            actor_config=actor_config,
            state=state,
            turn_id=turn_id,
            seed=seed,
            collection_plan=collection_plan,
        )
        turn_results.append(turn_result)
        state = turn_result.state_after
        last_indicators = turn_result.indicators
        all_evidence.extend(turn_result.evidence)
        source_capture_manifest_rows.extend(turn_result.source_capture_manifest)
        claim_registry_rows.extend(turn_result.claim_registry)
        evidence_cluster_rows.extend(turn_result.evidence_clusters)
        expert_review_rows.append({"turn_id": turn_id, **turn_result.expert_review})
        adjudication_dissent_rows.append(
            {
                "turn_id": turn_id,
                "panel_summary": turn_result.adjudication.get("panel_summary", ""),
                "structured_dissent": turn_result.adjudication_dissent,
            }
        )

        write_json(replay_dir / f"turn_{turn_id:02d}_turn_packet.json", turn_result.turn_packet)
        write_json(replay_dir / f"turn_{turn_id:02d}_result.json", turn_result.to_dict())
        write_json(replay_dir / f"turn_{turn_id:02d}_state.json", turn_result.state_after)
        write_json(replay_dir / f"turn_{turn_id:02d}_agent_log.json", turn_result.agent_log)
        write_json(replay_dir / f"turn_{turn_id:02d}_event_ledger.json", turn_result.event_ledger)
        write_json(replay_dir / f"turn_{turn_id:02d}_source_capture_manifest.json", turn_result.source_capture_manifest)
        write_json(replay_dir / f"turn_{turn_id:02d}_expert_review.json", turn_result.expert_review)
        event_rows.extend(turn_result.event_ledger)
        baseline_deviation_rows.extend(turn_result.baseline_deviations)
        turn_cards = turn_story_cards(turn_result)
        story_cards_by_turn[turn_id] = turn_cards
        write_json(replay_dir / f"turn_{turn_id:02d}_story_cards.json", turn_cards)
        run_log_rows.extend(_build_event_rows(turn_result))

    ach_detailed = build_ach_matrix([], evidence_rows=all_evidence, mission=mission)
    ach_summary = _ach_summary_from_detail(ach_detailed)
    key_judgments = derive_key_judgments(
        mission=mission,
        state=state,
        indicators=last_indicators,
        evidence_rows=all_evidence,
        ach_result=ach_detailed,
        event_rows=event_rows,
        baseline_deviation_rows=baseline_deviation_rows,
    )
    sensitivity = run_sensitivity(mission, scenario, state, key_judgments, seed)
    dashboard = build_dashboard(mission, state, last_indicators, key_judgments)
    report_exec = render_exec_report_markdown(
        mission,
        state,
        last_indicators,
        key_judgments,
        ach_detailed,
        turn_results=turn_results,
    )
    report_analyst = render_analyst_report_markdown(
        mission=mission,
        final_state=state,
        indicators=last_indicators,
        key_judgments=key_judgments,
        ach_detail=ach_detailed,
        sensitivity=sensitivity,
        turn_results=turn_results,
        story_cards_by_turn=story_cards_by_turn,
    )
    terms_doc = render_terms_and_parameters(mission, scenario, actor_config)
    timeline_md = render_turn_timeline(turn_results)
    event_timeline_md = render_event_timeline(turn_results)
    report_metrics = build_report_metrics(mission, report_exec, report_analyst)
    length_warnings, length_errors = evaluate_length_policy(mission, report_metrics)
    write_json(out_dir / "report_metrics.json", report_metrics)
    quality_warnings = length_warnings + collect_quality_gate_warnings(mission, all_evidence)
    write_json(out_dir / "quality_gate_warnings.json", {"warnings": quality_warnings})

    quality_errors = verify_quality_gates(
        mission=mission,
        evidence_rows=all_evidence,
        key_judgments=key_judgments,
        ach_detail=ach_detailed,
        report_exec_text=report_exec,
        event_rows=event_rows,
        baseline_deviation_rows=baseline_deviation_rows,
    )
    if quality_errors:
        write_json(out_dir / "quality_gate_errors.json", {"errors": quality_errors})
        raise SystemExit("Quality gates failed. See quality_gate_errors.json")
    if length_errors:
        write_json(out_dir / "quality_gate_errors.json", {"errors": length_errors})
        raise SystemExit("Length policy failed. See quality_gate_errors.json")

    (out_dir / "report_exec.md").write_text(report_exec, encoding="utf-8")
    (out_dir / "report_analyst.md").write_text(report_analyst, encoding="utf-8")
    (out_dir / "report.md").write_text(report_exec, encoding="utf-8")
    (out_dir / "terms_and_parameters.md").write_text(terms_doc, encoding="utf-8")
    (out_dir / "turn_timeline.md").write_text(timeline_md, encoding="utf-8")
    (out_dir / "event_timeline.md").write_text(event_timeline_md, encoding="utf-8")

    write_json(out_dir / "dashboard.json", dashboard)
    write_json(out_dir / "ach.json", ach_summary)
    write_json(out_dir / "ach_detailed.json", ach_detailed)
    write_json(out_dir / "sensitivity.json", sensitivity)
    write_json(out_dir / "evidence.json", all_evidence)
    write_json(out_dir / "source_capture_manifest.json", source_capture_manifest_rows)
    write_json(out_dir / "claim_registry.json", claim_registry_rows)
    write_json(out_dir / "evidence_clusters.json", evidence_cluster_rows)
    write_json(out_dir / "expert_review.json", expert_review_rows)
    write_json(out_dir / "adjudication_dissent.json", adjudication_dissent_rows)
    write_json(out_dir / "event_ledger.json", event_rows)
    write_json(out_dir / "key_judgments.json", key_judgments)
    write_json(
        out_dir / "baseline_deviation_report.json",
        {
            "baseline_db_path": mission["baseline_db_path"],
            "actors": baseline_meta.get("actors", []),
            "records": baseline_deviation_rows,
            "average_score": round(
                sum(float(row.get("severity_score", 0.0)) for row in baseline_deviation_rows) / max(1, len(baseline_deviation_rows)),
                3,
            ),
        },
    )
    write_jsonl(out_dir / "run_log.jsonl", run_log_rows)

    artifact = {
        "report_md": str((out_dir / "report.md").resolve()),
        "report_exec_md": str((out_dir / "report_exec.md").resolve()),
        "report_analyst_md": str((out_dir / "report_analyst.md").resolve()),
        "terms_and_parameters_md": str((out_dir / "terms_and_parameters.md").resolve()),
        "turn_timeline_md": str((out_dir / "turn_timeline.md").resolve()),
        "event_timeline_md": str((out_dir / "event_timeline.md").resolve()),
        "report_metrics_json": str((out_dir / "report_metrics.json").resolve()),
        "quality_gate_warnings_json": str((out_dir / "quality_gate_warnings.json").resolve()),
        "source_capture_manifest_json": str((out_dir / "source_capture_manifest.json").resolve()),
        "claim_registry_json": str((out_dir / "claim_registry.json").resolve()),
        "evidence_clusters_json": str((out_dir / "evidence_clusters.json").resolve()),
        "expert_review_json": str((out_dir / "expert_review.json").resolve()),
        "adjudication_dissent_json": str((out_dir / "adjudication_dissent.json").resolve()),
        "baseline_deviation_report_json": str((out_dir / "baseline_deviation_report.json").resolve()),
        "event_ledger_json": str((out_dir / "event_ledger.json").resolve()),
        "actor_baseline_db": str((out_dir / "actor_baseline_db.sqlite").resolve()),
        "dashboard_json": str((out_dir / "dashboard.json").resolve()),
        "ach_json": str((out_dir / "ach.json").resolve()),
        "ach_detailed_json": str((out_dir / "ach_detailed.json").resolve()),
        "run_log_jsonl": str((out_dir / "run_log.jsonl").resolve()),
        "replay_bundle": str(replay_dir.resolve()),
        "sensitivity_json": str((out_dir / "sensitivity.json").resolve()),
    }
    write_json(out_dir / "run_artifact.json", artifact)

    summary = {
        "turns": turns,
        "seed": seed,
        "final_state_hash": stable_hash(state),
        "final_state": state,
        "key_judgments": [row["claim"] for row in key_judgments],
        "report_profile": mission.get("report_profile", "dual_layer"),
        "ach_profile": mission.get("ach_profile", "full"),
        "narrative_mode": mission.get("narrative_mode", "event_cards"),
        "baseline_mode": mission.get("baseline_mode", "public_auto"),
        "event_granularity": mission.get("event_granularity", "semi_tactical"),
        "fidelity_guardrail": mission.get("fidelity_guardrail", "enabled"),
        "length_policy": mission.get("length_policy", "warn"),
        "length_counting": mission.get("length_counting", "cjk_chars"),
        "evidence_mode": mission.get("evidence_mode", "hybrid"),
        "review_mode": mission.get("review_mode", "ai_panel"),
    }
    write_json(out_dir / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
