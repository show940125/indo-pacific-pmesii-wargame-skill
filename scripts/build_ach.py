from __future__ import annotations

import argparse
from pathlib import Path

from common import _ach_summary_from_detail, build_ach_matrix, load_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Build V2 ACH outputs (detailed + summary).")
    parser.add_argument("--key-judgments", required=True)
    parser.add_argument("--mission", default=None)
    parser.add_argument("--evidence", default=None)
    parser.add_argument("--hypotheses", default=None)
    parser.add_argument("--out", required=True, help="Detailed ACH output path")
    parser.add_argument("--summary-out", default=None, help="Optional summary ACH output path")
    args = parser.parse_args()

    key_judgments = load_json(args.key_judgments)
    mission = load_json(args.mission) if args.mission else None
    evidence = load_json(args.evidence) if args.evidence else None
    hypotheses = load_json(args.hypotheses) if args.hypotheses else None
    if not isinstance(key_judgments, list):
        raise SystemExit("--key-judgments must be a JSON array")

    ach_detailed = build_ach_matrix(
        key_judgments=key_judgments,
        hypotheses=hypotheses if isinstance(hypotheses, list) else None,
        evidence_rows=evidence if isinstance(evidence, list) else None,
        mission=mission if isinstance(mission, dict) else None,
    )
    write_json(args.out, ach_detailed)

    summary_path = Path(args.summary_out) if args.summary_out else Path(args.out).with_name("ach.json")
    write_json(summary_path, _ach_summary_from_detail(ach_detailed))

    print(f"Saved detailed ACH: {Path(args.out)}")
    print(f"Saved summary ACH: {summary_path}")


if __name__ == "__main__":
    main()
