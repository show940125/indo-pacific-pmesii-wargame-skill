from __future__ import annotations

import argparse
import json
from pathlib import Path

from knowledge_db import actor_context_pack, load_json, manifest, seed_database, select_scenario_actor_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and inspect the V4 world knowledge layer.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--mission", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--actor-config")
    parser.add_argument("--collection-plan")
    parser.add_argument("--references-dir")
    parser.add_argument("--world-seed-dir")
    parser.add_argument("--context-actor")
    args = parser.parse_args()

    mission = load_json(args.mission)
    scenario = load_json(args.scenario)
    meta = seed_database(
        db_path=args.db,
        mission=mission,
        scenario=scenario,
        actor_config=load_json(args.actor_config) if args.actor_config else {},
        collection_plan=load_json(args.collection_plan) if args.collection_plan else {},
        references_dir=args.references_dir,
        world_seed_dir=args.world_seed_dir,
    )
    output = {
        "manifest": meta,
        "selected_actor_roles": select_scenario_actor_ids(mission, scenario),
    }
    if args.context_actor:
        output["context_pack"] = actor_context_pack(Path(args.db), args.context_actor, 1, {"P": 50, "M": 70, "E": 55, "S": 48, "I": 72, "Infra": 53})
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
