from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DIMENSIONS = ["P", "M", "E", "S", "I", "Infra"]
SCHEMA_VERSION = 6


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(db_path: str | Path) -> None:
    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rebuild = False
    if target.exists():
        try:
            conn = sqlite3.connect(target)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key='schema_version'")
            row = cursor.fetchone()
            if row and int(row[0]) < SCHEMA_VERSION:
                rebuild = True
            conn.close()
        except Exception:
            rebuild = True
    if rebuild:
        try:
            target.unlink()
        except Exception as e:
            raise RuntimeError(f"Failed to unlink database file {target} during migration: {e}") from e

    with connect(target) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actors (
              actor_id TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              faction TEXT NOT NULL,
              goals_json TEXT NOT NULL,
              redlines_json TEXT NOT NULL,
              command_style TEXT NOT NULL,
              risk_tolerance REAL NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actor_doctrine (
              actor_id TEXT NOT NULL,
              dimension TEXT NOT NULL,
              preferred_actions_json TEXT NOT NULL,
              taboos_json TEXT NOT NULL,
              escalation_logic TEXT NOT NULL,
              deescalation_conditions_json TEXT NOT NULL,
              PRIMARY KEY(actor_id, dimension)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pmesii_indicators (
              dimension TEXT PRIMARY KEY,
              definition TEXT NOT NULL,
              normal_low REAL NOT NULL,
              normal_high REAL NOT NULL,
              stress_interpretation TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS capabilities (
              actor_id TEXT NOT NULL,
              domain TEXT NOT NULL,
              capability TEXT NOT NULL,
              limits TEXT NOT NULL,
              confidence REAL NOT NULL,
              PRIMARY KEY(actor_id, domain, capability)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS constraints (
              constraint_id TEXT PRIMARY KEY,
              actor_id TEXT,
              category TEXT NOT NULL,
              rule_text TEXT NOT NULL,
              severity TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
              source_id TEXT PRIMARY KEY,
              source_name TEXT NOT NULL,
              independence_group TEXT NOT NULL,
              reliability_prior REAL NOT NULL,
              update_frequency TEXT NOT NULL,
              citation_policy TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scenario_facts (
              fact_id TEXT PRIMARY KEY,
              scope TEXT NOT NULL,
              fact_text TEXT NOT NULL,
              source_id TEXT,
              confidence REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turn_memory (
              run_id TEXT NOT NULL,
              turn_id INTEGER NOT NULL,
              actor_id TEXT NOT NULL,
              decision_json TEXT NOT NULL,
              state_delta_json TEXT NOT NULL,
              controller_rationale TEXT NOT NULL,
              violations_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(run_id, turn_id, actor_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS world_actors (
              actor_id TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              actor_type TEXT NOT NULL,
              region TEXT NOT NULL,
              alignment_tags_json TEXT NOT NULL,
              default_bloc_affinity TEXT NOT NULL,
              source_note TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS actor_aliases (alias TEXT PRIMARY KEY, actor_id TEXT NOT NULL)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actor_bloc_roles (
              scenario_id TEXT NOT NULL,
              role TEXT NOT NULL,
              actor_id TEXT NOT NULL,
              rationale TEXT NOT NULL,
              PRIMARY KEY(scenario_id, role, actor_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_sources (
              source_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              url TEXT NOT NULL,
              publisher TEXT NOT NULL,
              source_tier TEXT NOT NULL,
              reliability_prior REAL NOT NULL,
              captured_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actor_pmesii_metrics (
              actor_id TEXT NOT NULL,
              metric TEXT NOT NULL,
              dimension TEXT NOT NULL,
              raw_value TEXT NOT NULL,
              normalized_score REAL NOT NULL,
              source_id TEXT NOT NULL,
              data_year INTEGER NOT NULL,
              confidence REAL NOT NULL,
              model_notes TEXT NOT NULL,
              PRIMARY KEY(actor_id, metric)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS military_platforms (
              platform_id TEXT PRIMARY KEY,
              actor_id TEXT NOT NULL,
              family TEXT NOT NULL,
              model TEXT NOT NULL,
              domain TEXT NOT NULL,
              quantity_min INTEGER,
              quantity_max INTEGER,
              readiness_band TEXT NOT NULL,
              range_effect_class TEXT NOT NULL,
              role TEXT NOT NULL,
              source_id TEXT NOT NULL,
              confidence REAL NOT NULL,
              initial_ammo_stock INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_capabilities (
              platform_id TEXT NOT NULL,
              capability_id TEXT NOT NULL,
              effect_class TEXT NOT NULL,
              pmesii_effect_json TEXT NOT NULL,
              constraints_json TEXT NOT NULL,
              PRIMARY KEY(platform_id, capability_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weapon_interactions (
              interaction_id TEXT PRIMARY KEY,
              attacker_family TEXT NOT NULL,
              defender_family TEXT NOT NULL,
              relationship TEXT NOT NULL,
              effect TEXT NOT NULL,
              limits TEXT NOT NULL,
              p_success_min REAL,
              p_success_max REAL,
              ammo_consume_attacker INTEGER,
              ammo_consume_defender INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS force_posture (
              actor_id TEXT NOT NULL,
              theater TEXT NOT NULL,
              posture_summary TEXT NOT NULL,
              readiness_band TEXT NOT NULL,
              source_id TEXT NOT NULL,
              confidence REAL NOT NULL,
              PRIMARY KEY(actor_id, theater)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS capability_rules (
              capability_id TEXT PRIMARY KEY,
              actor_id TEXT NOT NULL,
              definition TEXT NOT NULL,
              preconditions_json TEXT NOT NULL,
              triggers_json TEXT NOT NULL,
              effects_json TEXT NOT NULL,
              costs_json TEXT NOT NULL,
              risks_json TEXT NOT NULL,
              countermeasures_json TEXT NOT NULL,
              cooldown_latency TEXT NOT NULL,
              pmesii_deltas_json TEXT NOT NULL,
              source_id TEXT NOT NULL,
              confidence REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS capability_triggers (capability_id TEXT NOT NULL, trigger_text TEXT NOT NULL, PRIMARY KEY(capability_id, trigger_text))")
        conn.execute("CREATE TABLE IF NOT EXISTS capability_effects (capability_id TEXT NOT NULL, effect_text TEXT NOT NULL, PRIMARY KEY(capability_id, effect_text))")
        conn.execute("CREATE TABLE IF NOT EXISTS capability_constraints (capability_id TEXT NOT NULL, constraint_text TEXT NOT NULL, PRIMARY KEY(capability_id, constraint_text))")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_documents (
              source_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              url TEXT NOT NULL,
              publisher TEXT NOT NULL,
              source_tier TEXT NOT NULL,
              reliability_prior REAL NOT NULL,
              captured_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_claims (
              claim_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              actor_id TEXT,
              claim_text TEXT NOT NULL,
              claim_type TEXT NOT NULL,
              confidence REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS field_provenance (
              table_name TEXT NOT NULL,
              record_id TEXT NOT NULL,
              field_name TEXT NOT NULL,
              source_id TEXT NOT NULL,
              source_url TEXT NOT NULL,
              data_year INTEGER,
              confidence REAL NOT NULL,
              notes TEXT NOT NULL,
              PRIMARY KEY(table_name, record_id, field_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quality_diagnostics (
              diagnostic_id TEXT PRIMARY KEY,
              diagnostic_type TEXT NOT NULL,
              subject TEXT NOT NULL,
              status TEXT NOT NULL,
              details_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmark_cases (
              case_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              expected_actor_ids_json TEXT NOT NULL,
              expected_checks_json TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geographic_theaters (
                theater_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                domain_type TEXT NOT NULL,
                logistics_capacity INTEGER NOT NULL,
                description TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS theater_connections (
                from_theater TEXT NOT NULL,
                to_theater TEXT NOT NULL,
                transit_turns_sea INTEGER NOT NULL,
                transit_turns_air INTEGER NOT NULL,
                political_access_rule TEXT,
                PRIMARY KEY (from_theater, to_theater),
                FOREIGN KEY (from_theater) REFERENCES geographic_theaters(theater_id),
                FOREIGN KEY (to_theater) REFERENCES geographic_theaters(theater_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actor_deployments (
                deployment_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                platform_id TEXT NOT NULL,
                theater_id TEXT NOT NULL,
                quantity_deployed INTEGER NOT NULL,
                current_status TEXT NOT NULL,
                destination_theater TEXT,
                remaining_transit_turns INTEGER,
                FOREIGN KEY (actor_id) REFERENCES world_actors(actor_id),
                FOREIGN KEY (platform_id) REFERENCES military_platforms(platform_id),
                FOREIGN KEY (theater_id) REFERENCES geographic_theaters(theater_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_inventories (
                actor_id TEXT NOT NULL,
                platform_family TEXT NOT NULL,
                stock_current INTEGER NOT NULL,
                stock_max INTEGER NOT NULL,
                burn_rate_standby REAL NOT NULL,
                burn_rate_active REAL NOT NULL,
                resupply_rate_turn INTEGER NOT NULL,
                PRIMARY KEY (actor_id, platform_family),
                FOREIGN KEY (actor_id) REFERENCES world_actors(actor_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geographic_bases (
                base_id TEXT PRIMARY KEY,
                theater_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                base_type TEXT NOT NULL CHECK(base_type IN ('naval_port', 'air_base', 'ground_garrison', 'radar_outpost')),
                max_capacity_units INTEGER NOT NULL,
                port_throughput_tons_day INTEGER DEFAULT 0,
                active_defense_level REAL DEFAULT 0.8,
                radar_coverage_range_km INTEGER NOT NULL,
                FOREIGN KEY (theater_id) REFERENCES geographic_theaters(theater_id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_munitions (
                munitions_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                munitions_family TEXT NOT NULL,
                unit_cost_usd_k INTEGER NOT NULL,
                range_class_km INTEGER NOT NULL,
                warhead_type TEXT NOT NULL,
                penetration_factor REAL NOT NULL,
                guidance_system TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS base_inventories (
                base_id TEXT NOT NULL,
                munitions_id TEXT NOT NULL,
                stock_current INTEGER NOT NULL,
                stock_max INTEGER NOT NULL,
                burn_rate_standby REAL NOT NULL DEFAULT 0.005,
                burn_rate_active REAL NOT NULL DEFAULT 2.0,
                resupply_rate_turn INTEGER NOT NULL,
                PRIMARY KEY (base_id, munitions_id),
                FOREIGN KEY (base_id) REFERENCES geographic_bases(base_id),
                FOREIGN KEY (munitions_id) REFERENCES platform_munitions(munitions_id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logistics_lanes (
                lane_id TEXT PRIMARY KEY,
                from_base TEXT NOT NULL,
                to_base TEXT NOT NULL,
                transit_turns INTEGER NOT NULL,
                transit_type TEXT NOT NULL CHECK(transit_type IN ('sea', 'air', 'land')),
                capacity_limit_tons_turn INTEGER NOT NULL,
                interdiction_risk REAL DEFAULT 0.0,
                FOREIGN KEY (from_base) REFERENCES geographic_bases(base_id),
                FOREIGN KEY (to_base) REFERENCES geographic_bases(base_id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actor_redlines (
                redline_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                trigger_condition TEXT NOT NULL,
                escalation_doctrine_json TEXT NOT NULL,
                pmesii_impact_json TEXT NOT NULL,
                is_triggered BOOLEAN DEFAULT 0,
                FOREIGN KEY (actor_id) REFERENCES world_actors(actor_id)
            );
            """
        )
        conn.execute("INSERT OR REPLACE INTO metadata(key,value,updated_at) VALUES(?,?,?)", ("schema_version", str(SCHEMA_VERSION), now_iso()))


def _fetch_all(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _seed_paths() -> tuple[Path, Path]:
    root = skill_dir() / "assets" / "world_seed"
    return root / "actors_core.json", root / "military_taxonomy.json"


def load_world_seed(seed_dir: str | Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    if seed_dir:
        root = Path(seed_dir)
        return load_json(root / "actors_core.json"), load_json(root / "military_taxonomy.json")
    actors_path, military_path = _seed_paths()
    return load_json(actors_path), load_json(military_path)


def select_scenario_actor_ids(mission: dict[str, Any], scenario: dict[str, Any]) -> dict[str, list[str]]:
    explicit = mission.get("actor_ids") or scenario.get("actor_ids")
    if isinstance(explicit, dict):
        return {str(k): [str(x).upper() for x in v] for k, v in explicit.items() if isinstance(v, list)}
    text = " ".join([str(mission.get("topic", "")), str(mission.get("geo_scope", "")), str(scenario.get("baseline", ""))]).lower()
    if any(token in text for token in ["台灣", "taiwan", "台海", "first island", "south china sea", "南海"]):
        return {"Blue": ["TW", "US", "JP", "PH", "AU"], "Red": ["CN", "RU"], "Neutral": ["KR", "VN", "SG", "IN"], "Non-state": []}
    if any(token in text for token in ["韓", "korea", "peninsula", "dprk", "north korea"]):
        return {"Blue": ["KR", "US", "JP"], "Red": ["KP", "CN", "RU"], "Neutral": [], "Non-state": []}
    if any(token in text for token in ["iran", "伊朗", "israel", "以色列", "gulf", "波斯灣", "red sea", "紅海", "middle east", "中東"]):
        return {"Blue": ["US", "IL", "SA", "AE", "GCC"], "Red": ["IR", "HOUTHIS", "HEZBOLLAH"], "Neutral": ["QA", "TR", "EU"], "Non-state": ["HOUTHIS", "HEZBOLLAH"]}
    return {"Blue": ["US", "JP", "AU", "PH"], "Red": ["CN", "RU"], "Neutral": ["IN", "VN", "SG", "KR"], "Non-state": []}


def _insert_provenance(conn: sqlite3.Connection, table: str, record_id: str, fields: list[str], source: dict[str, Any], data_year: int | None, confidence: float, notes: str) -> None:
    for field in fields:
        conn.execute(
            """
            INSERT OR REPLACE INTO field_provenance(table_name,record_id,field_name,source_id,source_url,data_year,confidence,notes)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (table, record_id, field, source.get("source_id", ""), source.get("url", ""), data_year, confidence, notes),
        )


def _seed_world_tables(
    conn: sqlite3.Connection,
    mission: dict[str, Any],
    scenario: dict[str, Any],
    world_seed: dict[str, Any],
    military_seed: dict[str, Any],
) -> None:
    now = now_iso()
    source_by_id: dict[str, dict[str, Any]] = {}
    for source in world_seed.get("source_documents", []):
        source_by_id[str(source["source_id"])] = source
        row = (
            source["source_id"],
            source["title"],
            source["url"],
            source["publisher"],
            source["source_tier"],
            float(source["reliability_prior"]),
            now,
        )
        conn.execute("INSERT OR REPLACE INTO source_documents(source_id,title,url,publisher,source_tier,reliability_prior,captured_at) VALUES(?,?,?,?,?,?,?)", row)
        conn.execute("INSERT OR REPLACE INTO metric_sources(source_id,title,url,publisher,source_tier,reliability_prior,captured_at) VALUES(?,?,?,?,?,?,?)", row)

    for actor in world_seed.get("actors", []):
        actor_id = str(actor["actor_id"]).upper()
        conn.execute(
            """
            INSERT OR REPLACE INTO world_actors(actor_id,display_name,actor_type,region,alignment_tags_json,default_bloc_affinity,source_note,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                actor_id,
                actor["display_name"],
                actor["actor_type"],
                actor["region"],
                _json(actor.get("alignment_tags", [])),
                actor.get("default_bloc_affinity", "Neutral"),
                world_seed.get("source_policy", "layered open-source seed"),
                now,
            ),
        )
        for alias in [actor_id, actor["display_name"], *actor.get("aliases", [])]:
            conn.execute("INSERT OR REPLACE INTO actor_aliases(alias,actor_id) VALUES(?,?)", (str(alias).lower(), actor_id))

    role_map = select_scenario_actor_ids(mission, scenario)
    conn.execute("DELETE FROM actor_bloc_roles WHERE scenario_id='current'")
    for role, actor_ids in role_map.items():
        for actor_id in actor_ids:
            conn.execute(
                "INSERT OR REPLACE INTO actor_bloc_roles(scenario_id,role,actor_id,rationale) VALUES(?,?,?,?)",
                ("current", role, actor_id, f"Selected from scenario topic/geo_scope for {role} role."),
            )

    for metric in world_seed.get("pmesii_metrics", []):
        actor_id = str(metric["actor_id"]).upper()
        conn.execute(
            """
            INSERT OR REPLACE INTO actor_pmesii_metrics(actor_id,metric,dimension,raw_value,normalized_score,source_id,data_year,confidence,model_notes)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                actor_id,
                metric["metric"],
                metric["dimension"],
                metric["raw_value"],
                float(metric["normalized_score"]),
                metric["source_id"],
                int(metric["data_year"]),
                float(metric["confidence"]),
                metric["model_notes"],
            ),
        )
        source = source_by_id.get(metric["source_id"], {"source_id": metric["source_id"], "url": ""})
        _insert_provenance(conn, "actor_pmesii_metrics", f"{actor_id}:{metric['metric']}", ["raw_value", "normalized_score"], source, int(metric["data_year"]), float(metric["confidence"]), metric["model_notes"])

    for row in military_seed.get("weapon_interactions", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO weapon_interactions(
                interaction_id,attacker_family,defender_family,relationship,effect,limits,
                p_success_min,p_success_max,ammo_consume_attacker,ammo_consume_defender
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["interaction_id"],
                row["attacker_family"],
                row["defender_family"],
                row["relationship"],
                row["effect"],
                row["limits"],
                row.get("p_success_min", 0.1),
                row.get("p_success_max", 0.9),
                row.get("ammo_consume_attacker", 1),
                row.get("ammo_consume_defender", 1)
            ),
        )
    for row in military_seed.get("platforms", []):
        actor_id = str(row["actor_id"]).upper()
        conn.execute(
            """
            INSERT OR REPLACE INTO military_platforms(platform_id,actor_id,family,model,domain,quantity_min,quantity_max,readiness_band,range_effect_class,role,source_id,confidence,initial_ammo_stock)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["platform_id"],
                actor_id,
                row["family"],
                row["model"],
                row["domain"],
                int(row["quantity_min"]),
                int(row["quantity_max"]),
                row["readiness_band"],
                row["range_effect_class"],
                row["role"],
                row["source_id"],
                float(row["confidence"]),
                row.get("initial_ammo_stock", 1000)
            ),
        )
        cap_id = f"CAP_{row['platform_id']}"
        pmesii_delta = {"M": 1.0 if row["domain"] in {"air", "naval", "missile", "air_defense", "ground"} else 0.4, "I": 0.5 if row["domain"] in {"cyber", "air"} else 0.0}
        constraints = ["requires theater access", "effect depends on readiness and targeting quality", "use quantity bands rather than exact attrition claims"]
        conn.execute(
            """
            INSERT OR REPLACE INTO platform_capabilities(platform_id,capability_id,effect_class,pmesii_effect_json,constraints_json)
            VALUES(?,?,?,?,?)
            """,
            (row["platform_id"], cap_id, row["range_effect_class"], _json(pmesii_delta), _json(constraints)),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO capability_rules(capability_id,actor_id,definition,preconditions_json,triggers_json,effects_json,costs_json,risks_json,countermeasures_json,cooldown_latency,pmesii_deltas_json,source_id,confidence)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                cap_id,
                actor_id,
                f"{row['model']} enables {row['role']} for {actor_id}.",
                _json(["platform available", "scenario geography in range", "political authorization"]),
                _json(["PMESII military pressure above baseline", "opponent action threatens relevant domain"]),
                _json([row["range_effect_class"], row["role"]]),
                _json(["readiness consumption", "escalation cost", "logistics exposure"]),
                _json(["miscalculation", "counterstrike", "source uncertainty"]),
                _json(["dispersion", "air defense", "electronic warfare", "diplomatic off-ramp"]),
                "turn-level; effect should be rechecked every turn",
                _json(pmesii_delta),
                row["source_id"],
                float(row["confidence"]),
            ),
        )
        for trigger in ["PMESII military pressure above baseline", "opponent action threatens relevant domain"]:
            conn.execute("INSERT OR REPLACE INTO capability_triggers(capability_id,trigger_text) VALUES(?,?)", (cap_id, trigger))
        for effect in [row["range_effect_class"], row["role"]]:
            conn.execute("INSERT OR REPLACE INTO capability_effects(capability_id,effect_text) VALUES(?,?)", (cap_id, effect))
        for constraint in constraints:
            conn.execute("INSERT OR REPLACE INTO capability_constraints(capability_id,constraint_text) VALUES(?,?)", (cap_id, constraint))
        source = source_by_id.get(row["source_id"], {"source_id": row["source_id"], "url": ""})
        _insert_provenance(conn, "military_platforms", row["platform_id"], ["quantity_min", "quantity_max", "model", "role"], source, 2025, float(row["confidence"]), "V4 seed uses quantity bands to avoid false precision.")

    for role, actor_ids in role_map.items():
        for actor_id in actor_ids:
            platforms = conn.execute("SELECT COUNT(*) AS n FROM military_platforms WHERE actor_id=?", (actor_id,)).fetchone()["n"]
            posture = "No platform seed yet; rely on PMESII and actor doctrine." if platforms == 0 else f"{platforms} seeded platform records available for context."
            conn.execute(
                "INSERT OR REPLACE INTO force_posture(actor_id,theater,posture_summary,readiness_band,source_id,confidence) VALUES(?,?,?,?,?,?)",
                (actor_id, "current", posture, "mixed", "SRC_WIKIPEDIA", 0.55),
            )

    cases = [
        ("taiwan_blockade", "Taiwan Strait blockade pressure", ["US", "CN", "TW", "JP"], ["actor_selection", "military_grounding", "controller_violation"]),
        ("grey_zone_harassment", "Grey-zone maritime and information pressure", ["CN", "TW", "PH", "US"], ["pmesii_grounding", "source_provenance"]),
        ("iran_israel_escalation", "Iran-Israel escalation chain", ["IR", "IL", "US", "GCC", "HOUTHIS", "HEZBOLLAH"], ["military_capability_grounding", "white_dissent"]),
        ("korean_peninsula_crisis", "Korean Peninsula crisis", ["KP", "KR", "US", "JP", "CN"], ["actor_selection", "missile_defense_interaction"]),
        ("south_china_sea_friction", "South China Sea friction", ["CN", "PH", "US", "VN", "SG"], ["maritime_interactions", "source_provenance"]),
    ]
    for case_id, title, actors, checks in cases:
        conn.execute(
            "INSERT OR REPLACE INTO benchmark_cases(case_id,title,expected_actor_ids_json,expected_checks_json,status) VALUES(?,?,?,?,?)",
            (case_id, title, _json(actors), _json(checks), "seeded"),
        )

    # Seed default theaters
    theaters = [
        ("red_sea", "Red Sea", "maritime", 100, "Critical maritime transit corridor and chokepoint near Yemen."),
        ("strait_of_hormuz", "Strait of Hormuz", "maritime", 150, "Vital chokepoint for global oil transit between Gulf and Arabian Sea."),
        ("levant_corridor", "Levant Corridor", "land", 80, "Land corridor connecting Iraq, Syria, Lebanon, and Israel."),
        ("persian_gulf", "Persian Gulf", "maritime", 120, "Gulf waters surrounding Iran, Iraq, and GCC states."),
    ]
    for theater_id, name, domain, cap, desc in theaters:
        conn.execute(
            """
            INSERT OR REPLACE INTO geographic_theaters(theater_id, display_name, domain_type, logistics_capacity, description)
            VALUES(?,?,?,?,?)
            """,
            (theater_id, name, domain, cap, desc),
        )

    # Seed default theater connections
    connections = [
        ("red_sea", "strait_of_hormuz", 2, 1, "requires transit clearance"),
        ("strait_of_hormuz", "red_sea", 2, 1, "requires transit clearance"),
        ("red_sea", "levant_corridor", 3, 1, "open transit"),
        ("levant_corridor", "red_sea", 3, 1, "open transit"),
        ("strait_of_hormuz", "levant_corridor", 4, 1, "restricted access"),
        ("levant_corridor", "strait_of_hormuz", 4, 1, "restricted access"),
        ("persian_gulf", "strait_of_hormuz", 1, 1, "open transit"),
        ("strait_of_hormuz", "persian_gulf", 1, 1, "open transit"),
    ]
    for from_t, to_t, sea_t, air_t, access in connections:
        conn.execute(
            """
            INSERT OR REPLACE INTO theater_connections(from_theater, to_theater, transit_turns_sea, transit_turns_air, political_access_rule)
            VALUES(?,?,?,?,?)
            """,
            (from_t, to_t, sea_t, air_t, access),
        )

    # Seed inventories and deployments
    cursor = conn.cursor()
    cursor.execute("SELECT actor_id, family, MAX(initial_ammo_stock) FROM military_platforms GROUP BY actor_id, family")
    platform_families = cursor.fetchall()
    for act_id, family, initial_ammo_stock in platform_families:
        stock = initial_ammo_stock if initial_ammo_stock is not None else 100
        conn.execute(
            """
            INSERT OR REPLACE INTO platform_inventories (
                actor_id, platform_family, stock_current, stock_max,
                burn_rate_standby, burn_rate_active, resupply_rate_turn
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (act_id, family, stock, stock, 0.05, 2.5, 4),
        )

    cursor.execute("SELECT platform_id, actor_id, quantity_max, quantity_min FROM military_platforms")
    platforms_list = cursor.fetchall()
    for platform_id, act_id, q_max, q_min in platforms_list:
        qty = q_max if q_max is not None else (q_min if q_min is not None else 10)
        act_upper = act_id.upper()
        if act_upper == "IR":
            default_theater = "persian_gulf"
        elif act_upper in {"HOUTHIS", "US"}:
            default_theater = "red_sea"
        elif act_upper in {"IL", "HEZBOLLAH"}:
            default_theater = "levant_corridor"
        elif act_upper in {"SA", "AE", "GCC"}:
            default_theater = "strait_of_hormuz"
        else:
            if act_upper in {"CN", "RU", "KP"}:
                default_theater = "strait_of_hormuz"
            else:
                default_theater = "red_sea"

        deployment_id = f"DEP_{platform_id}_{default_theater}"
        conn.execute(
            """
            INSERT OR REPLACE INTO actor_deployments (
                deployment_id, actor_id, platform_id, theater_id,
                quantity_deployed, current_status, destination_theater, remaining_transit_turns
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (deployment_id, act_id, platform_id, default_theater, qty, "deployed", None, None),
        )

    # Seed V6 tables
    # 1. Seed geographic_bases
    for row in world_seed.get("geographic_bases", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO geographic_bases (
                base_id, theater_id, display_name, base_type,
                max_capacity_units, port_throughput_tons_day,
                active_defense_level, radar_coverage_range_km
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["base_id"],
                row["theater_id"],
                row["display_name"],
                row["base_type"],
                int(row["max_capacity_units"]),
                int(row.get("port_throughput_tons_day", 0)),
                float(row.get("active_defense_level", 0.8)),
                int(row["radar_coverage_range_km"])
            ),
        )

    # 2. Seed platform_munitions
    for row in military_seed.get("platform_munitions", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO platform_munitions (
                munitions_id, display_name, munitions_family,
                unit_cost_usd_k, range_class_km, warhead_type,
                penetration_factor, guidance_system
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["munitions_id"],
                row["display_name"],
                row["munitions_family"],
                int(row["unit_cost_usd_k"]),
                int(row["range_class_km"]),
                row["warhead_type"],
                float(row["penetration_factor"]),
                row["guidance_system"]
            ),
        )

    # 3. Seed base_inventories based on base location / ownership
    cursor = conn.cursor()
    cursor.execute("SELECT base_id FROM geographic_bases")
    bases = [r["base_id"] for r in cursor.fetchall()]
    for b_id in bases:
        # Determine target actor based on base_id naming conventions
        b_lower = b_id.lower()
        if "guam" in b_lower or "kadena" in b_lower or "yokosuka" in b_lower or "manama" in b_lower or "udeid" in b_lower:
            target_actors = ["US"]
        elif "tsoying" in b_lower or "chingchuangang" in b_lower:
            target_actors = ["TW"]
        elif "sanya" in b_lower or "zhanjiang" in b_lower:
            target_actors = ["CN"]
        elif "bandar" in b_lower:
            target_actors = ["IR"]
        elif "palmachim" in b_lower:
            target_actors = ["IL"]
        elif "hodeidah" in b_lower:
            target_actors = ["HOUTHIS"]
        else:
            target_actors = ["US"]

        for act in target_actors:
            cursor.execute("SELECT DISTINCT family, initial_ammo_stock FROM military_platforms WHERE actor_id = ?", (act,))
            families = cursor.fetchall()
            for fam, init_stock in families:
                stock = init_stock if init_stock is not None else 1000
                # Find matching munitions in platform_munitions
                cursor.execute("SELECT munitions_id FROM platform_munitions WHERE munitions_family = ?", (fam,))
                mun_rows = cursor.fetchall()
                for mun_r in mun_rows:
                    mun_id = mun_r["munitions_id"]
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO base_inventories (
                            base_id, munitions_id, stock_current, stock_max,
                            burn_rate_standby, burn_rate_active, resupply_rate_turn
                        ) VALUES (?, ?, ?, ?, 0.005, 2.0, 4)
                        """,
                        (b_id, mun_id, stock, stock),
                    )

    # 4. Seed logistics_lanes
    for row in world_seed.get("logistics_lanes", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO logistics_lanes (
                lane_id, from_base, to_base, transit_turns,
                transit_type, capacity_limit_tons_turn, interdiction_risk
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["lane_id"],
                row["from_base"],
                row["to_base"],
                int(row["transit_turns"]),
                row["transit_type"],
                int(row["capacity_limit_tons_turn"]),
                float(row.get("interdiction_risk", 0.0))
            ),
        )

    # 5. Seed actor_redlines
    for row in world_seed.get("actor_redlines", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO actor_redlines (
                redline_id, actor_id, trigger_condition,
                escalation_doctrine_json, pmesii_impact_json, is_triggered
            ) VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                row["redline_id"],
                row["actor_id"],
                row["trigger_condition"],
                _json(row["escalation_doctrine"]),
                _json(row["pmesii_impact"])
            ),
        )


def _seed_compat_tables(conn: sqlite3.Connection, actor_config: dict[str, Any]) -> None:
    now = now_iso()
    actors = [
        ("Blue", "Blue Coalition Slot", "scenario_slot", ["stabilize assigned role actors"], ["avoid ungrounded escalation"], "controller-assigned coalition slot", 0.54),
        ("Red", "Red Coercive Slot", "scenario_slot", ["pressure assigned role actors"], ["avoid unsupported overreach"], "controller-assigned coercive slot", 0.72),
        ("White", "White Control Cell", "controller", ["enforce rules"], ["do not create actor COA"], "skeptical adjudicator", 0.25),
        ("Intel", "Intel Fusion Cell", "observer", ["compress evidence"], ["preserve provenance"], "source-vetting analyst", 0.35),
    ]
    for actor in actors:
        conn.execute(
            "INSERT OR REPLACE INTO actors(actor_id,display_name,faction,goals_json,redlines_json,command_style,risk_tolerance,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (actor[0], actor[1], actor[2], _json(actor[3]), _json(actor[4]), actor[5], actor[6], now),
        )
    definitions = {
        "P": "政治合法性、決策穩定、聯盟承諾與國內政治成本。",
        "M": "軍事部署、戰備、交火風險、指管韌性與威懾可信度。",
        "E": "制裁、能源、貿易、金融壓力與供應鏈衝擊。",
        "S": "社會凝聚、族群/宗教張力、輿論承受度與民生壓力。",
        "I": "資訊作戰、敘事競爭、網路行動、欺敵與反欺敵。",
        "Infra": "港口、航道、能源、通訊、交通與關鍵基礎設施韌性。",
    }
    for idx, dimension in enumerate(DIMENSIONS):
        conn.execute(
            "INSERT OR REPLACE INTO pmesii_indicators(dimension,definition,normal_low,normal_high,stress_interpretation) VALUES(?,?,?,?,?)",
            (dimension, definitions[dimension], 45.0 + idx, 68.0 + idx, "高於正常區間代表該維壓力升高，需尋找來源支持與反證。"),
        )
        for actor_id in ["Blue", "Red"]:
            priorities = actor_config.get(f"{actor_id.lower()}_priorities", {})
            priority = float(priorities.get(dimension, 0.6))
            posture = "stabilize" if actor_id == "Blue" else "pressure"
            conn.execute(
                "INSERT OR REPLACE INTO actor_doctrine(actor_id,dimension,preferred_actions_json,taboos_json,escalation_logic,deescalation_conditions_json) VALUES(?,?,?,?,?,?)",
                (actor_id, dimension, _json([f"{posture}_{dimension.lower()}_initiative", "seek evidence-grounded option"]), _json(["precise casualty claims without evidence", "actions outside mission geography"]), f"Priority {priority:.2f}; escalate only when pressure, capability, and source support align.", _json(["credible mediation signal", "two-turn evidence weakening", "controller violation flag"])),
            )
    for row in [
        ("C_PUBLIC_ONLY", None, "source_policy", "Use public or provided sources only; mark unsupported claims.", "high"),
        ("C_STRATEGIC_LEVEL", None, "fidelity", "Keep outputs at strategic or semi-tactical level; avoid false precision.", "high"),
        ("C_JSON_CONTRACT", None, "format", "Actor responses must satisfy the JSON contract.", "high"),
        ("C_CAPABILITY_EXISTS", None, "capability", "Actor actions must map to seeded actor capability or be flagged.", "high"),
        ("C_WHITE_DISSENT", "White", "adjudication", "White must state at least one dissent or uncertainty item.", "medium"),
    ]:
        conn.execute("INSERT OR REPLACE INTO constraints(constraint_id,actor_id,category,rule_text,severity) VALUES(?,?,?,?,?)", row)
    for row in [
        ("Blue", "controller_slot", "use selected Blue world-actor capabilities", "must cite concrete actor capability rules", 0.8),
        ("Red", "controller_slot", "use selected Red world-actor capabilities", "must cite concrete actor capability rules", 0.8),
        ("White", "adjudication", "rule and probability review", "cannot create actor COA", 0.9),
        ("Intel", "analysis", "source fusion and gap flagging", "limited by collection plan and source provenance", 0.82),
    ]:
        conn.execute("INSERT OR REPLACE INTO capabilities(actor_id,domain,capability,limits,confidence) VALUES(?,?,?,?,?)", row)


def _seed_collection_sources(conn: sqlite3.Connection, collection_plan: dict[str, Any]) -> None:
    for idx, source in enumerate(collection_plan.get("sources", [])[:24], start=1):
        source_name = str(source.get("name") or f"source_{idx}")
        tier = str(source.get("tier", "public")).lower()
        prior = {"official": 0.86, "public": 0.72, "mixed": 0.62, "social": 0.45}.get(tier, 0.6)
        conn.execute(
            "INSERT OR REPLACE INTO sources(source_id,source_name,independence_group,reliability_prior,update_frequency,citation_policy) VALUES(?,?,?,?,?,?)",
            (f"SRC{idx:03d}", source_name, str(source.get("independence_group", "unknown")), prior, str(source.get("update_frequency", "daily")), "cite source_name and preserve capture metadata"),
        )


def _seed_reference_facts(conn: sqlite3.Connection, mission: dict[str, Any], scenario: dict[str, Any], references_dir: str | Path | None) -> None:
    for row in [
        ("MISSION_TOPIC", "mission", str(mission.get("topic", "")), None, 0.9),
        ("MISSION_GEO", "mission", str(mission.get("geo_scope", "")), None, 0.85),
        ("SCENARIO_BASELINE", "scenario", str(scenario.get("baseline", "")), None, 0.75),
    ]:
        conn.execute("INSERT OR REPLACE INTO scenario_facts(fact_id,scope,fact_text,source_id,confidence) VALUES(?,?,?,?,?)", row)
    if references_dir:
        for path in sorted(Path(references_dir).glob("*.md")):
            text = path.read_text(encoding="utf-8")[:1400]
            conn.execute(
                "INSERT OR REPLACE INTO scenario_facts(fact_id,scope,fact_text,source_id,confidence) VALUES(?,?,?,?,?)",
                (f"REF_{path.stem.upper().replace('-', '_')}", "reference", f"{path.name}: {text}", None, 0.7),
            )


def _write_coverage_diagnostics(conn: sqlite3.Connection) -> None:
    rows = _fetch_all(conn, "SELECT actor_id FROM world_actors ORDER BY actor_id")
    missing_metrics = []
    missing_caps = []
    for row in rows:
        actor_id = row["actor_id"]
        metric_count = conn.execute("SELECT COUNT(*) AS n FROM actor_pmesii_metrics WHERE actor_id=?", (actor_id,)).fetchone()["n"]
        cap_count = conn.execute("SELECT COUNT(*) AS n FROM capability_rules WHERE actor_id=?", (actor_id,)).fetchone()["n"]
        if metric_count == 0:
            missing_metrics.append(actor_id)
        if cap_count == 0:
            missing_caps.append(actor_id)
    status = "warn" if missing_metrics or missing_caps else "pass"
    conn.execute(
        "INSERT OR REPLACE INTO quality_diagnostics(diagnostic_id,diagnostic_type,subject,status,details_json,created_at) VALUES(?,?,?,?,?,?)",
        ("coverage_world_actors", "coverage", "world_actors", status, _json({"missing_metrics": missing_metrics, "missing_capabilities": missing_caps}), now_iso()),
    )


def seed_database(
    db_path: str | Path,
    mission: dict[str, Any],
    scenario: dict[str, Any],
    actor_config: dict[str, Any] | None = None,
    collection_plan: dict[str, Any] | None = None,
    references_dir: str | Path | None = None,
    world_seed_dir: str | Path | None = None,
) -> dict[str, Any]:
    migrate(db_path)
    actor_config = actor_config or {}
    collection_plan = collection_plan or {}
    world_seed, military_seed = load_world_seed(world_seed_dir)
    with connect(db_path) as conn:
        _seed_compat_tables(conn, actor_config)
        _seed_collection_sources(conn, collection_plan)
        _seed_reference_facts(conn, mission, scenario, references_dir)
        _seed_world_tables(conn, mission, scenario, world_seed, military_seed)
        _write_coverage_diagnostics(conn)
    return manifest(db_path)


def _role_primary_actor(conn: sqlite3.Connection, role: str) -> str | None:
    row = conn.execute(
        """
        SELECT abr.actor_id FROM actor_bloc_roles abr
        LEFT JOIN world_actors wa ON wa.actor_id=abr.actor_id
        LEFT JOIN (
          SELECT actor_id, COUNT(*) AS platform_count FROM military_platforms GROUP BY actor_id
        ) mp ON mp.actor_id=abr.actor_id
        LEFT JOIN (
          SELECT actor_id, COUNT(*) AS capability_count FROM capability_rules GROUP BY actor_id
        ) cr ON cr.actor_id=abr.actor_id
        WHERE abr.scenario_id='current' AND abr.role=?
        ORDER BY CASE wa.default_bloc_affinity WHEN ? THEN 0 ELSE 1 END,
                 COALESCE(cr.capability_count, 0) DESC,
                 COALESCE(mp.platform_count, 0) DESC,
                 abr.actor_id
        LIMIT 1
        """,
        (role, role),
    ).fetchone()
    return str(row["actor_id"]) if row else None


def _decode_json_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key, value in list(item.items()):
            if key.endswith("_json") and isinstance(value, str):
                item[key[:-5]] = _loads(value, value)
        decoded.append(item)
    return decoded


def _actor_matches(conn: sqlite3.Connection, actor_or_alias: str) -> list[dict[str, Any]]:
    term = actor_or_alias.strip()
    if not term:
        return []
    rows = _fetch_all(
        conn,
        """
        SELECT DISTINCT wa.*, aa.alias AS matched_alias
        FROM world_actors wa
        LEFT JOIN actor_aliases aa ON aa.actor_id=wa.actor_id
        WHERE lower(wa.actor_id)=lower(?)
           OR lower(wa.display_name)=lower(?)
           OR lower(aa.alias)=lower(?)
        ORDER BY CASE
          WHEN lower(wa.actor_id)=lower(?) THEN 0
          WHEN lower(wa.display_name)=lower(?) THEN 1
          ELSE 2
        END, wa.actor_id
        """,
        (term, term, term, term, term),
    )
    return _decode_json_columns(rows)


def resolve_actor_id(
    conn: sqlite3.Connection,
    actor_or_alias: str,
    mission: dict[str, Any] | None = None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    term = actor_or_alias.strip()
    role_names = {"Blue", "Red", "White", "Neutral", "Non-state", "Intel"}
    if term in role_names:
        if mission is None or scenario is None:
            raise ValueError(f"Scenario role '{term}' requires mission and scenario context.")
        actor_id = _role_primary_actor(conn, term)
        if actor_id is None:
            raise ValueError(f"No concrete actor mapped for scenario role: {term}")
        actor = _fetch_all(conn, "SELECT * FROM world_actors WHERE actor_id=?", (actor_id,))
        if not actor:
            raise ValueError(f"Scenario role '{term}' mapped to missing actor: {actor_id}")
        payload = _decode_json_columns(actor)[0]
        payload["scenario_role"] = term
        payload["match_type"] = "scenario_role"
        return payload
    matches = _actor_matches(conn, term)
    if not matches:
        raise ValueError(f"Unknown actor or alias: {actor_or_alias}")
    actor_ids = sorted({row["actor_id"] for row in matches})
    if len(actor_ids) > 1:
        raise ValueError(f"Ambiguous actor or alias '{actor_or_alias}': {', '.join(actor_ids)}")
    payload = matches[0]
    payload["scenario_role"] = None
    payload["match_type"] = "actor_or_alias"
    return payload


def query_actor_search(conn: sqlite3.Connection, keyword: str, max_items: int = 12) -> list[dict[str, Any]]:
    pattern = f"%{keyword.strip()}%"
    rows = _fetch_all(
        conn,
        """
        SELECT DISTINCT wa.*, aa.alias AS matched_alias
        FROM world_actors wa
        LEFT JOIN actor_aliases aa ON aa.actor_id=wa.actor_id
        WHERE lower(wa.actor_id) LIKE lower(?)
           OR lower(wa.display_name) LIKE lower(?)
           OR lower(wa.region) LIKE lower(?)
           OR lower(wa.alignment_tags_json) LIKE lower(?)
           OR lower(aa.alias) LIKE lower(?)
        ORDER BY wa.actor_id
        LIMIT ?
        """,
        (pattern, pattern, pattern, pattern, pattern, max_items * 4),
    )
    merged: dict[str, dict[str, Any]] = {}
    for row in _decode_json_columns(rows):
        actor_id = str(row["actor_id"])
        alias = row.pop("matched_alias", None)
        if actor_id not in merged:
            row["matched_aliases"] = []
            merged[actor_id] = row
        if alias and alias not in merged[actor_id]["matched_aliases"]:
            merged[actor_id]["matched_aliases"].append(alias)
    return list(merged.values())[:max_items]


def query_pmesii(conn: sqlite3.Connection, actor_id: str, dimension: str | None = None, max_items: int = 12) -> list[dict[str, Any]]:
    if dimension:
        return _fetch_all(
            conn,
            """
            SELECT m.*, s.title AS source_title, s.url AS source_url, s.publisher, s.source_tier
            FROM actor_pmesii_metrics m
            LEFT JOIN source_documents s ON s.source_id=m.source_id
            WHERE m.actor_id=? AND m.dimension=?
            ORDER BY m.dimension, m.metric
            LIMIT ?
            """,
            (actor_id, dimension, max_items),
        )
    return _fetch_all(
        conn,
        """
        SELECT m.*, s.title AS source_title, s.url AS source_url, s.publisher, s.source_tier
        FROM actor_pmesii_metrics m
        LEFT JOIN source_documents s ON s.source_id=m.source_id
        WHERE m.actor_id=?
        ORDER BY m.dimension, m.metric
        LIMIT ?
        """,
        (actor_id, max_items),
    )


def query_capabilities(conn: sqlite3.Connection, actor_id: str, domain: str | None = None, max_items: int = 12) -> list[dict[str, Any]]:
    pattern = f"%{domain.strip()}%" if domain else None
    if pattern:
        rows = _fetch_all(
            conn,
            """
            SELECT c.*, s.title AS source_title, s.url AS source_url, s.publisher, s.source_tier
            FROM capability_rules c
            LEFT JOIN source_documents s ON s.source_id=c.source_id
            WHERE c.actor_id=?
              AND (lower(c.definition) LIKE lower(?) OR lower(c.capability_id) LIKE lower(?))
            ORDER BY c.confidence DESC, c.capability_id
            LIMIT ?
            """,
            (actor_id, pattern, pattern, max_items),
        )
    else:
        rows = _fetch_all(
            conn,
            """
            SELECT c.*, s.title AS source_title, s.url AS source_url, s.publisher, s.source_tier
            FROM capability_rules c
            LEFT JOIN source_documents s ON s.source_id=c.source_id
            WHERE c.actor_id=?
            ORDER BY c.confidence DESC, c.capability_id
            LIMIT ?
            """,
            (actor_id, max_items),
        )
    return _decode_json_columns(rows)


def query_platforms(conn: sqlite3.Connection, actor_id: str, domain: str | None = None, max_items: int = 12) -> list[dict[str, Any]]:
    if domain:
        rows = _fetch_all(
            conn,
            """
            SELECT p.*, s.title AS source_title, s.url AS source_url, s.publisher, s.source_tier
            FROM military_platforms p
            LEFT JOIN source_documents s ON s.source_id=p.source_id
            WHERE p.actor_id=? AND lower(p.domain)=lower(?)
            ORDER BY p.confidence DESC, p.platform_id
            LIMIT ?
            """,
            (actor_id, domain, max_items),
        )
    else:
        rows = _fetch_all(
            conn,
            """
            SELECT p.*, s.title AS source_title, s.url AS source_url, s.publisher, s.source_tier
            FROM military_platforms p
            LEFT JOIN source_documents s ON s.source_id=p.source_id
            WHERE p.actor_id=?
            ORDER BY p.confidence DESC, p.platform_id
            LIMIT ?
            """,
            (actor_id, max_items),
        )
    return rows


def query_interactions(conn: sqlite3.Connection, family: str, max_items: int = 12) -> list[dict[str, Any]]:
    pattern = f"%{family.strip()}%"
    return _fetch_all(
        conn,
        """
        SELECT * FROM weapon_interactions
        WHERE lower(attacker_family) LIKE lower(?) OR lower(defender_family) LIKE lower(?)
        ORDER BY interaction_id
        LIMIT ?
        """,
        (pattern, pattern, max_items),
    )


def query_sources(conn: sqlite3.Connection, actor_id: str, max_items: int = 12) -> dict[str, Any]:
    claims = _fetch_all(
        conn,
        """
        SELECT sc.*, sd.title AS source_title, sd.url AS source_url, sd.publisher, sd.source_tier
        FROM source_claims sc
        LEFT JOIN source_documents sd ON sd.source_id=sc.source_id
        WHERE sc.actor_id=? OR sc.actor_id IS NULL
        ORDER BY sc.confidence DESC, sc.claim_id
        LIMIT ?
        """,
        (actor_id, max_items),
    )
    provenance = _fetch_all(
        conn,
        """
        SELECT * FROM field_provenance
        WHERE record_id LIKE ?
           OR record_id IN (SELECT platform_id FROM military_platforms WHERE actor_id=?)
           OR record_id IN (SELECT capability_id FROM capability_rules WHERE actor_id=?)
        ORDER BY table_name, record_id, field_name
        LIMIT ?
        """,
        (f"{actor_id}:%", actor_id, actor_id, max_items),
    )
    source_ids = sorted({row.get("source_id") for row in claims + provenance if row.get("source_id")})
    documents: list[dict[str, Any]] = []
    if source_ids:
        placeholders = ",".join("?" for _ in source_ids)
        documents = _fetch_all(conn, f"SELECT * FROM source_documents WHERE source_id IN ({placeholders}) ORDER BY source_id", tuple(source_ids))
    return {"source_documents": documents, "source_claims": claims, "field_provenance": provenance}


def _world_actor_context(conn: sqlite3.Connection, actor_id: str, max_rows: int) -> dict[str, Any] | None:
    actor = conn.execute("SELECT * FROM world_actors WHERE actor_id=?", (actor_id,)).fetchone()
    if actor is None:
        return None
    platforms = _fetch_all(conn, "SELECT * FROM military_platforms WHERE actor_id=? ORDER BY confidence DESC, platform_id LIMIT ?", (actor_id, max_rows))
    caps = _fetch_all(conn, "SELECT * FROM capability_rules WHERE actor_id=? ORDER BY confidence DESC, capability_id LIMIT ?", (actor_id, max_rows))
    metrics = _fetch_all(conn, "SELECT * FROM actor_pmesii_metrics WHERE actor_id=? ORDER BY dimension, metric", (actor_id,))
    posture = _fetch_all(conn, "SELECT * FROM force_posture WHERE actor_id=? ORDER BY theater", (actor_id,))
    families = sorted({row["family"] for row in platforms})
    interactions = []
    if families:
        placeholders = ",".join("?" for _ in families)
        interactions = _fetch_all(
            conn,
            f"SELECT * FROM weapon_interactions WHERE attacker_family IN ({placeholders}) OR defender_family IN ({placeholders}) ORDER BY interaction_id LIMIT ?",
            tuple(families + families + [max_rows]),
        )
    provenance = _fetch_all(
        conn,
        "SELECT * FROM field_provenance WHERE record_id LIKE ? OR record_id IN (SELECT platform_id FROM military_platforms WHERE actor_id=?) ORDER BY table_name, record_id LIMIT ?",
        (f"{actor_id}:%", actor_id, max_rows),
    )
    actor_deployments = _fetch_all(conn, "SELECT * FROM actor_deployments WHERE actor_id=?", (actor_id,))
    platform_inventories = _fetch_all(conn, "SELECT * FROM platform_inventories WHERE actor_id=?", (actor_id,))
    geographic_theaters = _fetch_all(conn, "SELECT * FROM geographic_theaters")
    theater_connections = _fetch_all(conn, "SELECT * FROM theater_connections")
    return {
        "world_actor": dict(actor),
        "pmesii_metrics": metrics,
        "military_platforms": platforms,
        "capability_rules": caps,
        "force_posture": posture,
        "weapon_interactions": interactions,
        "field_provenance": provenance,
        "actor_deployments": actor_deployments,
        "platform_inventories": platform_inventories,
        "geographic_theaters": geographic_theaters,
        "theater_connections": theater_connections,
    }


def actor_context_pack(
    db_path: str | Path,
    actor_id: str,
    turn_id: int,
    state: dict[str, float],
    decision_questions: list[str] | None = None,
    max_rows: int = 24,
    scenario_role: str | None = None,
) -> dict[str, Any]:
    support_roles = {"Blue", "Red", "White", "Intel"}
    actor_key = actor_id if actor_id in support_roles else actor_id.upper()
    role_key = scenario_role or (actor_key if actor_key in support_roles else "Blue")
    with connect(db_path) as conn:
        actor = conn.execute("SELECT * FROM actors WHERE actor_id=?", (actor_key if actor_key in support_roles else role_key,)).fetchone()
        concrete_actor_id = None
        if actor is None and actor_key not in support_roles:
            concrete_actor_id = actor_key
            actor = conn.execute("SELECT * FROM actors WHERE actor_id=?", ("Blue",)).fetchone()
        if actor is None:
            raise ValueError(f"Unknown actor_id: {actor_id}")
        if actor_key in {"Blue", "Red"} and scenario_role is None:
            concrete_actor_id = _role_primary_actor(conn, actor_key)
        elif actor_key not in {"White", "Intel"}:
            concrete_actor_id = actor_key
        dimensions = sorted(state, key=lambda key: float(state.get(key, 0.0)), reverse=True)
        doctrine_actor = role_key if role_key in {"Blue", "Red"} else "Blue"
        doctrine = _fetch_all(conn, "SELECT * FROM actor_doctrine WHERE actor_id=? ORDER BY dimension", (doctrine_actor,))
        indicators = _fetch_all(conn, f"SELECT * FROM pmesii_indicators WHERE dimension IN ({','.join('?' for _ in dimensions)})", tuple(dimensions))
        capabilities = _fetch_all(conn, "SELECT * FROM capabilities WHERE actor_id=? ORDER BY confidence DESC LIMIT ?", (doctrine_actor, max_rows))
        constraints = _fetch_all(conn, "SELECT * FROM constraints WHERE actor_id IS NULL OR actor_id=? ORDER BY severity DESC, constraint_id LIMIT ?", (doctrine_actor, max_rows))
        sources = _fetch_all(conn, "SELECT * FROM sources ORDER BY reliability_prior DESC LIMIT ?", (max_rows,))
        source_documents = _fetch_all(conn, "SELECT * FROM source_documents ORDER BY reliability_prior DESC LIMIT ?", (max_rows,))
        facts = _fetch_all(conn, "SELECT * FROM scenario_facts ORDER BY confidence DESC LIMIT ?", (max_rows,))
        memory_actor = concrete_actor_id or actor_key
        memory = _fetch_all(conn, "SELECT * FROM turn_memory WHERE actor_id=? ORDER BY turn_id DESC LIMIT ?", (memory_actor, 8))
        role_map = _fetch_all(conn, "SELECT * FROM actor_bloc_roles WHERE scenario_id='current' ORDER BY role, actor_id")
        role_peers = [row["actor_id"] for row in role_map if row.get("role") == role_key and row.get("actor_id") != concrete_actor_id]
        alliance_peers = [row["actor_id"] for row in role_map if row.get("role") == role_key]
        opposing_role = "Red" if role_key == "Blue" else "Blue" if role_key == "Red" else None
        opposing_actors = [row["actor_id"] for row in role_map if opposing_role and row.get("role") == opposing_role]
        neutral_actors = [row["actor_id"] for row in role_map if row.get("role") == "Neutral"]
        world_context = _world_actor_context(conn, concrete_actor_id, max_rows) if concrete_actor_id else None
    return {
        "schema_version": SCHEMA_VERSION,
        "actor": dict(actor),
        "scenario_role": role_key,
        "concrete_actor_id": concrete_actor_id,
        "concrete_actor_context": world_context,
        "scenario_role_map": role_map,
        "role_peers": role_peers,
        "alliance_peers": alliance_peers,
        "opposing_actors": opposing_actors,
        "neutral_actors": neutral_actors,
        "turn_id": turn_id,
        "state": state,
        "decision_questions": decision_questions or [],
        "doctrine": doctrine,
        "pmesii_indicators": indicators,
        "capabilities": capabilities,
        "constraints": constraints,
        "sources": sources,
        "source_documents": source_documents,
        "scenario_facts": facts,
        "recent_turn_memory": memory,
    }


def record_turn_memory(
    db_path: str | Path,
    run_id: str,
    turn_id: int,
    actor_id: str,
    decision: dict[str, Any],
    state_delta: dict[str, Any] | list[Any],
    controller_rationale: str,
    violations: list[dict[str, Any]],
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO turn_memory(run_id,turn_id,actor_id,decision_json,state_delta_json,controller_rationale,violations_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (run_id, turn_id, actor_id, _json(decision), _json(state_delta), controller_rationale, _json(violations), now_iso()),
        )


def manifest(db_path: str | Path) -> dict[str, Any]:
    target = Path(db_path)
    with connect(target) as conn:
        tables = {}
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            name = str(row["name"])
            count = conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
            tables[name] = int(count)
        version_row = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        coverage = {
            "world_actor_count": tables.get("world_actors", 0),
            "military_platform_count": tables.get("military_platforms", 0),
            "capability_rule_count": tables.get("capability_rules", 0),
            "source_document_count": tables.get("source_documents", 0),
            "benchmark_case_count": tables.get("benchmark_cases", 0),
            "diagnostics": _fetch_all(conn, "SELECT * FROM quality_diagnostics ORDER BY diagnostic_id"),
        }
    return {
        "db_path": str(target.resolve()),
        "schema_version": int(version_row["value"]) if version_row else SCHEMA_VERSION,
        "tables": tables,
        "coverage": coverage,
        "generated_at": now_iso(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or inspect the V4 wargame knowledge SQLite database.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--mission")
    parser.add_argument("--scenario")
    parser.add_argument("--actor-config")
    parser.add_argument("--collection-plan")
    parser.add_argument("--references-dir")
    parser.add_argument("--world-seed-dir")
    parser.add_argument("--context-actor")
    parser.add_argument("--turn-id", type=int, default=1)
    args = parser.parse_args()
    if args.mission and args.scenario:
        output = seed_database(
            db_path=args.db,
            mission=load_json(args.mission),
            scenario=load_json(args.scenario),
            actor_config=load_json(args.actor_config) if args.actor_config else {},
            collection_plan=load_json(args.collection_plan) if args.collection_plan else {},
            references_dir=args.references_dir,
            world_seed_dir=args.world_seed_dir,
        )
    elif args.context_actor:
        migrate(args.db)
        output = actor_context_pack(args.db, args.context_actor, args.turn_id, {dimension: 50.0 for dimension in DIMENSIONS})
    else:
        migrate(args.db)
        output = manifest(args.db)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
