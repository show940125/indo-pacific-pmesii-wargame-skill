from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import resolve_knowledge_db_path
from knowledge_db import (
    SCHEMA_VERSION,
    actor_context_pack,
    connect,
    load_json,
    manifest,
    query_actor_search,
    query_capabilities,
    query_interactions,
    query_platforms,
    query_pmesii,
    query_sources,
    resolve_actor_id,
    select_scenario_actor_ids,
)

DIMENSION_CHOICES = ["P", "M", "E", "S", "I", "Infra"]


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _emit_json(payload: dict[str, Any], pretty: bool = False) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, default=_json_default))


def _emit_markdown(payload: dict[str, Any]) -> None:
    print(f"# {payload.get('query_type', 'knowledge_query')}")
    if "resolved_actor" in payload and payload["resolved_actor"]:
        actor = payload["resolved_actor"]
        print(f"\nActor: `{actor.get('actor_id')}` - {actor.get('display_name')}")
    if "items" in payload:
        print(f"\nItems: {len(payload['items'])}")
        for item in payload["items"]:
            title = item.get("display_name") or item.get("capability_id") or item.get("platform_id") or item.get("metric") or item.get("interaction_id") or item.get("actor_id") or item.get("source_id") or "item"
            print(f"\n## {title}")
            for key, value in item.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                print(f"- `{key}`: {value}")
    elif "context_pack" in payload:
        pack = payload["context_pack"]
        print(f"\nConcrete actor: `{pack.get('concrete_actor_id')}`")
        print(f"Decision question: {payload.get('decision_question', '')}")
        concrete = pack.get("concrete_actor_context") or {}
        print(f"\nPMESII metrics: {len(concrete.get('pmesii_metrics') or [])}")
        print(f"Capabilities: {len(concrete.get('capability_rules') or [])}")
        print(f"Military platforms: {len(concrete.get('military_platforms') or [])}")
        print(f"Weapon interactions: {len(concrete.get('weapon_interactions') or [])}")
    else:
        print("\n```json")
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        print("```")


def _emit(payload: dict[str, Any], fmt: str, pretty: bool = False, max_chars: int | None = None) -> None:
    if max_chars and max_chars > 0:
        raw = json.dumps(payload, ensure_ascii=False, default=_json_default)
        if len(raw) > max_chars:
            payload["limit_warning"] = {
                "truncated": False,
                "original_char_count": len(raw),
                "max_chars": max_chars,
                "message": "Response exceeds max_chars; reduce --max-items or use --no-sources for a smaller prompt.",
            }
    if fmt == "md":
        _emit_markdown(payload)
    else:
        _emit_json(payload, pretty=pretty)


def _error(message: str, *, fmt: str = "json", pretty: bool = False, code: str = "QUERY_ERROR") -> int:
    payload = {"ok": False, "error": {"code": code, "message": message}}
    _emit(payload, fmt, pretty)
    return 2


def _open_db(path_arg: str | None) -> tuple[Path, Any]:
    db_path = resolve_knowledge_db_path(path_arg)
    if not db_path.exists():
        raise FileNotFoundError(f"Knowledge DB not found: {db_path}. Build it with scripts/world_kb_import.py --db {db_path}.")
    return db_path, connect(db_path)


def _resolved_actor(conn: Any, actor: str, mission_path: str | None = None, scenario_path: str | None = None) -> dict[str, Any]:
    mission = load_json(mission_path) if mission_path else None
    scenario = load_json(scenario_path) if scenario_path else None
    return resolve_actor_id(conn, actor, mission=mission, scenario=scenario)


def _base_payload(query_type: str, db_path: Path) -> dict[str, Any]:
    return {"ok": True, "query_type": query_type, "db_path": str(db_path.resolve()), "schema_version": SCHEMA_VERSION}


def _strip_sources_from_context(pack: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(pack)
    cleaned.pop("sources", None)
    cleaned.pop("source_documents", None)
    concrete = dict(cleaned.get("concrete_actor_context") or {})
    concrete.pop("field_provenance", None)
    cleaned["concrete_actor_context"] = concrete
    return cleaned


def _strip_source_fields(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_keys = {"source_id", "source_title", "source_url", "publisher", "source_tier"}
    return [{key: value for key, value in item.items() if key not in source_keys} for item in items]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query the V4 wargame knowledge SQLite database for LLM-safe context packs.")
    parser.add_argument("--db", default=None, help="Knowledge DB path. Defaults to data/wargame_knowledge.sqlite.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser, *, sources: bool = False, chars: int | None = None) -> None:
        p.add_argument("--format", choices=["json", "md"], default="json")
        p.add_argument("--max-items", type=int, default=12)
        p.add_argument("--max-chars", type=int, default=chars)
        if sources:
            source_group = p.add_mutually_exclusive_group()
            source_group.add_argument("--include-sources", action="store_true", default=True)
            source_group.add_argument("--no-sources", action="store_false", dest="include_sources")
        p.add_argument("--pretty", action="store_true")

    add_common(sub.add_parser("manifest", help="Show schema version, table counts, and coverage diagnostics."))

    actor_search = sub.add_parser("actor-search", help="Search actors by id, alias, display name, region, or alignment tags.")
    actor_search.add_argument("--keyword", required=True)
    add_common(actor_search)

    scenario_actors = sub.add_parser("scenario-actors", help="Resolve scenario role candidates from mission and scenario.")
    scenario_actors.add_argument("--mission", required=True)
    scenario_actors.add_argument("--scenario", required=True)
    add_common(scenario_actors)

    actor_context = sub.add_parser("actor-context", help="Return an LLM-ready actor context pack.")
    actor_context.add_argument("--actor", required=True)
    actor_context.add_argument("--mission", required=True)
    actor_context.add_argument("--scenario", required=True)
    actor_context.add_argument("--question", default="")
    actor_context.add_argument("--turn-id", type=int, default=1)
    add_common(actor_context, sources=True, chars=12000)

    pmesii = sub.add_parser("pmesii", help="Query actor PMESII metrics.")
    pmesii.add_argument("--actor", required=True)
    pmesii.add_argument("--dimension", choices=DIMENSION_CHOICES)
    add_common(pmesii, sources=True)

    capabilities = sub.add_parser("capabilities", help="Query actor capability rules.")
    capabilities.add_argument("--actor", required=True)
    capabilities.add_argument("--domain")
    add_common(capabilities, sources=True)

    platforms = sub.add_parser("platforms", help="Query actor military platforms.")
    platforms.add_argument("--actor", required=True)
    platforms.add_argument("--domain")
    add_common(platforms, sources=True)

    interactions = sub.add_parser("interactions", help="Query weapon/platform interaction rules by family.")
    interactions.add_argument("--family", required=True)
    add_common(interactions, sources=True)

    sources = sub.add_parser("sources", help="Query source claims and provenance for an actor.")
    sources.add_argument("--actor", required=True)
    add_common(sources, sources=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    fmt = getattr(args, "format", "json")
    pretty = bool(getattr(args, "pretty", False))
    try:
        if args.command == "scenario-actors":
            mission = load_json(args.mission)
            scenario = load_json(args.scenario)
            payload = {
                "ok": True,
                "query_type": "scenario_actors",
                "schema_version": SCHEMA_VERSION,
                "scenario_roles": select_scenario_actor_ids(mission, scenario),
                "limits": {"max_items": args.max_items},
            }
            _emit(payload, fmt, pretty, getattr(args, "max_chars", None))
            return

        db_path, conn = _open_db(args.db)
        with conn:
            if args.command == "manifest":
                payload = manifest(db_path)
                payload["ok"] = True
                payload["query_type"] = "manifest"
            elif args.command == "actor-search":
                payload = _base_payload("actor_search", db_path)
                payload["items"] = query_actor_search(conn, args.keyword, args.max_items)
                payload["limits"] = {"max_items": args.max_items}
            elif args.command == "actor-context":
                actor = _resolved_actor(conn, args.actor, args.mission, args.scenario)
                question = args.question or f"Context request for {actor['actor_id']}"
                pack = actor_context_pack(
                    db_path,
                    actor["scenario_role"] or actor["actor_id"],
                    args.turn_id,
                    {"P": 50, "M": 50, "E": 50, "S": 50, "I": 50, "Infra": 50},
                    decision_questions=[question],
                    max_rows=args.max_items,
                )
                if not args.include_sources:
                    pack = _strip_sources_from_context(pack)
                payload = _base_payload("actor_context", db_path)
                payload.update(
                    {
                        "resolved_actor": actor,
                        "scenario_role": actor.get("scenario_role"),
                        "decision_question": question,
                        "context_pack": pack,
                        "source_policy": "JSON context is grounded in wargame_knowledge.sqlite; use source/provenance fields for claims.",
                        "limits": {"max_items": args.max_items, "max_chars": args.max_chars, "include_sources": args.include_sources},
                    }
                )
            elif args.command == "pmesii":
                actor = _resolved_actor(conn, args.actor)
                items = query_pmesii(conn, actor["actor_id"], args.dimension, args.max_items)
                if not args.include_sources:
                    items = _strip_source_fields(items)
                payload = _base_payload("pmesii", db_path)
                payload["resolved_actor"] = actor
                payload["items"] = items
                payload["limits"] = {"max_items": args.max_items, "dimension": args.dimension, "include_sources": args.include_sources}
            elif args.command == "capabilities":
                actor = _resolved_actor(conn, args.actor)
                items = query_capabilities(conn, actor["actor_id"], args.domain, args.max_items)
                if not args.include_sources:
                    items = _strip_source_fields(items)
                payload = _base_payload("capabilities", db_path)
                payload["resolved_actor"] = actor
                payload["items"] = items
                payload["limits"] = {"max_items": args.max_items, "domain": args.domain, "include_sources": args.include_sources}
            elif args.command == "platforms":
                actor = _resolved_actor(conn, args.actor)
                items = query_platforms(conn, actor["actor_id"], args.domain, args.max_items)
                if not args.include_sources:
                    items = _strip_source_fields(items)
                payload = _base_payload("platforms", db_path)
                payload["resolved_actor"] = actor
                payload["items"] = items
                payload["limits"] = {"max_items": args.max_items, "domain": args.domain, "include_sources": args.include_sources}
            elif args.command == "interactions":
                payload = _base_payload("interactions", db_path)
                payload["items"] = query_interactions(conn, args.family, args.max_items)
                payload["limits"] = {"max_items": args.max_items, "family": args.family, "include_sources": args.include_sources}
            elif args.command == "sources":
                actor = _resolved_actor(conn, args.actor)
                payload = _base_payload("sources", db_path)
                payload["resolved_actor"] = actor
                payload.update(query_sources(conn, actor["actor_id"], args.max_items))
                payload["limits"] = {"max_items": args.max_items, "include_sources": args.include_sources}
            else:
                raise ValueError(f"Unsupported command: {args.command}")
        _emit(payload, fmt, pretty, getattr(args, "max_chars", None))
    except Exception as exc:
        sys.exit(_error(str(exc), fmt=fmt, pretty=pretty))


if __name__ == "__main__":
    main()
