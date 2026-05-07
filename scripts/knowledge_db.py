from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DIMENSIONS = ["P", "M", "E", "S", "I", "Infra"]
SCHEMA_VERSION = 4


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
              confidence REAL NOT NULL
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
              limits TEXT NOT NULL
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
            "INSERT OR REPLACE INTO weapon_interactions(interaction_id,attacker_family,defender_family,relationship,effect,limits) VALUES(?,?,?,?,?,?)",
            (row["interaction_id"], row["attacker_family"], row["defender_family"], row["relationship"], row["effect"], row["limits"]),
        )
    for row in military_seed.get("platforms", []):
        actor_id = str(row["actor_id"]).upper()
        conn.execute(
            """
            INSERT OR REPLACE INTO military_platforms(platform_id,actor_id,family,model,domain,quantity_min,quantity_max,readiness_band,range_effect_class,role,source_id,confidence)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
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
    return {
        "world_actor": dict(actor),
        "pmesii_metrics": metrics,
        "military_platforms": platforms,
        "capability_rules": caps,
        "force_posture": posture,
        "weapon_interactions": interactions,
        "field_provenance": provenance,
    }


def actor_context_pack(
    db_path: str | Path,
    actor_id: str,
    turn_id: int,
    state: dict[str, float],
    decision_questions: list[str] | None = None,
    max_rows: int = 24,
) -> dict[str, Any]:
    actor_key = actor_id if actor_id in {"Blue", "Red", "White", "Intel"} else actor_id.upper()
    with connect(db_path) as conn:
        actor = conn.execute("SELECT * FROM actors WHERE actor_id=?", (actor_key,)).fetchone()
        concrete_actor_id = None
        if actor is None and actor_key not in {"Blue", "Red", "White", "Intel"}:
            concrete_actor_id = actor_key
            actor = conn.execute("SELECT * FROM actors WHERE actor_id=?", ("Blue",)).fetchone()
        if actor is None:
            raise ValueError(f"Unknown actor_id: {actor_id}")
        if actor_key in {"Blue", "Red"}:
            concrete_actor_id = _role_primary_actor(conn, actor_key)
        elif actor_key not in {"White", "Intel"}:
            concrete_actor_id = actor_key
        dimensions = sorted(state, key=lambda key: float(state.get(key, 0.0)), reverse=True)
        doctrine = _fetch_all(conn, "SELECT * FROM actor_doctrine WHERE actor_id=? ORDER BY dimension", (actor_key if actor_key in {"Blue", "Red"} else "Blue",))
        indicators = _fetch_all(conn, f"SELECT * FROM pmesii_indicators WHERE dimension IN ({','.join('?' for _ in dimensions)})", tuple(dimensions))
        capabilities = _fetch_all(conn, "SELECT * FROM capabilities WHERE actor_id=? ORDER BY confidence DESC LIMIT ?", (actor_key, max_rows))
        constraints = _fetch_all(conn, "SELECT * FROM constraints WHERE actor_id IS NULL OR actor_id=? ORDER BY severity DESC, constraint_id LIMIT ?", (actor_key, max_rows))
        sources = _fetch_all(conn, "SELECT * FROM sources ORDER BY reliability_prior DESC LIMIT ?", (max_rows,))
        source_documents = _fetch_all(conn, "SELECT * FROM source_documents ORDER BY reliability_prior DESC LIMIT ?", (max_rows,))
        facts = _fetch_all(conn, "SELECT * FROM scenario_facts ORDER BY confidence DESC LIMIT ?", (max_rows,))
        memory = _fetch_all(conn, "SELECT * FROM turn_memory WHERE actor_id=? ORDER BY turn_id DESC LIMIT ?", (actor_key, 8))
        role_map = _fetch_all(conn, "SELECT * FROM actor_bloc_roles WHERE scenario_id='current' ORDER BY role, actor_id")
        world_context = _world_actor_context(conn, concrete_actor_id, max_rows) if concrete_actor_id else None
    return {
        "schema_version": SCHEMA_VERSION,
        "actor": dict(actor),
        "concrete_actor_id": concrete_actor_id,
        "concrete_actor_context": world_context,
        "scenario_role_map": role_map,
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
