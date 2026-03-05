from __future__ import annotations

import argparse
import json

from common import build_report_metrics, evaluate_length_policy, load_json, validate_mission, verify_quality_gates


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify V2 quality gates and traceability.")
    parser.add_argument("--mission", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--key-judgments", required=True)
    parser.add_argument("--ach", default=None, help="ach_detailed.json path")
    parser.add_argument("--event-ledger", default=None, help="event ledger JSON array path")
    parser.add_argument("--baseline-deviation", default=None, help="baseline_deviation_report.json path")
    parser.add_argument("--report-exec", default=None, help="report_exec.md path")
    parser.add_argument("--report-analyst", default=None, help="report_analyst.md path")
    parser.add_argument("--strict-kj-threshold", type=int, default=None, help="override threshold for this verification run")
    parser.add_argument("--length-policy", default=None, help="override length policy: warn|strict|autofill")
    parser.add_argument("--min-chars-exec", type=int, default=None, help="override exec minimum units")
    parser.add_argument("--min-chars-analyst", type=int, default=None, help="override analyst minimum units")
    parser.add_argument("--length-counting", default=None, help="override length counting mode")
    args = parser.parse_args()

    mission = load_json(args.mission)
    evidence = load_json(args.evidence)
    key_judgments = load_json(args.key_judgments)
    if not isinstance(mission, dict) or not isinstance(evidence, list) or not isinstance(key_judgments, list):
        raise SystemExit("mission must be object; evidence/key-judgments must be arrays")

    if args.strict_kj_threshold is not None:
        mission["strict_kj_threshold"] = int(args.strict_kj_threshold)
    if args.length_policy is not None:
        mission["length_policy"] = args.length_policy
    if args.min_chars_exec is not None:
        mission["min_chars_exec"] = int(args.min_chars_exec)
    if args.min_chars_analyst is not None:
        mission["min_chars_analyst"] = int(args.min_chars_analyst)
    if args.length_counting is not None:
        mission["length_counting"] = args.length_counting
    validate_mission(mission)
    ach_detail = load_json(args.ach) if args.ach else None
    event_rows = load_json(args.event_ledger) if args.event_ledger else None
    baseline_report = load_json(args.baseline_deviation) if args.baseline_deviation else None
    baseline_rows = None
    if isinstance(baseline_report, dict):
        records = baseline_report.get("records", [])
        baseline_rows = records if isinstance(records, list) else None
    elif isinstance(baseline_report, list):
        baseline_rows = baseline_report
    report_exec_text = None
    if args.report_exec:
        with open(args.report_exec, "r", encoding="utf-8") as file:
            report_exec_text = file.read()
    report_analyst_text = None
    if args.report_analyst:
        with open(args.report_analyst, "r", encoding="utf-8") as file:
            report_analyst_text = file.read()

    errors = verify_quality_gates(
        mission=mission,
        evidence_rows=evidence,
        key_judgments=key_judgments,
        ach_detail=ach_detail if isinstance(ach_detail, dict) else None,
        report_exec_text=report_exec_text,
        event_rows=event_rows if isinstance(event_rows, list) else None,
        baseline_deviation_rows=baseline_rows,
    )
    warnings: list[str] = []
    metrics = None
    if report_exec_text is not None and report_analyst_text is not None:
        metrics = build_report_metrics(mission, report_exec_text, report_analyst_text)
        length_warnings, length_errors = evaluate_length_policy(mission, metrics)
        warnings.extend(length_warnings)
        errors.extend(length_errors)
    elif args.length_policy is not None or args.min_chars_exec is not None or args.min_chars_analyst is not None:
        warnings.append("length check skipped because both --report-exec and --report-analyst are required.")
    if errors:
        print(
            json.dumps(
                {"status": "failed", "errors": errors, "warnings": warnings, "report_metrics": metrics},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)
    checks = 9 if args.event_ledger or args.baseline_deviation else (7 if args.ach or args.report_exec else 5)
    print(
        json.dumps(
            {"status": "passed", "checks": checks, "warnings": warnings, "report_metrics": metrics},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
