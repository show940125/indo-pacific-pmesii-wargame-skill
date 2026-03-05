from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    execute_turn,
    load_actor_config,
    load_json,
    merge_initial_state,
    validate_mission,
    validate_scenario,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single turn with multi-agent/subagent flow.")
    parser.add_argument("--mission", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--actor-config", default=None)
    parser.add_argument("--collection-plan", default=None)
    parser.add_argument("--turn-packet", default=None, help="Existing turn packet (optional; turn id inferred).")
    parser.add_argument("--state", default=None, help="State JSON path. If missing, uses scenario initial_state.")
    parser.add_argument("--turn-id", type=int, default=None, help="Turn id when no turn packet is provided.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    mission = load_json(args.mission)
    scenario = load_json(args.scenario)
    validate_mission(mission)
    validate_scenario(scenario)
    actor_config = load_actor_config(args.actor_config)
    collection_plan = load_json(args.collection_plan) if args.collection_plan else {}

    state = load_json(args.state) if args.state else merge_initial_state(scenario)
    if args.turn_packet:
        turn_packet = load_json(args.turn_packet)
        turn_id = int(turn_packet["turn_id"])
    elif args.turn_id is not None:
        turn_id = int(args.turn_id)
    else:
        raise SystemExit("Provide either --turn-packet or --turn-id.")

    seed = int(args.seed if args.seed is not None else mission.get("seed", 20260305))
    out_path = Path(args.out)
    mission.setdefault("working_dir", str(out_path.parent))
    mission.setdefault("baseline_db_path", str(out_path.parent / "actor_baseline_db.sqlite"))
    result = execute_turn(mission, scenario, actor_config, state, turn_id, seed, collection_plan)

    write_json(out_path, result.to_dict())
    print(f"Saved turn result: {out_path}")


if __name__ == "__main__":
    main()
