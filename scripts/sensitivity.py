from __future__ import annotations

import argparse
from pathlib import Path

from common import derive_key_judgments, indicator_from_state, load_json, run_sensitivity, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run sensitivity checks for assumption breakpoints.")
    parser.add_argument("--mission", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--state", required=True, help="Final PMESII state JSON")
    parser.add_argument("--evidence", required=True, help="Evidence JSON array")
    parser.add_argument("--seed", type=int, default=20260305)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    mission = load_json(args.mission)
    scenario = load_json(args.scenario)
    state = load_json(args.state)
    evidence = load_json(args.evidence)

    indicators = indicator_from_state(state)
    key_judgments = derive_key_judgments(mission, state, indicators, evidence)
    sensitivity = run_sensitivity(mission, scenario, state, key_judgments, args.seed)

    out_path = Path(args.out)
    write_json(out_path, sensitivity)
    print(f"Saved sensitivity results: {out_path}")


if __name__ == "__main__":
    main()
