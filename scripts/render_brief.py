from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import (
    _ach_summary_from_detail,
    build_dashboard,
    build_report_metrics,
    evaluate_length_policy,
    load_json,
    render_analyst_report_markdown,
    render_exec_report_markdown,
    render_terms_and_parameters,
)


def _load_turn_results(replay_dir: Path) -> list[dict]:
    results = []
    for file in sorted(replay_dir.glob("turn_*_result.json")):
        payload = load_json(file)
        if isinstance(payload, dict):
            results.append(payload)
    return results


def _render_timeline_from_dicts(turn_results: list[dict]) -> str:
    lines = [
        "# 逐回合時間線",
        "",
        "| 回合 | 裁決 | M | I | P | E | 主要規則 | 主要證據數 |",
        "|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for row in turn_results:
        turn_id = row.get("turn_id", "?")
        adjudication = row.get("adjudication", {})
        after = row.get("state_after", {})
        rules = ",".join(adjudication.get("rule_hits", [])[:3])
        lines.append(
            f"| {turn_id} | {adjudication.get('decision', '')} | {after.get('M', '')} | {after.get('I', '')} | {after.get('P', '')} | {after.get('E', '')} | {rules} | {len(row.get('evidence', []))} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render V2 reports and dashboard.")
    parser.add_argument("--mission", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--actor-config", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--indicators", required=True)
    parser.add_argument("--key-judgments", required=True)
    parser.add_argument("--ach-detailed", required=True)
    parser.add_argument("--sensitivity", required=True)
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--out-exec", required=True)
    parser.add_argument("--out-analyst", required=True)
    parser.add_argument("--out-dashboard", required=True)
    parser.add_argument("--out-terms", required=True)
    parser.add_argument("--out-timeline", required=True)
    parser.add_argument("--out-ach", default=None)
    parser.add_argument("--out-metrics", default=None)
    parser.add_argument("--out-warnings", default=None)
    args = parser.parse_args()

    mission = load_json(args.mission)
    scenario = load_json(args.scenario)
    actor_config = load_json(args.actor_config)
    state = load_json(args.state)
    indicators = load_json(args.indicators)
    key_judgments = load_json(args.key_judgments)
    ach_detailed = load_json(args.ach_detailed)
    sensitivity = load_json(args.sensitivity)
    replay_dir = Path(args.replay_dir)
    turn_results = _load_turn_results(replay_dir)

    report_exec = render_exec_report_markdown(
        mission,
        state,
        indicators,
        key_judgments,
        ach_detailed,
        turn_results=turn_results,
    )
    report_analyst = render_analyst_report_markdown(
        mission=mission,
        final_state=state,
        indicators=indicators,
        key_judgments=key_judgments,
        ach_detail=ach_detailed,
        sensitivity=sensitivity,
        turn_results=turn_results,
    )
    dashboard = build_dashboard(mission, state, indicators, key_judgments)
    terms_doc = render_terms_and_parameters(mission, scenario, actor_config)

    exec_path = Path(args.out_exec)
    analyst_path = Path(args.out_analyst)
    dashboard_path = Path(args.out_dashboard)
    terms_path = Path(args.out_terms)
    timeline_path = Path(args.out_timeline)
    for path in [exec_path, analyst_path, dashboard_path, terms_path, timeline_path]:
        path.parent.mkdir(parents=True, exist_ok=True)

    exec_path.write_text(report_exec, encoding="utf-8")
    analyst_path.write_text(report_analyst, encoding="utf-8")
    terms_path.write_text(terms_doc, encoding="utf-8")
    timeline_path.write_text(_render_timeline_from_dicts(turn_results), encoding="utf-8")
    dashboard_path.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.out_metrics:
        metrics_path = Path(args.out_metrics)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics = build_report_metrics(mission, report_exec, report_analyst)
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.out_warnings:
            warnings_path = Path(args.out_warnings)
            warnings_path.parent.mkdir(parents=True, exist_ok=True)
            warnings, _ = evaluate_length_policy(mission, metrics)
            warnings_path.write_text(json.dumps({"warnings": warnings}, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.out_ach:
        summary_path = Path(args.out_ach)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(_ach_summary_from_detail(ach_detailed), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"Rendered exec report: {exec_path}")
    print(f"Rendered analyst report: {analyst_path}")


if __name__ == "__main__":
    main()
