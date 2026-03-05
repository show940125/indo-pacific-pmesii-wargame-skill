from __future__ import annotations

import argparse
from pathlib import Path

from common import adjudicate_turn, load_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run white-cell adjudication for one turn.")
    parser.add_argument("--mission", required=True)
    parser.add_argument("--turn-packet", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--blue-coa", required=True)
    parser.add_argument("--red-coa", required=True)
    parser.add_argument("--evidence", required=True, help="Fused evidence JSON array")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    mission = load_json(args.mission)
    turn_packet = load_json(args.turn_packet)
    state = load_json(args.state)
    blue_coa = load_json(args.blue_coa)
    red_coa = load_json(args.red_coa)
    evidence = load_json(args.evidence)

    adjudication, new_state = adjudicate_turn(
        mission=mission,
        turn_packet=turn_packet,
        state=state,
        blue_coa=blue_coa,
        red_coa=red_coa,
        fused_evidence=evidence,
        seed=args.seed,
    )

    out_path = Path(args.out)
    write_json(
        out_path,
        {
            "adjudication": adjudication,
            "new_state": new_state,
        },
    )
    print(f"Saved adjudication output: {out_path}")


if __name__ == "__main__":
    main()
