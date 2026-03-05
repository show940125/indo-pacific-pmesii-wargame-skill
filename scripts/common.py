from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

DIMENSIONS = ["P", "M", "E", "S", "I", "Infra"]
PROBABILITY_BUCKETS = ["極低", "低", "中", "高", "極高"]
CONFIDENCE_LEVELS = ["低", "中", "高"]
REPORT_PROFILES = {"dual_layer", "technical_full", "exec_only"}
ACH_PROFILES = {"full", "mid", "graph"}
TERM_ANNOTATION_PROFILES = {"inline_glossary", "appendix_only", "repeat"}
NARRATIVE_MODES = {"battle_report", "event_cards", "commander_log"}
LENGTH_POLICIES = {"warn", "strict", "autofill"}
LENGTH_COUNTING_MODES = {"cjk_chars", "all_chars", "words"}
BASELINE_MODES = {"public_auto"}
EVENT_GRANULARITIES = {"semi_tactical"}
FIDELITY_GUARDRAILS = {"enabled", "disabled"}
SEMI_TACTICAL_EVENT_TYPES = [
    "military_movement",
    "simulated_engagement",
    "sanction_action",
    "diplomatic_mediation",
    "info_operation",
    "infrastructure_disruption",
]

TERMS_AND_PARAMETERS = [
    {
        "名稱": "PMESII",
        "定義": "政治(P)、軍事(M)、經濟(E)、社會(S)、資訊(I)、基礎設施(Infra)六維狀態框架。",
        "範圍": "每維 0~100",
        "預設值": "50",
        "增減影響方向": "分數越高代表該維壓力/風險越高；需搭配脈絡解讀。",
        "對哪些輸出敏感": "report_exec.md、report_analyst.md、key_judgments.json、turn_timeline.md",
    },
    {
        "名稱": "ACH",
        "定義": "競爭假設分析，逐證據評估多個假設的一致/不一致程度。",
        "範圍": "cell consistency -2..+2；diagnosticity 0..1",
        "預設值": "full",
        "增減影響方向": "診斷性與權重越高，對假設總分影響越大。",
        "對哪些輸出敏感": "ach_detailed.json、ach.json、report_analyst.md、key_judgments.json",
    },
    {
        "名稱": "strict_kj_threshold",
        "定義": "高機率且高信心判斷所需的最小獨立來源群組數。",
        "範圍": ">=2",
        "預設值": "3",
        "增減影響方向": "值越高，品質閘門越嚴格，判斷被退件機率上升。",
        "對哪些輸出敏感": "verify_trace.py、run_campaign.py、quality_gate_errors.json",
    },
    {
        "名稱": "report_profile",
        "定義": "報告輸出深度模式。",
        "範圍": "dual_layer|technical_full|exec_only",
        "預設值": "dual_layer",
        "增減影響方向": "越偏 technical，輸出更長且復盤細節更多。",
        "對哪些輸出敏感": "report_exec.md、report_analyst.md、report.md",
    },
    {
        "名稱": "ach_profile",
        "定義": "ACH 引擎模式。",
        "範圍": "full|mid|graph",
        "預設值": "full",
        "增減影響方向": "full 計算最細，mid/graph 較快但推理可見性下降。",
        "對哪些輸出敏感": "ach_detailed.json、ach.json、report_analyst.md",
    },
    {
        "名稱": "term_annotation",
        "定義": "主文術語註解策略。",
        "範圍": "inline_glossary|appendix_only|repeat",
        "預設值": "inline_glossary",
        "增減影響方向": "inline 提升可讀性；appendix 簡潔但跳轉成本高。",
        "對哪些輸出敏感": "report_exec.md、report_analyst.md、terms_and_parameters.md",
    },
    {
        "名稱": "narrative_mode",
        "定義": "回合敘事呈現模式。",
        "範圍": "battle_report|event_cards|commander_log",
        "預設值": "event_cards",
        "增減影響方向": "event_cards 可視化最強；battle_report 最正式；commander_log 敘事感較重。",
        "對哪些輸出敏感": "report_analyst.md、turn_*_story_cards.json",
    },
    {
        "名稱": "baseline_mode",
        "定義": "行為者基底資料模式，對公開來源自動對比。",
        "範圍": "public_auto",
        "預設值": "public_auto",
        "增減影響方向": "啟用後會產生 baseline 偏離事件與分數，提升推演可比較性。",
        "對哪些輸出敏感": "baseline_deviation_report.json、report_exec.md、report_analyst.md、verify_trace.py",
    },
    {
        "名稱": "event_granularity",
        "定義": "回合事件敘事粒度。",
        "範圍": "semi_tactical",
        "預設值": "semi_tactical",
        "增減影響方向": "粒度越高，事件敘事越具體，但需同時提高防假精度護欄。",
        "對哪些輸出敏感": "turn_*_event_ledger.json、event_timeline.md、report_analyst.md",
    },
    {
        "名稱": "fidelity_guardrail",
        "定義": "半戰術敘事精度護欄，禁止輸出精準戰損數字。",
        "範圍": "enabled|disabled",
        "預設值": "enabled",
        "增減影響方向": "enabled 可降低假精度風險；disabled 可讀性高但可信度風險升高。",
        "對哪些輸出敏感": "turn_*_event_ledger.json、report_exec.md、report_analyst.md",
    },
    {
        "名稱": "length_policy",
        "定義": "報告字數門檻策略。",
        "範圍": "warn|strict|autofill",
        "預設值": "warn",
        "增減影響方向": "strict 可能擋下 run；warn 僅提示；autofill 會自動補寫。",
        "對哪些輸出敏感": "report_metrics.json、quality_gate_warnings.json、verify_trace.py",
    },
    {
        "名稱": "min_chars_exec",
        "定義": "管理層報告最低字數門檻。",
        "範圍": ">=500",
        "預設值": "2000",
        "增減影響方向": "值越高，管理層報告細節密度越高。",
        "對哪些輸出敏感": "report_exec.md、report_metrics.json",
    },
    {
        "名稱": "min_chars_analyst",
        "定義": "分析師報告最低字數門檻。",
        "範圍": ">=1000",
        "預設值": "5000",
        "增減影響方向": "值越高，逐回合與證據解釋篇幅越長。",
        "對哪些輸出敏感": "report_analyst.md、report_metrics.json",
    },
    {
        "名稱": "length_counting",
        "定義": "字數計量方式。",
        "範圍": "cjk_chars|all_chars|words",
        "預設值": "cjk_chars",
        "增減影響方向": "cjk_chars 最能反映繁中內容密度。",
        "對哪些輸出敏感": "report_metrics.json、verify_trace.py",
    },
]

INLINE_TERMS = {
    "PMESII": "PMESII（政治/軍事/經濟/社會/資訊/基礎設施六維框架）",
    "ACH": "ACH（競爭假設分析）",
    "KJ": "KJ（關鍵判斷）",
    "ROE": "ROE（交戰規則）",
    "Blue": "Blue（藍隊）",
    "Red": "Red（紅隊）",
    "White": "White（白隊）",
}


def parse_args(description: str, *arg_specs: tuple[list[str], dict[str, Any]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    for flags, kwargs in arg_specs:
        parser.add_argument(*flags, **kwargs)
    return parser.parse_args()


def load_json(path: str | Path) -> dict[str, Any] | list[Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def stable_hash(data: Any) -> str:
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_rng(seed: int, turn_id: int, salt: str = "") -> random.Random:
    encoded = f"{seed}:{turn_id}:{salt}".encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return random.Random(int(digest[:16], 16))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_required(payload: dict[str, Any], required: list[str], name: str) -> None:
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"{name} missing required fields: {', '.join(missing)}")


def _default_mission_controls(mission: dict[str, Any]) -> dict[str, Any]:
    mission.setdefault("output_lang", "zh-TW")
    mission.setdefault("report_profile", "dual_layer")
    mission.setdefault("ach_profile", "full")
    mission.setdefault("term_annotation", "inline_glossary")
    mission.setdefault("narrative_mode", "event_cards")
    mission.setdefault("baseline_mode", "public_auto")
    mission.setdefault("event_granularity", "semi_tactical")
    mission.setdefault("fidelity_guardrail", "enabled")
    mission.setdefault("length_policy", "warn")
    mission.setdefault("min_chars_exec", 2000)
    mission.setdefault("min_chars_analyst", 5000)
    mission.setdefault("length_counting", "cjk_chars")
    mission.setdefault("strict_kj_threshold", 3)
    mission.setdefault("seed", 20260305)
    return mission


def validate_mission(mission: dict[str, Any]) -> None:
    _ensure_required(
        mission,
        ["topic", "decision_questions", "geo_scope", "time_window", "classification", "run_mode", "success_criteria"],
        "MissionSpec",
    )
    _ensure_required(mission["time_window"], ["start", "end"], "MissionSpec.time_window")
    _default_mission_controls(mission)
    if mission["run_mode"] not in {"quick", "deep", "custom"}:
        raise ValueError("MissionSpec.run_mode must be one of: quick, deep, custom")
    if mission["report_profile"] not in REPORT_PROFILES:
        raise ValueError(f"MissionSpec.report_profile must be one of: {', '.join(sorted(REPORT_PROFILES))}")
    if mission["ach_profile"] not in ACH_PROFILES:
        raise ValueError(f"MissionSpec.ach_profile must be one of: {', '.join(sorted(ACH_PROFILES))}")
    if mission["term_annotation"] not in TERM_ANNOTATION_PROFILES:
        raise ValueError(
            f"MissionSpec.term_annotation must be one of: {', '.join(sorted(TERM_ANNOTATION_PROFILES))}"
        )
    if mission["narrative_mode"] not in NARRATIVE_MODES:
        raise ValueError(f"MissionSpec.narrative_mode must be one of: {', '.join(sorted(NARRATIVE_MODES))}")
    if mission["baseline_mode"] not in BASELINE_MODES:
        raise ValueError(f"MissionSpec.baseline_mode must be one of: {', '.join(sorted(BASELINE_MODES))}")
    if mission["event_granularity"] not in EVENT_GRANULARITIES:
        raise ValueError(f"MissionSpec.event_granularity must be one of: {', '.join(sorted(EVENT_GRANULARITIES))}")
    if mission["fidelity_guardrail"] not in FIDELITY_GUARDRAILS:
        raise ValueError(f"MissionSpec.fidelity_guardrail must be one of: {', '.join(sorted(FIDELITY_GUARDRAILS))}")
    if mission["length_policy"] not in LENGTH_POLICIES:
        raise ValueError(f"MissionSpec.length_policy must be one of: {', '.join(sorted(LENGTH_POLICIES))}")
    if mission["length_counting"] not in LENGTH_COUNTING_MODES:
        raise ValueError(
            f"MissionSpec.length_counting must be one of: {', '.join(sorted(LENGTH_COUNTING_MODES))}"
        )
    if int(mission["min_chars_exec"]) < 500:
        raise ValueError("MissionSpec.min_chars_exec must be >= 500")
    if int(mission["min_chars_analyst"]) < 1000:
        raise ValueError("MissionSpec.min_chars_analyst must be >= 1000")
    if int(mission["strict_kj_threshold"]) < 2:
        raise ValueError("MissionSpec.strict_kj_threshold must be >= 2")


def validate_scenario(scenario: dict[str, Any]) -> None:
    _ensure_required(
        scenario,
        ["baseline", "excursions", "assumption_tree", "termination_conditions", "shock_library"],
        "ScenarioPack",
    )


def get_turn_count(mission: dict[str, Any], override_turns: int | None = None) -> int:
    if override_turns is not None:
        return int(override_turns)
    if mission["run_mode"] == "quick":
        return 8
    if mission["run_mode"] == "deep":
        return 12
    return int(mission.get("turns", 10))


def load_actor_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "blue_priorities": {"P": 0.8, "M": 0.65, "E": 0.7, "S": 0.7, "I": 0.8, "Infra": 0.75},
            "red_priorities": {"P": 0.7, "M": 0.9, "E": 0.65, "S": 0.55, "I": 0.85, "Infra": 0.8},
        }
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Actor config must be a JSON object.")
    return payload


def infer_actor_roster(mission: dict[str, Any]) -> list[dict[str, Any]]:
    topic = str(mission.get("topic", ""))
    if any(token in topic for token in ["美伊", "伊朗", "Iran", "中東", "波斯灣"]):
        return [
            {"actor_id": "Blue", "name": "US_Allied_Coalition", "role": "coalition", "links": "US,GCC,Israel"},
            {"actor_id": "Red", "name": "Iran_Proxy_Network", "role": "coalition", "links": "Iran,proxy_axis"},
        ]
    return [
        {"actor_id": "Blue", "name": "Blue_Coalition", "role": "coalition", "links": "status_quo_partners"},
        {"actor_id": "Red", "name": "Red_Coercive_Coalition", "role": "coalition", "links": "revisionist_network"},
    ]


def ensure_actor_baseline_db(
    db_path: str | Path,
    mission: dict[str, Any],
    collection_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    roster = infer_actor_roster(mission)
    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS actors (actor_id TEXT PRIMARY KEY, name TEXT, role TEXT, links TEXT, updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pmesii_baseline (actor_id TEXT, dimension TEXT, normal_low REAL, normal_high REAL, seasonality TEXT, volatility_band REAL, PRIMARY KEY(actor_id, dimension))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS military_baseline (actor_id TEXT PRIMARY KEY, force_structure TEXT, deployment_regions TEXT, equipment_profile TEXT, mobilization_index REAL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS economic_baseline (actor_id TEXT PRIMARY KEY, sanction_exposure REAL, trade_dependency REAL, energy_vulnerability REAL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS diplomatic_baseline (actor_id TEXT PRIMARY KEY, alliance_network TEXT, channel_activity REAL, mediation_openness REAL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS source_registry (source_name TEXT PRIMARY KEY, independence_group TEXT, update_frequency TEXT, reliability_prior REAL)"
        )

        now = now_iso()
        for row in roster:
            conn.execute(
                "INSERT OR REPLACE INTO actors(actor_id,name,role,links,updated_at) VALUES(?,?,?,?,?)",
                (row["actor_id"], row["name"], row["role"], row["links"], now),
            )
            for dimension in DIMENSIONS:
                if row["actor_id"] == "Blue":
                    low, high, vol = 52.0, 68.0, 7.5
                    if dimension in {"M", "I"}:
                        low, high, vol = 60.0, 74.0, 8.5
                else:
                    low, high, vol = 50.0, 66.0, 8.0
                    if dimension in {"M", "I"}:
                        low, high, vol = 66.0, 82.0, 10.0
                conn.execute(
                    "INSERT OR REPLACE INTO pmesii_baseline(actor_id,dimension,normal_low,normal_high,seasonality,volatility_band) VALUES(?,?,?,?,?,?)",
                    (row["actor_id"], dimension, low, high, "none", vol),
                )
            conn.execute(
                "INSERT OR REPLACE INTO military_baseline(actor_id,force_structure,deployment_regions,equipment_profile,mobilization_index) VALUES(?,?,?,?,?)",
                (
                    row["actor_id"],
                    "combined_arms_task_forces",
                    "gulf;levant;maritime_corridors",
                    "precision_strike+uav+naval_patrol",
                    0.7 if row["actor_id"] == "Blue" else 0.76,
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO economic_baseline(actor_id,sanction_exposure,trade_dependency,energy_vulnerability) VALUES(?,?,?,?)",
                (row["actor_id"], 0.45 if row["actor_id"] == "Blue" else 0.82, 0.58, 0.66),
            )
            conn.execute(
                "INSERT OR REPLACE INTO diplomatic_baseline(actor_id,alliance_network,channel_activity,mediation_openness) VALUES(?,?,?,?)",
                (
                    row["actor_id"],
                    row["links"],
                    0.72 if row["actor_id"] == "Blue" else 0.57,
                    0.61 if row["actor_id"] == "Blue" else 0.49,
                ),
            )

        for source in (collection_plan or {}).get("sources", [])[:12]:
            source_name = str(source.get("name", "")).strip()
            if not source_name:
                continue
            tier = str(source.get("tier", "public")).lower()
            prior = {"official": 0.86, "public": 0.72, "mixed": 0.62, "social": 0.45}.get(tier, 0.6)
            conn.execute(
                "INSERT OR REPLACE INTO source_registry(source_name,independence_group,update_frequency,reliability_prior) VALUES(?,?,?,?)",
                (
                    source_name,
                    str(source.get("independence_group", "unknown")),
                    "daily",
                    prior,
                ),
            )

    return {"db_path": str(target), "actors": [row["actor_id"] for row in roster]}


def _baseline_band(db_path: str | Path, actor_id: str, dimension: str) -> tuple[float, float, float]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT normal_low,normal_high,volatility_band FROM pmesii_baseline WHERE actor_id=? AND dimension=?",
            (actor_id, dimension),
        ).fetchone()
    if not row:
        return (48.0, 66.0, 8.0)
    return float(row[0]), float(row[1]), float(row[2])


def _source_prior(db_path: str | Path, source_name: str) -> float:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT reliability_prior FROM source_registry WHERE source_name=?",
            (source_name,),
        ).fetchone()
    if not row:
        return 0.6
    return float(row[0])


def default_state() -> dict[str, float]:
    return {dimension: 50.0 for dimension in DIMENSIONS}


def clamp_state(state: dict[str, float]) -> dict[str, float]:
    return {name: round(max(0.0, min(100.0, float(value))), 2) for name, value in state.items()}


def merge_initial_state(scenario: dict[str, Any]) -> dict[str, float]:
    merged = default_state()
    for name, value in scenario.get("initial_state", {}).items():
        if name in DIMENSIONS:
            merged[name] = float(value)
    return clamp_state(merged)


def date_from_window(mission: dict[str, Any], turn_id: int) -> str:
    start = datetime.fromisoformat(mission["time_window"]["start"])
    end = datetime.fromisoformat(mission["time_window"]["end"])
    span = max(1, (end - start).days)
    offset = min(span, max(0, turn_id - 1))
    return (start + timedelta(days=offset)).replace(tzinfo=timezone.utc).isoformat()


def _hypothesis_keywords(hypothesis_id: str) -> set[str]:
    mapping = {
        "H1": {"降溫", "對話", "去衝突", "受控", "協調", "緩和"},
        "H2": {"灰色", "施壓", "制裁", "資訊戰", "代理人", "騷擾"},
        "H3": {"升級", "交火", "襲擊", "中斷", "封鎖", "報復", "航運受阻"},
    }
    return mapping.get(hypothesis_id, set())


def _infer_hypotheses(mission: dict[str, Any]) -> list[dict[str, Any]]:
    topic = str(mission.get("topic", ""))
    if any(token in topic for token in ["美伊", "伊朗", "波斯灣", "中東", "Iran"]):
        return [
            {"id": "H1", "statement": "可控競爭：雙方維持有限衝突並避免全面戰爭。"},
            {"id": "H2", "statement": "灰色擴張：代理人、制裁與資訊戰在多戰區持續升壓。"},
            {"id": "H3", "statement": "局部升級：航運與基地攻防觸發連鎖報復。"},
        ]
    return [
        {"id": "H1", "statement": "受控競爭仍是主要路徑。"},
        {"id": "H2", "statement": "灰色地帶壓力跨資訊與軍事面擴張。"},
        {"id": "H3", "statement": "複合衝擊導致局部升級。"},
    ]


def _keyword_consistency(claim: str, hypothesis_id: str) -> int:
    text = claim.lower()
    kws = _hypothesis_keywords(hypothesis_id)
    hit_count = sum(1 for keyword in kws if keyword in text)
    if hit_count == 0:
        return 0
    if hit_count == 1:
        return 1
    return 2


def _cross_hypothesis_penalty(claim: str, hypothesis_id: str) -> int:
    text = claim.lower()
    if hypothesis_id == "H1" and any(token in text for token in ["升級", "交火", "報復", "封鎖", "受阻"]):
        return -2
    if hypothesis_id == "H3" and any(token in text for token in ["降溫", "對話", "受控", "緩和"]):
        return -1
    return 0


def _calc_relevance_to_hypotheses(claim: str, hypotheses: list[dict[str, Any]]) -> list[str]:
    matched: list[str] = []
    for hypothesis in hypotheses:
        hid = hypothesis["id"]
        if _keyword_consistency(claim, hid) > 0:
            matched.append(hid)
    if not matched:
        matched = [hypothesis["id"] for hypothesis in hypotheses]
    return matched

def _build_evidence_item(
    evidence_id: str,
    timestamp: str,
    source: str,
    source_tier: str,
    independence_group: str,
    claim: str,
    credibility_hint: float,
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    tier_weights = {"official": 0.9, "public": 0.75, "mixed": 0.6, "social": 0.45}
    source_weight = tier_weights.get(source_tier.lower(), 0.6)
    reliability = round(max(0.05, min(1.0, (source_weight + credibility_hint) / 2.0)), 2)
    independence = 0.95 if "official" in independence_group else 0.75
    recency = 0.8
    relevance = _calc_relevance_to_hypotheses(claim, hypotheses)
    return {
        "evidence_id": evidence_id,
        "timestamp": timestamp,
        "source": source,
        "source_tier": source_tier,
        "independence_group": independence_group,
        "claim": claim,
        "credibility_hint": round(credibility_hint, 2),
        "reliability_score": reliability,
        "independence_score": round(independence, 2),
        "recency_score": recency,
        "relevance_to_hypotheses": relevance,
    }


def collect_intel(
    mission: dict[str, Any],
    scenario: dict[str, Any],
    turn_id: int,
    collection_plan: dict[str, Any] | None,
    seed: int,
) -> list[dict[str, Any]]:
    rng = make_rng(seed, turn_id, "intel")
    hypotheses = _infer_hypotheses(mission)
    day = date_from_window(mission, turn_id)
    evidence: list[dict[str, Any]] = []

    sources = (collection_plan or {}).get("sources", [])
    for idx, source in enumerate(sources[:6], start=1):
        evidence.append(
            _build_evidence_item(
                evidence_id=f"E{turn_id:02d}S{idx:02d}",
                timestamp=day,
                source=source.get("name", f"source_{idx}"),
                source_tier=source.get("tier", "public"),
                independence_group=source.get("independence_group", f"group_{idx}"),
                claim=source.get("focus", "regional_signal_update"),
                credibility_hint=rng.uniform(0.45, 0.92),
                hypotheses=hypotheses,
            )
        )

    for idx, shock in enumerate(scenario.get("shock_library", []), start=1):
        start_turn = int(shock.get("start_turn", 1))
        end_turn = int(shock.get("end_turn", start_turn))
        if start_turn <= turn_id <= end_turn:
            evidence.append(
                _build_evidence_item(
                    evidence_id=f"E{turn_id:02d}K{idx:02d}",
                    timestamp=day,
                    source=shock.get("source", "scenario-shock"),
                    source_tier=shock.get("source_tier", "mixed"),
                    independence_group=shock.get("independence_group", f"shock_group_{idx}"),
                    claim=shock.get("title", "scenario_shock_event"),
                    credibility_hint=rng.uniform(0.4, 0.88),
                    hypotheses=hypotheses,
                )
            )
    return evidence


def source_vetting(evidence_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vetted: list[dict[str, Any]] = []
    for row in evidence_rows:
        reliability = float(row.get("reliability_score", 0.6))
        independence = float(row.get("independence_score", 0.6))
        recency = float(row.get("recency_score", 0.6))
        credibility = round((reliability * 0.5) + (independence * 0.25) + (recency * 0.25), 3)
        flagged = credibility < 0.48
        vetted.append({**row, "credibility_score": credibility, "flagged": flagged})
    return vetted


def fuse_evidence(vetted_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in vetted_rows if not row.get("flagged", False)]


def generate_subagent_actions(
    side: str,
    turn_id: int,
    state: dict[str, float],
    priorities: dict[str, float],
    seed: int,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for dimension in DIMENSIONS:
        rng = make_rng(seed, turn_id, f"{side}:{dimension}")
        pressure = (state[dimension] - 50.0) / 50.0
        priority = float(priorities.get(dimension, 0.6))
        severity = round(max(0.1, min(0.95, 0.35 + abs(pressure) * 0.4 + priority * 0.2 + rng.uniform(-0.1, 0.1))), 2)
        action = f"{side.lower()}_{dimension.lower()}_initiative"
        if side == "Red" and dimension in {"M", "I"}:
            action = f"{side.lower()}_{dimension.lower()}_pressure"
        if side == "Blue" and dimension in {"P", "Infra"}:
            action = f"{side.lower()}_{dimension.lower()}_stabilize"
        direction = 1.0 if side == "Blue" else -1.0
        if side == "Red" and dimension == "M":
            direction = -1.25
        expected_delta = round(direction * severity * rng.uniform(1.1, 3.2), 2)
        rationale = (
            f"{side} {dimension} 子代理採取 `{action}`，因當前 {dimension} 壓力為 {state[dimension]}，"
            f"優先權 {priority}，預估影響 {expected_delta}。"
        )
        actions.append(
            {
                "subagent": f"{side}-{dimension}",
                "dimension": dimension,
                "action": action,
                "severity": severity,
                "confidence": round(max(0.45, min(0.95, 0.55 + rng.uniform(-0.1, 0.25))), 2),
                "rationale": rationale,
                "expected_delta": expected_delta,
            }
        )
    return actions


def consolidate_coa(side: str, turn_id: int, subactions: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    rng = make_rng(seed, turn_id, f"{side}:coa")
    expected_effect = [{"dimension": row["dimension"], "delta": row["expected_delta"]} for row in subactions]
    return {
        "actor_id": side.lower(),
        "intent": "stabilize_regional_posture" if side == "Blue" else "raise_cost_and_pressure",
        "action_bundle": [{"dimension": row["dimension"], "action": row["action"], "severity": row["severity"]} for row in subactions],
        "subagent_actions": subactions,
        "resource_cost": round(sum(row["severity"] for row in subactions) * rng.uniform(2.4, 4.2), 2),
        "expected_effect": expected_effect,
        "confidence": round(sum(row["confidence"] for row in subactions) / max(1, len(subactions)), 2),
    }


def _infer_locations(mission: dict[str, Any]) -> list[str]:
    geo = str(mission.get("geo_scope", ""))
    if any(token in geo for token in ["中東", "波斯灣", "紅海", "黎巴嫩", "敘利亞"]):
        return ["波斯灣", "紅海", "黎凡特走廊", "伊拉克-敘利亞邊境", "荷姆茲海峽"]
    return ["區域關鍵海空域", "邊境地帶", "能源節點", "關鍵航道"]


def _loss_band_from_risk(risk_value: float) -> str:
    if risk_value >= 80:
        return "高損耗帶"
    if risk_value >= 65:
        return "中損耗帶"
    return "低損耗帶"


def _event_confidence(evidence_rows: list[dict[str, Any]], evidence_ids: list[str]) -> float:
    selected = [row for row in evidence_rows if str(row.get("evidence_id")) in set(evidence_ids)]
    if not selected:
        return 0.58
    score = sum(float(row.get("reliability_score", 0.6)) for row in selected) / len(selected)
    return round(max(0.35, min(0.95, score)), 2)


def _event_probability(base: float, seed: int, turn_id: int, salt: str) -> float:
    rng = make_rng(seed, turn_id, f"event:{salt}")
    return round(max(0.18, min(0.94, base + rng.uniform(-0.12, 0.12))), 2)


def build_turn_event_ledger(
    mission: dict[str, Any],
    scenario: dict[str, Any],
    turn_id: int,
    state_before: dict[str, float],
    state_after: dict[str, float],
    blue_coa: dict[str, Any],
    red_coa: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    seed: int,
) -> list[dict[str, Any]]:
    locations = _infer_locations(mission)
    assumptions = [str(row.get("name", "")) for row in scenario.get("assumption_tree", []) if isinstance(row, dict)]
    if not assumptions:
        assumptions = ["deconfliction_channel_reliability", "supply_chain_resilience"]
    by_type = {
        "military_movement": evidence_rows[:2],
        "simulated_engagement": evidence_rows[1:4],
        "sanction_action": evidence_rows[2:5],
        "diplomatic_mediation": evidence_rows[3:6],
        "info_operation": evidence_rows[:3],
        "infrastructure_disruption": evidence_rows[2:6],
    }
    full_window = mission.get("time_window", {})
    time_window = {
        "start": str(full_window.get("start", now_iso())),
        "end": str(full_window.get("end", now_iso())),
    }
    delta_m = round(float(state_after.get("M", 50.0)) - float(state_before.get("M", 50.0)), 2)
    delta_i = round(float(state_after.get("I", 50.0)) - float(state_before.get("I", 50.0)), 2)
    delta_e = round(float(state_after.get("E", 50.0)) - float(state_before.get("E", 50.0)), 2)
    delta_p = round(float(state_after.get("P", 50.0)) - float(state_before.get("P", 50.0)), 2)
    delta_infra = round(float(state_after.get("Infra", 50.0)) - float(state_before.get("Infra", 50.0)), 2)
    risk_value = (float(state_after.get("M", 50.0)) + float(state_after.get("I", 50.0))) / 2.0
    top_blue = sorted(blue_coa.get("subagent_actions", []), key=lambda row: abs(float(row.get("expected_delta", 0.0))), reverse=True)[:2]
    top_red = sorted(red_coa.get("subagent_actions", []), key=lambda row: abs(float(row.get("expected_delta", 0.0))), reverse=True)[:2]

    def _event_row(
        idx: int,
        event_type: str,
        actor: str,
        target: str,
        location: str,
        detail: str,
        outcome: str,
        loss_band: str,
        pmesii_delta: dict[str, float],
        base_prob: float,
        evidence_slice: list[dict[str, Any]],
        assumption_slice: list[str],
    ) -> dict[str, Any]:
        evidence_ids = [str(row.get("evidence_id", "")) for row in evidence_slice if row.get("evidence_id")]
        return {
            "event_id": f"T{turn_id:02d}EV{idx:02d}",
            "turn_id": turn_id,
            "actor": actor,
            "target": target,
            "location": location,
            "time_window": time_window,
            "event_type": event_type,
            "action_detail": detail,
            "estimated_outcome": outcome,
            "casualty_or_loss_band": loss_band,
            "pmesii_delta": pmesii_delta,
            "probability": _event_probability(base_prob, seed, turn_id, event_type),
            "confidence": _event_confidence(evidence_rows, evidence_ids),
            "evidence_ids": evidence_ids,
            "assumption_links": assumption_slice,
        }

    return [
        _event_row(
            1,
            "military_movement",
            "Blue",
            "Red",
            locations[turn_id % len(locations)],
            f"藍隊執行軍事機動與前沿部署，重點在 {', '.join(row.get('dimension', '') for row in top_blue) or 'M/I'} 維度。",
            "提高前沿壓制與威懾可見度，但也同步拉高反制誘因。",
            "低損耗帶",
            {"M": abs(delta_m), "I": abs(delta_i) * 0.4},
            0.62,
            by_type["military_movement"],
            assumptions[:2],
        ),
        _event_row(
            2,
            "simulated_engagement",
            "Red",
            "Blue",
            locations[(turn_id + 1) % len(locations)],
            "紅隊以代理節點與遠距打擊進行模擬交火測試，目標是壓迫藍隊反應節奏。",
            "交火造成戰術摩擦升高，但仍停留在可控範圍內。",
            _loss_band_from_risk(risk_value),
            {"M": abs(delta_m) * 1.2, "Infra": abs(delta_infra) * 0.7},
            0.68,
            by_type["simulated_engagement"],
            assumptions[1:3],
        ),
        _event_row(
            3,
            "sanction_action",
            "Blue",
            "Red",
            "金融與能源交易節點",
            "藍隊推動新一輪金融/能源制裁組合，壓縮紅隊資源機動空間。",
            "短期削弱紅隊資源彈性，但可能刺激對稱外的反制行為。",
            "中損耗帶",
            {"E": abs(delta_e) * 1.1, "P": abs(delta_p) * 0.6},
            0.59,
            by_type["sanction_action"],
            assumptions[:2],
        ),
        _event_row(
            4,
            "diplomatic_mediation",
            "White",
            "Blue/Red",
            "第三方外交渠道",
            "白隊推動去衝突窗口與第三方斡旋，要求雙方降低誤判風險。",
            "降階訊號可暫時壓住失控鏈，但需要持續配合軍經層面的風險壓制。",
            "低損耗帶",
            {"P": abs(delta_p) * 0.8, "I": abs(delta_i) * 0.5},
            0.54,
            by_type["diplomatic_mediation"],
            assumptions[:2],
        ),
        _event_row(
            5,
            "info_operation",
            "Red",
            "Blue",
            "跨平台資訊域",
            f"紅隊執行資訊操作與敘事污染，焦點在 {', '.join(row.get('dimension', '') for row in top_red) or 'I/P'} 維度。",
            "提升決策雜訊與誤判壓力，迫使藍隊提高驗證成本。",
            "中損耗帶",
            {"I": abs(delta_i) * 1.3, "S": abs(float(state_after.get('S', 50.0)) - float(state_before.get('S', 50.0)))},
            0.66,
            by_type["info_operation"],
            assumptions[1:3],
        ),
        _event_row(
            6,
            "infrastructure_disruption",
            "Red",
            "Regional Nodes",
            locations[(turn_id + 2) % len(locations)],
            "區域運補/港口/通信節點遭受中斷型壓力測試，造成運補節奏不穩。",
            "基礎設施韌性下降會放大後續軍事與經濟風險傳導。",
            "中損耗帶",
            {"Infra": abs(delta_infra) * 1.4, "E": abs(delta_e) * 0.7},
            0.63,
            by_type["infrastructure_disruption"],
            assumptions[:2],
        ),
    ]


def attach_event_metadata_to_evidence(
    evidence_rows: list[dict[str, Any]],
    event_ledger: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_to_events: dict[str, list[dict[str, Any]]] = {}
    for event in event_ledger:
        for evidence_id in event.get("evidence_ids", []):
            evidence_to_events.setdefault(str(evidence_id), []).append(event)
    updated: list[dict[str, Any]] = []
    for row in evidence_rows:
        evidence_id = str(row.get("evidence_id", ""))
        linked = evidence_to_events.get(evidence_id, [])
        diagnosticity_bonus = 0.0
        for event in linked:
            if event.get("event_type") in {"simulated_engagement", "sanction_action", "diplomatic_mediation"}:
                diagnosticity_bonus += 0.2
            else:
                diagnosticity_bonus += 0.08
        updated.append(
            {
                **row,
                "linked_event_ids": [str(event.get("event_id", "")) for event in linked],
                "event_diagnosticity": round(min(1.0, diagnosticity_bonus), 3),
            }
        )
    return updated


def compare_events_with_baseline(
    db_path: str | Path,
    turn_id: int,
    event_ledger: list[dict[str, Any]],
    state_after: dict[str, float],
) -> tuple[list[dict[str, Any]], float]:
    records: list[dict[str, Any]] = []
    weighted_sum = 0.0
    weighted_count = 0
    for event in event_ledger:
        actor = str(event.get("actor", "Blue"))
        if actor not in {"Blue", "Red"}:
            continue
        evidence_ids = [str(value) for value in event.get("evidence_ids", [])]
        source_weight = 0.6
        if evidence_ids:
            priors = []
            for evidence_id in evidence_ids[:3]:
                if evidence_id.startswith(f"E{turn_id:02d}S"):
                    match = re.findall(r"S(\d+)", evidence_id)
                    source_idx = int(match[0]) if match else 1
                    priors.append(_source_prior(db_path, f"source_{source_idx}"))
            source_weight = sum(priors) / len(priors) if priors else 0.6

        for dimension, delta in event.get("pmesii_delta", {}).items():
            if dimension not in DIMENSIONS:
                continue
            low, high, vol = _baseline_band(db_path, actor, dimension)
            observed = float(state_after.get(dimension, 50.0))
            direction = "within_band"
            magnitude = 0.0
            if observed > high:
                direction = "above_baseline"
                magnitude = (observed - high) / max(1.0, vol)
            elif observed < low:
                direction = "below_baseline"
                magnitude = (low - observed) / max(1.0, vol)
            if abs(float(delta)) >= vol * 0.35:
                magnitude += abs(float(delta)) / max(1.0, vol * 2.0)
                if direction == "within_band":
                    direction = "volatility_spike"
            severity = round(min(1.0, max(0.0, magnitude * max(0.5, source_weight))), 3)
            if severity <= 0:
                continue
            weighted_sum += severity
            weighted_count += 1
            records.append(
                {
                    "deviation_id": f"BD-T{turn_id:02d}-{event.get('event_id', '')}-{dimension}",
                    "turn_id": turn_id,
                    "actor": actor,
                    "dimension": dimension,
                    "baseline_low": round(low, 2),
                    "baseline_high": round(high, 2),
                    "observed_value": round(observed, 2),
                    "deviation_direction": direction,
                    "deviation_magnitude": round(magnitude, 3),
                    "severity_score": severity,
                    "source_weight": round(source_weight, 3),
                    "event_id": event.get("event_id", ""),
                    "event_type": event.get("event_type", ""),
                    "evidence_ids": evidence_ids,
                }
            )
    score = round(weighted_sum / weighted_count, 3) if weighted_count else 0.0
    return records, score


def white_legal_roe(blue_coa: dict[str, Any], red_coa: dict[str, Any]) -> list[dict[str, Any]]:
    rule_fires: list[dict[str, Any]] = []
    red_m = [row for row in red_coa.get("action_bundle", []) if row["dimension"] == "M"]
    red_i = [row for row in red_coa.get("action_bundle", []) if row["dimension"] == "I"]
    blue_i = [row for row in blue_coa.get("action_bundle", []) if row["dimension"] == "I"]

    max_red_m = max((row["severity"] for row in red_m), default=0.0)
    max_red_i = max((row["severity"] for row in red_i), default=0.0)
    max_blue_i = max((row["severity"] for row in blue_i), default=0.0)

    if max_red_m >= 0.85:
        rule_fires.append(
            {
                "rule_id": "ROE_ESCALATION_THRESHOLD",
                "trigger": True,
                "value": max_red_m,
                "threshold": 0.85,
                "message": "紅方軍事強度超過局部升級門檻。",
            }
        )
    if max_red_i >= 0.85:
        rule_fires.append(
            {
                "rule_id": "ROE_INFO_PRESSURE_THRESHOLD",
                "trigger": True,
                "value": max_red_i,
                "threshold": 0.85,
                "message": "紅方資訊壓力達高風險區間。",
            }
        )
    if max_blue_i >= 0.9:
        rule_fires.append(
            {
                "rule_id": "INFO_DECONFLICT_REVIEW",
                "trigger": True,
                "value": max_blue_i,
                "threshold": 0.9,
                "message": "藍方資訊行動需進行去衝突審查。",
            }
        )
    if not rule_fires:
        rule_fires.append(
            {
                "rule_id": "ROE_BASELINE_PASS",
                "trigger": True,
                "value": 0.0,
                "threshold": 0.0,
                "message": "本回合未觸發升級型 ROE 規則。",
            }
        )
    return rule_fires

def white_counterdeception(evidence_rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    flags: list[str] = []
    if not evidence_rows:
        findings.append(
            {
                "finding_id": "COUNTERDECEPTION_NO_DATA",
                "severity": "medium",
                "detail": "本回合無有效證據，需提高不確定性權重。",
            }
        )
        flags.append("COUNTERDECEPTION_NO_DATA")
        return flags, findings

    by_group: dict[str, int] = {}
    by_claim: dict[str, int] = {}
    for row in evidence_rows:
        group = str(row.get("independence_group", "unknown"))
        claim = str(row.get("claim", ""))
        by_group[group] = by_group.get(group, 0) + 1
        by_claim[claim] = by_claim.get(claim, 0) + 1

    dominant_ratio = max(by_group.values()) / max(1, len(evidence_rows))
    if dominant_ratio > 0.6:
        flags.append("SOURCE_LOOP_RISK")
        findings.append(
            {
                "finding_id": "SOURCE_LOOP_RISK",
                "severity": "high",
                "detail": f"證據集中於單一獨立來源群組（占比 {round(dominant_ratio, 2)}）。",
            }
        )
    duplicate_ratio = max(by_claim.values()) / max(1, len(evidence_rows))
    if duplicate_ratio > 0.5:
        flags.append("NARRATIVE_CONVERGENCE_ANOMALY")
        findings.append(
            {
                "finding_id": "NARRATIVE_CONVERGENCE_ANOMALY",
                "severity": "medium",
                "detail": f"敘事重複度偏高（占比 {round(duplicate_ratio, 2)}），可能存在同源擴散。",
            }
        )
    if not flags:
        flags.append("COUNTERDECEPTION_CLEAR")
        findings.append(
            {
                "finding_id": "COUNTERDECEPTION_CLEAR",
                "severity": "low",
                "detail": "未偵測到顯著來源循環或異常一致性。",
            }
        )
    return flags, findings


def white_probability_delta(
    state: dict[str, float],
    blue_coa: dict[str, Any],
    red_coa: dict[str, Any],
    turn_id: int,
    seed: int,
) -> tuple[dict[str, float], list[str]]:
    rng = make_rng(seed, turn_id, "white-probability")
    delta = {dimension: 0.0 for dimension in DIMENSIONS}
    notes: list[str] = []
    for row in blue_coa.get("expected_effect", []):
        delta[row["dimension"]] += float(row["delta"])
    for row in red_coa.get("expected_effect", []):
        delta[row["dimension"]] += float(row["delta"])
    for dimension in DIMENSIONS:
        noise = rng.uniform(-1.0, 1.0)
        adjusted = round(delta[dimension] * 0.35 + noise, 2)
        delta[dimension] = adjusted
        notes.append(f"{dimension} 回合裁決增量={adjusted}（含隨機擾動 {round(noise, 2)}）")
    return delta, notes


def adjudicate_turn(
    mission: dict[str, Any],
    turn_packet: dict[str, Any],
    state: dict[str, float],
    blue_coa: dict[str, Any],
    red_coa: dict[str, Any],
    fused_evidence: list[dict[str, Any]],
    seed: int,
    event_ledger: list[dict[str, Any]] | None = None,
    baseline_deviation_score: float = 0.0,
) -> tuple[dict[str, Any], dict[str, float]]:
    turn_id = int(turn_packet["turn_id"])
    rule_fires = white_legal_roe(blue_coa, red_coa)
    if baseline_deviation_score >= 0.65:
        rule_fires.append(
            {
                "rule_id": "BASELINE_DEVIATION_SPIKE",
                "trigger": True,
                "value": round(baseline_deviation_score, 3),
                "threshold": 0.65,
                "message": "基底偏離分數過高，代表事件偏離常態行為帶。",
            }
        )
    counter_flags, counter_findings = white_counterdeception(fused_evidence)
    delta, uncertainty_notes = white_probability_delta(state, blue_coa, red_coa, turn_id, seed)
    next_state = clamp_state({name: state[name] + delta[name] for name in DIMENSIONS})
    event_pressure = 0.0
    for row in event_ledger or []:
        if row.get("event_type") in {"simulated_engagement", "military_movement", "info_operation"}:
            event_pressure += float(row.get("probability", 0.5)) * float(row.get("confidence", 0.5))
    military_pressure = (next_state["M"] + next_state["I"]) / 2.0 + baseline_deviation_score * 8.0 + min(4.0, event_pressure)
    if military_pressure >= 68:
        decision = "localized_escalation_risk"
    elif military_pressure >= 55:
        decision = "gray_zone_competition"
    else:
        decision = "managed_competition"
    rationale = [
        f"M/I 平均壓力為 {round(military_pressure, 2)}，對應決策分類 `{decision}`。",
        f"規則觸發數 {len(rule_fires)}；反欺敵旗標 {', '.join(counter_flags)}；baseline_deviation_score={round(baseline_deviation_score, 3)}。",
    ]
    return (
        {
            "turn_id": turn_id,
            "decision": decision,
            "rule_hits": [row["rule_id"] for row in rule_fires],
            "rule_fires": rule_fires,
            "stochastic_seed": seed,
            "override_note": "",
            "evidence_ids": [row["evidence_id"] for row in fused_evidence[:10]],
            "decision_rationale": rationale,
            "counterdeception_findings": counter_findings,
            "uncertainty_notes": uncertainty_notes,
            "baseline_deviation_score": round(baseline_deviation_score, 3),
            "event_ids": [str(row.get("event_id", "")) for row in (event_ledger or [])[:12]],
        },
        next_state,
    )


def indicator_from_state(state: dict[str, float]) -> dict[str, Any]:
    leading: list[dict[str, Any]] = []
    significant: list[dict[str, Any]] = []
    confirmatory: list[dict[str, Any]] = []
    for dimension in DIMENSIONS:
        value = float(state[dimension])
        status = "觀察"
        if value >= 70:
            status = "高"
        elif value <= 35:
            status = "低"
        row = {
            "name": f"{dimension}_pressure",
            "dimension": dimension,
            "value": round(value, 2),
            "threshold": 60.0,
            "status": status,
        }
        if dimension in {"M", "I"}:
            leading.append(row)
        elif dimension in {"E", "Infra"}:
            significant.append(row)
        else:
            confirmatory.append(row)
    return {"leading": leading, "significant": significant, "confirmatory": confirmatory}


def probability_from_score(score: float) -> str:
    if score < 25:
        return "極低"
    if score < 40:
        return "低"
    if score < 60:
        return "中"
    if score < 75:
        return "高"
    return "極高"


def confidence_from_diagnosticity(diagnosticity: float, evidence_count: int) -> str:
    base = min(1.0, max(0.0, diagnosticity))
    if evidence_count >= 12:
        base += 0.1
    elif evidence_count <= 4:
        base -= 0.1
    if base >= 0.72:
        return "高"
    if base >= 0.45:
        return "中"
    return "低"


def _align_probability_confidence(probability: str, confidence: str) -> str:
    if probability in {"高", "極高"} and confidence == "低":
        return "中"
    if probability in {"低", "極低"} and confidence == "高":
        return "中"
    return confidence


def _calc_ach_cell(evidence: dict[str, Any], hypothesis: dict[str, Any]) -> dict[str, Any]:
    hypothesis_id = hypothesis["id"]
    consistency = _keyword_consistency(str(evidence["claim"]), hypothesis_id)
    consistency += _cross_hypothesis_penalty(str(evidence["claim"]), hypothesis_id)
    consistency = max(-2, min(2, consistency))
    confidence_weight = round(
        float(evidence.get("reliability_score", 0.6)) * 0.55
        + float(evidence.get("independence_score", 0.6)) * 0.25
        + float(evidence.get("recency_score", 0.6)) * 0.2,
        3,
    )
    event_diag = float(evidence.get("event_diagnosticity", 0.0))
    diagnosticity = round(min(1.0, abs(consistency) / 2.0 * confidence_weight + event_diag * 0.35), 3)
    weighted = round(consistency * confidence_weight * (1.0 + event_diag * 0.25), 3)
    relation = "支持"
    if consistency < 0:
        relation = "反對"
    elif consistency == 0:
        relation = "中性"
    reason_text = (
        f"證據 `{evidence['evidence_id']}` 對 {hypothesis_id} 判定為 `{relation}`；"
        f"一致分 {consistency}、權重 {confidence_weight}、事件診斷性加權 {round(event_diag, 3)}、診斷性 {diagnosticity}。"
    )
    return {
        "hypothesis_id": hypothesis_id,
        "evidence_id": evidence["evidence_id"],
        "consistency_score": consistency,
        "confidence_weight": confidence_weight,
        "diagnosticity": diagnosticity,
        "weighted_score": weighted,
        "counterevidence_flag": consistency < 0,
        "reason_text": reason_text,
        "linked_event_ids": list(dict.fromkeys(evidence.get("linked_event_ids", []))),
    }

def _compute_ach_detail(
    mission: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    cell_scores: list[dict[str, Any]] = []
    for evidence in evidence_rows:
        for hypothesis in hypotheses:
            cell_scores.append(_calc_ach_cell(evidence, hypothesis))

    weighted_totals: dict[str, float] = {}
    diagnosticity_totals: dict[str, float] = {}
    support_map: dict[str, list[str]] = {}
    contradict_map: dict[str, list[str]] = {}
    support_event_map: dict[str, list[str]] = {}
    contradict_event_map: dict[str, list[str]] = {}
    support_reasons: dict[str, list[str]] = {}
    oppose_reasons: dict[str, list[str]] = {}
    impact_map: dict[str, list[tuple[str, float]]] = {}
    for hypothesis in hypotheses:
        hid = hypothesis["id"]
        subset = [row for row in cell_scores if row["hypothesis_id"] == hid]
        weighted_totals[hid] = round(sum(row["weighted_score"] for row in subset), 3)
        diagnosticity_totals[hid] = round(sum(row["diagnosticity"] for row in subset), 3)
        support_map[hid] = [row["evidence_id"] for row in subset if row["consistency_score"] > 0]
        contradict_map[hid] = [row["evidence_id"] for row in subset if row["consistency_score"] < 0]
        support_event_map[hid] = list(
            dict.fromkeys(
                event_id
                for row in subset
                if row["consistency_score"] > 0
                for event_id in row.get("linked_event_ids", [])
            )
        )
        contradict_event_map[hid] = list(
            dict.fromkeys(
                event_id
                for row in subset
                if row["consistency_score"] < 0
                for event_id in row.get("linked_event_ids", [])
            )
        )
        support_reasons[hid] = [row["reason_text"] for row in subset if row["consistency_score"] > 0][:5]
        oppose_reasons[hid] = [row["reason_text"] for row in subset if row["consistency_score"] < 0][:5]
        impact_map[hid] = sorted(
            [(row["evidence_id"], abs(row["weighted_score"])) for row in subset],
            key=lambda item: item[1],
            reverse=True,
        )

    ranked = sorted(weighted_totals.items(), key=lambda item: item[1], reverse=True)
    elimination_trace: list[dict[str, Any]] = []
    for rank, (hypothesis_id, score) in enumerate(ranked, start=1):
        elimination_trace.append(
            {
                "rank": rank,
                "hypothesis_id": hypothesis_id,
                "weighted_score": score,
                "status": "primary" if rank == 1 else "alternative",
            }
        )

    sensitivity_runs: list[dict[str, Any]] = []
    for hypothesis_id, baseline_score in weighted_totals.items():
        strongest = impact_map[hypothesis_id][0][0] if impact_map[hypothesis_id] else None
        if strongest is None:
            sensitivity_runs.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "removed_evidence_id": None,
                    "baseline_score": baseline_score,
                    "recomputed_score": baseline_score,
                    "score_shift": 0.0,
                }
            )
            continue
        recomputed = round(
            sum(
                row["weighted_score"]
                for row in cell_scores
                if row["hypothesis_id"] == hypothesis_id and row["evidence_id"] != strongest
            ),
            3,
        )
        sensitivity_runs.append(
            {
                "hypothesis_id": hypothesis_id,
                "removed_evidence_id": strongest,
                "baseline_score": baseline_score,
                "recomputed_score": recomputed,
                "score_shift": round(recomputed - baseline_score, 3),
            }
        )

    summary_rows: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        hid = hypothesis["id"]
        strongest = impact_map[hid][0][0] if impact_map[hid] else None
        flip_condition = f"若移除高影響證據 `{strongest}`，該假設排序可能改變。" if strongest else "資料不足以形成翻盤條件。"
        summary_rows.append(
            {
                "hypothesis_id": hid,
                "statement": hypothesis["statement"],
                "weighted_total": weighted_totals[hid],
                "diagnosticity": diagnosticity_totals[hid],
                "supporting_evidence_ids": support_map[hid],
                "contradicting_evidence_ids": contradict_map[hid],
                "supporting_event_ids": support_event_map[hid],
                "contradicting_event_ids": contradict_event_map[hid],
                "why_support": support_reasons[hid] or ["尚無強支持證據，偏中性。"],
                "why_oppose": oppose_reasons[hid] or ["尚無強反對證據。"],
                "most_sensitive_evidence": strongest,
                "flip_condition": flip_condition,
            }
        )

    return {
        "version": "2.0",
        "mission_topic": mission.get("topic", ""),
        "hypotheses": hypotheses,
        "evidence_rows": evidence_rows,
        "cell_scores": cell_scores,
        "diagnosticity": diagnosticity_totals,
        "weighted_totals": weighted_totals,
        "sensitivity_runs": sensitivity_runs,
        "elimination_trace": elimination_trace,
        "hypothesis_summaries": summary_rows,
    }


def _ach_summary_from_detail(ach_detail: dict[str, Any]) -> dict[str, Any]:
    hypotheses = ach_detail.get("hypotheses", [])
    matrix_rows = []
    for summary in ach_detail.get("hypothesis_summaries", []):
        matrix_rows.append(
            {
                "claim": summary["statement"],
                "scores": {summary["hypothesis_id"]: summary["weighted_total"]},
            }
        )
    return {"hypotheses": hypotheses, "matrix": matrix_rows}


def build_ach_matrix(
    key_judgments: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]] | None = None,
    evidence_rows: list[dict[str, Any]] | None = None,
    mission: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mission_payload = mission or {"topic": "generic"}
    selected_hypotheses = hypotheses or _infer_hypotheses(mission_payload)
    if evidence_rows is None:
        synthetic: list[dict[str, Any]] = []
        for idx, judgment in enumerate(key_judgments, start=1):
            synthetic.append(
                _build_evidence_item(
                    evidence_id=f"SYN{idx:02d}",
                    timestamp=now_iso(),
                    source="synthetic-kj",
                    source_tier="mixed",
                    independence_group=f"syn_group_{idx}",
                    claim=judgment.get("claim", "synthetic_claim"),
                    credibility_hint=0.65,
                    hypotheses=selected_hypotheses,
                )
            )
        evidence_rows = synthetic
    return _compute_ach_detail(mission_payload, evidence_rows, selected_hypotheses)


def _probability_from_weighted_total(total: float) -> str:
    scaled = 50 + total * 12
    return probability_from_score(scaled)


def _pick_diverse_evidence_ids(
    evidence_rows: list[dict[str, Any]],
    preferred_ids: list[str],
    min_count: int,
    exclude_ids: set[str] | None = None,
) -> list[str]:
    evidence_by_id = {row["evidence_id"]: row for row in evidence_rows}
    ordered_candidates = list(dict.fromkeys(preferred_ids))
    for row in evidence_rows:
        evidence_id = str(row["evidence_id"])
        if evidence_id not in ordered_candidates:
            ordered_candidates.append(evidence_id)

    excluded = exclude_ids or set()
    selected: list[str] = []
    selected_groups: set[str] = set()

    # Pass 1: prioritize evidence that increases independence-group diversity.
    for evidence_id in ordered_candidates:
        if evidence_id in excluded or evidence_id not in evidence_by_id or evidence_id in selected:
            continue
        group = str(evidence_by_id[evidence_id].get("independence_group", "unknown"))
        if group in selected_groups:
            continue
        selected.append(evidence_id)
        selected_groups.add(group)
        if len(selected) >= min_count:
            return selected

    # Pass 2: fill remaining quota even if group repeats.
    for evidence_id in ordered_candidates:
        if evidence_id in excluded or evidence_id not in evidence_by_id or evidence_id in selected:
            continue
        selected.append(evidence_id)
        if len(selected) >= min_count:
            return selected

    return selected


def _index_events(event_rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_id = {str(row.get("event_id", "")): row for row in event_rows if row.get("event_id")}
    by_evidence: dict[str, list[dict[str, Any]]] = {}
    for row in event_rows:
        for evidence_id in row.get("evidence_ids", []):
            by_evidence.setdefault(str(evidence_id), []).append(row)
    return by_id, by_evidence


def _event_chain_from_ids(event_by_id: dict[str, dict[str, Any]], event_ids: list[str]) -> list[str]:
    chain: list[str] = []
    for event_id in event_ids:
        row = event_by_id.get(str(event_id))
        if not row:
            continue
        chain.append(
            f"{event_id}:{row.get('event_type','')}->{row.get('estimated_outcome','')}"
        )
    return chain


def _pick_event_ids(
    preferred: list[str],
    fallback_events: list[dict[str, Any]],
    required_types: set[str] | None = None,
    min_count: int = 1,
) -> list[str]:
    selected: list[str] = []
    for event_id in preferred:
        if event_id and event_id not in selected:
            selected.append(event_id)
    if required_types:
        have_types = {
            str(row.get("event_type", ""))
            for row in fallback_events
            if str(row.get("event_id", "")) in selected
        }
        if not have_types.intersection(required_types):
            for row in fallback_events:
                event_id = str(row.get("event_id", ""))
                if not event_id or event_id in selected:
                    continue
                if str(row.get("event_type", "")) in required_types:
                    selected.append(event_id)
                    break
    if len(selected) < min_count:
        for row in fallback_events:
            event_id = str(row.get("event_id", ""))
            if event_id and event_id not in selected:
                selected.append(event_id)
                if len(selected) >= min_count:
                    break
    return selected


def derive_key_judgments(
    mission: dict[str, Any],
    state: dict[str, float],
    indicators: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    ach_result: dict[str, Any] | None = None,
    event_rows: list[dict[str, Any]] | None = None,
    baseline_deviation_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    ach_detail = ach_result or build_ach_matrix([], evidence_rows=evidence_rows, mission=mission)
    summaries = ach_detail.get("hypothesis_summaries", [])
    if not summaries:
        return []
    sorted_rows = sorted(summaries, key=lambda row: row.get("weighted_total", 0.0), reverse=True)
    key_judgments: list[dict[str, Any]] = []
    strict_threshold = max(2, int(mission.get("strict_kj_threshold", 3)))
    all_evidence_ids = [str(row["evidence_id"]) for row in evidence_rows]
    event_rows = event_rows or []
    baseline_deviation_rows = baseline_deviation_rows or []
    event_by_id, events_by_evidence = _index_events(event_rows)
    required_types = {"simulated_engagement", "sanction_action", "diplomatic_mediation"}
    for summary in sorted_rows[:3]:
        probability = _probability_from_weighted_total(float(summary["weighted_total"]))
        confidence = confidence_from_diagnosticity(float(summary["diagnosticity"]), len(evidence_rows))
        confidence = _align_probability_confidence(probability, confidence)
        supporting = list(dict.fromkeys(summary.get("supporting_evidence_ids", [])))
        contradicting = list(dict.fromkeys(summary.get("contradicting_evidence_ids", [])))

        supporting = _pick_diverse_evidence_ids(
            evidence_rows=evidence_rows,
            preferred_ids=[str(evidence_id) for evidence_id in supporting],
            min_count=strict_threshold,
        )
        if not contradicting:
            contradicting = [evidence_id for evidence_id in all_evidence_ids if evidence_id not in supporting]
        contradicting = _pick_diverse_evidence_ids(
            evidence_rows=evidence_rows,
            preferred_ids=[str(evidence_id) for evidence_id in contradicting],
            min_count=1,
            exclude_ids=set(),
        )
        evidence_ids = _pick_diverse_evidence_ids(
            evidence_rows=evidence_rows,
            preferred_ids=supporting + contradicting,
            min_count=2,
        )

        support_events_candidates = [
            event
            for evidence_id in supporting
            for event in events_by_evidence.get(str(evidence_id), [])
        ]
        contradict_events_candidates = [
            event
            for evidence_id in contradicting
            for event in events_by_evidence.get(str(evidence_id), [])
        ]
        support_event_ids = _pick_event_ids(
            preferred=[str(event.get("event_id", "")) for event in support_events_candidates],
            fallback_events=event_rows,
            required_types=required_types,
            min_count=1,
        )
        contradict_event_ids = _pick_event_ids(
            preferred=[str(event.get("event_id", "")) for event in contradict_events_candidates],
            fallback_events=[row for row in event_rows if str(row.get("event_id", "")) not in set(support_event_ids)],
            required_types=required_types,
            min_count=1,
        )

        baseline_event_ids = list(
            dict.fromkeys(
                row.get("event_id", "")
                for row in baseline_deviation_rows
                if any(eid in row.get("evidence_ids", []) for eid in supporting)
            )
        )
        if not baseline_event_ids and baseline_deviation_rows:
            baseline_event_ids = [str(baseline_deviation_rows[0].get("event_id", ""))]
        baseline_event_ids = [event_id for event_id in baseline_event_ids if event_id]

        facts = [
            f"M 指標 {state['M']}",
            f"I 指標 {state['I']}",
            f"P 指標 {state['P']}",
            f"support_event_ids={','.join(support_event_ids) if support_event_ids else '無'}",
        ]
        inferences = [summary["why_support"][0] if summary["why_support"] else "支持訊號有限，仍需持續追蹤。"]
        counterevidence = [summary["why_oppose"][0] if summary["why_oppose"] else "主要反證訊號尚不強。"]
        key_judgments.append(
            {
                "claim": summary["statement"],
                "facts": facts,
                "inferences": inferences,
                "probability_range": probability,
                "confidence_level": confidence,
                "counterevidence": counterevidence,
                "assumption_breakpoints": [summary.get("flip_condition", "尚未形成明確翻盤條件。")],
                "evidence_ids": evidence_ids[:6],
                "supporting_evidence_ids": supporting[:6],
                "contradicting_evidence_ids": contradicting[:6],
                "supporting_event_ids": support_event_ids[:6],
                "contradicting_event_ids": contradict_event_ids[:6],
                "baseline_deviation_event_ids": baseline_event_ids[:4],
                "supporting_event_chain": _event_chain_from_ids(event_by_id, support_event_ids[:4]),
                "contradicting_event_chain": _event_chain_from_ids(event_by_id, contradict_event_ids[:4]),
            }
        )
    return key_judgments


def run_sensitivity(
    mission: dict[str, Any],
    scenario: dict[str, Any],
    base_state: dict[str, float],
    base_key_judgments: list[dict[str, Any]],
    seed: int,
) -> dict[str, Any]:
    assumptions = scenario.get("assumption_tree", [])
    outcomes = []
    for idx, assumption in enumerate(assumptions[:8], start=1):
        rng = make_rng(seed, idx, "sensitivity")
        factor = float(assumption.get("stress_factor", 1.0))
        perturbed: dict[str, float] = {}
        for dimension in DIMENSIONS:
            direction = rng.choice([-1.0, 1.0])
            perturb = direction * rng.uniform(0.3, 1.2) * factor
            perturbed[dimension] = clamp_state({dimension: base_state[dimension] + perturb})[dimension]
        escalation = (perturbed["M"] + perturbed["I"]) / 2.0
        outcomes.append(
            {
                "assumption": assumption.get("name", f"A{idx}"),
                "stress_factor": factor,
                "escalation_score": round(escalation, 2),
                "probability_range": probability_from_score(escalation),
                "breakpoint_triggered": escalation >= 70 or escalation <= 30,
            }
        )
    return {
        "mission_topic": mission.get("topic", ""),
        "base_probabilities": [row["probability_range"] for row in base_key_judgments],
        "results": outcomes,
        "summary": {
            "high_risk_cases": sum(1 for row in outcomes if row["probability_range"] in {"高", "極高"}),
            "breakpoint_cases": sum(1 for row in outcomes if row["breakpoint_triggered"]),
        },
    }

def _annotate_terms(text: str, profile: str) -> str:
    if profile == "appendix_only":
        return text
    annotated = text
    for raw, mapped in INLINE_TERMS.items():
        if mapped in annotated or f"{raw}（" in annotated:
            continue
        if raw in annotated:
            annotated = annotated.replace(raw, mapped, 1)
    return annotated


def count_text_units(text: str, mode: str = "cjk_chars") -> int:
    if mode == "all_chars":
        return len(text)
    if mode == "words":
        return len([token for token in text.split() if token.strip()])
    return sum(1 for ch in text if "\u3400" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff")


def _section_unit_counts(markdown_text: str, mode: str) -> dict[str, int]:
    sections: dict[str, str] = {}
    current = "全文"
    buffer: list[str] = []
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            sections[current] = "\n".join(buffer)
            current = line.replace("## ", "", 1).strip()
            buffer = []
            continue
        buffer.append(line)
    sections[current] = "\n".join(buffer)
    return {name: count_text_units(content, mode) for name, content in sections.items()}


def build_report_metrics(
    mission: dict[str, Any],
    report_exec_text: str,
    report_analyst_text: str,
) -> dict[str, Any]:
    mode = str(mission.get("length_counting", "cjk_chars"))
    min_exec = int(mission.get("min_chars_exec", 2000))
    min_analyst = int(mission.get("min_chars_analyst", 5000))
    exec_count = count_text_units(report_exec_text, mode)
    analyst_count = count_text_units(report_analyst_text, mode)
    exec_sections = _section_unit_counts(report_exec_text, mode)
    analyst_sections = _section_unit_counts(report_analyst_text, mode)
    return {
        "counting_mode": mode,
        "thresholds": {"exec": min_exec, "analyst": min_analyst},
        "exec": {
            "units": exec_count,
            "meets_min": exec_count >= min_exec,
            "section_units": exec_sections,
        },
        "analyst": {
            "units": analyst_count,
            "meets_min": analyst_count >= min_analyst,
            "section_units": analyst_sections,
        },
        "overall_pass": exec_count >= min_exec and analyst_count >= min_analyst,
    }


def evaluate_length_policy(mission: dict[str, Any], metrics: dict[str, Any]) -> tuple[list[str], list[str]]:
    policy = str(mission.get("length_policy", "warn"))
    warnings: list[str] = []
    errors: list[str] = []
    if metrics.get("exec", {}).get("meets_min", False) is False:
        msg = (
            f"exec report below threshold: {metrics['exec']['units']} < "
            f"{metrics['thresholds']['exec']} ({metrics['counting_mode']})."
        )
        if policy == "strict":
            errors.append(msg)
        else:
            warnings.append(msg)
    if metrics.get("analyst", {}).get("meets_min", False) is False:
        msg = (
            f"analyst report below threshold: {metrics['analyst']['units']} < "
            f"{metrics['thresholds']['analyst']} ({metrics['counting_mode']})."
        )
        if policy == "strict":
            errors.append(msg)
        else:
            warnings.append(msg)
    return warnings, errors


def _core_parameter_rows(mission: dict[str, Any]) -> list[dict[str, str]]:
    lookup = {row["名稱"]: row for row in TERMS_AND_PARAMETERS}
    selected = [
        "PMESII",
        "ACH",
        "baseline_mode",
        "event_granularity",
        "fidelity_guardrail",
        "narrative_mode",
        "length_policy",
        "length_counting",
        "report_profile",
    ]
    rows: list[dict[str, str]] = []
    for name in selected:
        row = lookup.get(name)
        if row is None:
            continue
        current_value = ""
        if name in mission:
            current_value = f"（本次={mission[name]}）"
        rows.append(
            {
                "名稱": name,
                "定義": row["定義"],
                "意義": f"{row['增減影響方向']}{current_value}",
            }
        )
    return rows


def render_quick_parameter_brief(mission: dict[str, Any]) -> list[str]:
    lines = ["## 讀前 90 秒：本報告用到的 8 個核心參數", ""]
    for row in _core_parameter_rows(mission):
        lines.append(f"- {row['名稱']}: {row['定義']} {row['意義']}")
    lines.append("")
    return lines


def render_role_legend(mission: dict[str, Any]) -> list[str]:
    topic = str(mission.get("topic", ""))
    if any(token in topic for token in ["美伊", "伊朗", "波斯灣", "Iran"]):
        mapping = "- 本題映射：Blue=美國/盟友決策群；Red=伊朗/代理網路決策群；White=裁決與規則監理群。"
    else:
        mapping = "- 本題映射：Blue=穩定現狀/防禦方決策群；Red=改變現狀/施壓方決策群；White=裁決與規則監理群。"
    return [
        "## 角色說明（Blue/Red/White 代表什麼）",
        "- Blue（藍隊）：代表我方或維持秩序方，目標是降低失控風險、維持戰略主動與韌性。",
        "- Red（紅隊）：代表對抗方或施壓方，目標是提高對手成本、擴張灰色空間或創造升級優勢。",
        "- White（白隊）：獨立裁決方，不代表任一陣營；職責是規則檢核、機率更新、反欺敵與仲裁。",
        mapping,
        "- 重要限制：目前引擎為雙陣營（Blue vs Red）結構，White 不作為第三個競爭陣營，而是裁決層。",
        "",
    ]


def render_terms_and_parameters(
    mission: dict[str, Any],
    scenario: dict[str, Any],
    actor_config: dict[str, Any],
) -> str:
    lines = ["# 術語與參數字典", ""]
    lines.append("| 名稱 | 定義 | 範圍 | 預設值 | 增減影響方向 | 對哪些輸出敏感 |")
    lines.append("|---|---|---|---|---|---|")
    for row in TERMS_AND_PARAMETERS:
        lines.append(
            f"| {row['名稱']} | {row['定義']} | {row['範圍']} | {row['預設值']} | {row['增減影響方向']} | {row['對哪些輸出敏感']} |"
        )
    lines.extend(["", "## 本次任務參數", ""])
    lines.append(f"- report_profile: `{mission.get('report_profile', 'dual_layer')}`")
    lines.append(f"- ach_profile: `{mission.get('ach_profile', 'full')}`")
    lines.append(f"- term_annotation: `{mission.get('term_annotation', 'inline_glossary')}`")
    lines.append(f"- narrative_mode: `{mission.get('narrative_mode', 'event_cards')}`")
    lines.append(f"- baseline_mode: `{mission.get('baseline_mode', 'public_auto')}`")
    lines.append(f"- event_granularity: `{mission.get('event_granularity', 'semi_tactical')}`")
    lines.append(f"- fidelity_guardrail: `{mission.get('fidelity_guardrail', 'enabled')}`")
    lines.append(f"- length_policy: `{mission.get('length_policy', 'warn')}`")
    lines.append(f"- min_chars_exec: `{mission.get('min_chars_exec', 2000)}`")
    lines.append(f"- min_chars_analyst: `{mission.get('min_chars_analyst', 5000)}`")
    lines.append(f"- length_counting: `{mission.get('length_counting', 'cjk_chars')}`")
    lines.append(f"- strict_kj_threshold: `{mission.get('strict_kj_threshold', 3)}`")
    lines.append(f"- scenario.baseline: `{scenario.get('baseline', '')}`")
    lines.append(f"- blue_priorities: `{actor_config.get('blue_priorities', {})}`")
    lines.append(f"- red_priorities: `{actor_config.get('red_priorities', {})}`")
    lines.append("")
    return "\n".join(lines)


def _read_turn_value(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field)


def turn_story_cards(turn_result: Any) -> list[dict[str, Any]]:
    turn_id = int(_read_turn_value(turn_result, "turn_id") or 0)
    state_before = _read_turn_value(turn_result, "state_before") or {}
    state_after = _read_turn_value(turn_result, "state_after") or {}
    evidence_rows = _read_turn_value(turn_result, "evidence") or []
    blue_coa = _read_turn_value(turn_result, "blue_coa") or {}
    red_coa = _read_turn_value(turn_result, "red_coa") or {}
    adjudication = _read_turn_value(turn_result, "adjudication") or {}
    event_ledger = _read_turn_value(turn_result, "event_ledger") or []

    dimension_deltas: dict[str, float] = {}
    for dimension in DIMENSIONS:
        before = float(state_before.get(dimension, 50.0))
        after = float(state_after.get(dimension, 50.0))
        dimension_deltas[dimension] = round(after - before, 2)
    impacted_dimensions = [
        f"{name}({delta:+.2f})"
        for name, delta in sorted(dimension_deltas.items(), key=lambda item: abs(item[1]), reverse=True)
        if abs(delta) >= 0.2
    ][:4]
    if not impacted_dimensions:
        impacted_dimensions = [f"{name}({delta:+.2f})" for name, delta in list(dimension_deltas.items())[:2]]

    evidence_ids = [str(row.get("evidence_id", "")) for row in evidence_rows[:5] if row.get("evidence_id")]
    leading_risk = (float(state_after.get("M", 50.0)) + float(state_after.get("I", 50.0))) / 2.0
    risk_level = "高" if leading_risk >= 75 else "中" if leading_risk >= 60 else "低"
    event_by_type = {
        event_type: [row for row in event_ledger if str(row.get("event_type", "")) == event_type]
        for event_type in SEMI_TACTICAL_EVENT_TYPES
    }

    def _event_line(rows: list[dict[str, Any]], fallback: str) -> str:
        if not rows:
            return fallback
        row = rows[0]
        return f"{row.get('action_detail', '')}（地點:{row.get('location', '')}；結果:{row.get('estimated_outcome', '')}）"

    military_rows = event_by_type.get("simulated_engagement", []) + event_by_type.get("military_movement", [])
    sanction_rows = event_by_type.get("sanction_action", [])
    diplomacy_rows = event_by_type.get("diplomatic_mediation", [])
    info_rows = event_by_type.get("info_operation", [])
    infra_rows = event_by_type.get("infrastructure_disruption", [])
    top_events = sorted(event_ledger, key=lambda row: float(row.get("probability", 0.5)) * float(row.get("confidence", 0.5)), reverse=True)[:3]
    top_event_ids = [str(row.get("event_id", "")) for row in top_events if row.get("event_id")]

    return [
        {
            "turn_id": turn_id,
            "card_type": "局勢卡",
            "title": f"Turn {turn_id} 局勢卡",
            "what_happened": f"本回合整體狀態由 {state_before} 變化至 {state_after}，重點變化為 {', '.join(impacted_dimensions)}；主導事件={','.join(top_event_ids) or '無'}。",
            "why_happened": _event_line(military_rows, "藍紅雙方在軍事與資訊維度同時施力，白隊依規則與機率模型進行收斂裁決。"),
            "impacted_dimensions": impacted_dimensions,
            "cost_benefit": f"收益在於局部維穩訊號仍在；代價是 M/I 維度壓力維持高位（風險={risk_level}）。",
            "next_watch": "下一回合需優先盯 M、I 是否連續上行，以及 Infra 是否跟隨惡化。",
            "evidence_ids": evidence_ids,
            "rule_ids": adjudication.get("rule_hits", []),
            "event_ids": top_event_ids,
        },
        {
            "turn_id": turn_id,
            "card_type": "藍隊行動卡",
            "title": f"Turn {turn_id} 藍隊行動卡",
            "what_happened": _event_line(event_by_type.get("military_movement", []), "藍隊主軸採取穩定局勢 COA，集中在壓制升級鏈與維持外交操作空間。"),
            "why_happened": _event_line(sanction_rows, "主要因關鍵維度壓力偏高，需先處理最敏感面向。"),
            "impacted_dimensions": [
                f"{dimension}({float(value):+.2f})"
                for dimension, value in (event_by_type.get("military_movement", [{}])[0].get("pmesii_delta", {}) if event_by_type.get("military_movement", []) else {}).items()
            ][:3],
            "cost_benefit": "收益是短期可降低失控概率；代價是資源成本上升且對手可針對弱點反制。",
            "next_watch": "觀察藍隊高成本動作是否帶來實質壓力回落，而非短期噪音。",
            "evidence_ids": evidence_ids,
            "rule_ids": [],
            "event_ids": [str(row.get("event_id", "")) for row in event_by_type.get("military_movement", [])[:2]],
        },
        {
            "turn_id": turn_id,
            "card_type": "紅隊反制卡",
            "title": f"Turn {turn_id} 紅隊反制卡",
            "what_happened": _event_line(military_rows, "紅隊以灰色與代理人策略拉高對手決策成本，偏向分散但持續施壓。"),
            "why_happened": _event_line(info_rows, "紅隊優先利用資訊與軍事維度建立多點牽制。"),
            "impacted_dimensions": [
                f"{dimension}({float(value):+.2f})"
                for dimension, value in (military_rows[0].get("pmesii_delta", {}) if military_rows else {}).items()
            ][:3],
            "cost_benefit": "收益是迫使藍隊投入更多防護資源；代價是升級門檻被逼近，反噬風險上升。",
            "next_watch": "需盯住紅隊是否從灰色施壓轉向可歸責高強度行動。",
            "evidence_ids": evidence_ids,
            "rule_ids": [],
            "event_ids": [str(row.get("event_id", "")) for row in military_rows[:2]],
        },
        {
            "turn_id": turn_id,
            "card_type": "白隊裁決卡",
            "title": f"Turn {turn_id} 白隊裁決卡",
            "what_happened": f"白隊裁決結果為 `{adjudication.get('decision', '')}`，並觸發規則 {', '.join(adjudication.get('rule_hits', []) or ['無'])}。",
            "why_happened": _event_line(diplomacy_rows, "白隊同時考慮 ROE、機率擾動與反欺敵檢核，避免單一訊號導致誤判。"),
            "impacted_dimensions": impacted_dimensions,
            "cost_benefit": "收益是維持裁決一致性與可審計性；代價是保守判定可能延後強硬反應時機。",
            "next_watch": "追蹤下一回合 rule_fires 是否增加，以及 uncertainty_notes 是否持續擴大。",
            "evidence_ids": adjudication.get("evidence_ids", [])[:5],
            "rule_ids": adjudication.get("rule_hits", []),
            "event_ids": [str(row.get("event_id", "")) for row in diplomacy_rows[:2]],
        },
        {
            "turn_id": turn_id,
            "card_type": "證據卡",
            "title": f"Turn {turn_id} 證據卡",
            "what_happened": f"本回合納入 {len(evidence_rows)} 筆主證據，核心樣本為 {', '.join(evidence_ids[:3])}。",
            "why_happened": "證據池同時覆蓋官方來源與公開監測，目的是提高獨立來源與時效平衡。",
            "impacted_dimensions": [row.get("claim", "") for row in evidence_rows[:3]],
            "cost_benefit": "收益是證據鏈可回溯；代價是來源品質差異造成解釋不確定度。",
            "next_watch": "優先補強對 ACH 診斷性高、但獨立性不足的證據類型。",
            "evidence_ids": evidence_ids,
            "rule_ids": [],
            "event_ids": top_event_ids,
        },
        {
            "turn_id": turn_id,
            "card_type": "風險卡",
            "title": f"Turn {turn_id} 風險卡",
            "what_happened": f"當前升級風險等級判定為 {risk_level}（M/I 平均={round(leading_risk, 2)}），交火損耗帶={_loss_band_from_risk(leading_risk)}。",
            "why_happened": _event_line(infra_rows, "M 與 I 維度在衝突鏈中具領先指標性，且容易受突發事件放大。"),
            "impacted_dimensions": [
                f"M({float(state_after.get('M', 50.0)):.2f})",
                f"I({float(state_after.get('I', 50.0)):.2f})",
                f"Infra({float(state_after.get('Infra', 50.0)):.2f})",
            ],
            "cost_benefit": "收益是可提前設門檻介入；代價是若過度反應會提高外溢成本。",
            "next_watch": "觀察 M 或 I 是否連兩回合突破門檻，並聯動檢查航運與基礎設施風險訊號。",
            "evidence_ids": evidence_ids,
            "rule_ids": adjudication.get("rule_hits", []),
            "event_ids": [str(row.get("event_id", "")) for row in (infra_rows or military_rows)[:2]],
        },
    ]


def render_turn_timeline(turn_results: list["TurnResult"]) -> str:
    lines = [
        "# 逐回合時間線",
        "",
        "| 回合 | 裁決 | M | I | P | E | 主要規則 | 主要證據數 |",
        "|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for result in turn_results:
        after = _read_turn_value(result, "state_after") or {}
        adjudication = _read_turn_value(result, "adjudication") or {}
        evidence_rows = _read_turn_value(result, "evidence") or []
        turn_id = _read_turn_value(result, "turn_id")
        rules = ",".join(adjudication.get("rule_hits", [])[:3])
        lines.append(
            f"| {turn_id} | {adjudication.get('decision', '')} | {after.get('M', '')} | {after.get('I', '')} | {after.get('P', '')} | {after.get('E', '')} | {rules} | {len(evidence_rows)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_event_timeline(turn_results: list["TurnResult"]) -> str:
    lines = [
        "# 回合事件時間線（半戰術）",
        "",
        "| 回合 | 事件ID | 類型 | 行為者 -> 目標 | 地點 | 機率 | 信心 | 損耗帶 | 主要證據 |",
        "|---|---|---|---|---|---:|---:|---|---|",
    ]
    for result in turn_results:
        turn_id = int(_read_turn_value(result, "turn_id") or 0)
        event_ledger = _read_turn_value(result, "event_ledger") or []
        for event in event_ledger:
            lines.append(
                f"| {turn_id} | {event.get('event_id', '')} | {event.get('event_type', '')} | "
                f"{event.get('actor', '')} -> {event.get('target', '')} | {event.get('location', '')} | "
                f"{event.get('probability', '')} | {event.get('confidence', '')} | {event.get('casualty_or_loss_band', '')} | "
                f"{','.join(event.get('evidence_ids', [])[:3])} |"
            )
    lines.append("")
    lines.append(
        "註：本時間線為半戰術敘事（semi_tactical），僅提供區間與等級，不等同戰術級火力/毀傷解算。"
    )
    lines.append("")
    return "\n".join(lines)


def _derive_execution_recommendations(state: dict[str, float]) -> list[str]:
    recommendations: list[str] = []
    if state["M"] >= 70:
        recommendations.append("提升前沿防護與去衝突通道可用性，避免局部交火擴散。")
    if state["I"] >= 70:
        recommendations.append("啟動跨部門反資訊戰節奏，縮短假訊息澄清週期。")
    if state["Infra"] >= 60:
        recommendations.append("強化能源/港口/通訊備援演練，預置關鍵節點替代方案。")
    if not recommendations:
        recommendations.append("維持現行監測與快速應變節奏，避免過度反應。")
    return recommendations[:5]


def _dimension_interpretation(dimension: str, value: float) -> str:
    if value >= 75:
        return f"{dimension} 維度處於高壓區，任何突發事件都可能放大連鎖風險。"
    if value >= 60:
        return f"{dimension} 維度處於偏高區，需要持續觀測是否跨越警戒線。"
    if value <= 35:
        return f"{dimension} 維度偏低，短期可視為緩衝，但仍需防範反轉。"
    return f"{dimension} 維度屬中性帶，主要影響來自外生衝擊而非內生崩解。"


def _build_turn_sequence_summary(turn_results: list[Any]) -> list[str]:
    if not turn_results:
        return ["本次未提供逐回合資料，無法形成序列型推進解讀。"]
    start_state = _read_turn_value(turn_results[0], "state_before") or {}
    end_state = _read_turn_value(turn_results[-1], "state_after") or {}
    lines = []
    for dimension in DIMENSIONS:
        start_value = float(start_state.get(dimension, 50.0))
        end_value = float(end_state.get(dimension, 50.0))
        delta = round(end_value - start_value, 2)
        direction = "上行" if delta > 0 else "下行" if delta < 0 else "持平"
        lines.append(
            f"{dimension} 從 {start_value:.2f} 到 {end_value:.2f}（{direction} {delta:+.2f}），"
            f"{_dimension_interpretation(dimension, end_value)}"
        )
    return lines


def grounded_autofill_report(
    report_text: str,
    report_type: str,
    mission: dict[str, Any],
    turn_results: list[Any],
    key_judgments: list[dict[str, Any]],
) -> str:
    mode = str(mission.get("length_counting", "cjk_chars"))
    threshold = int(
        mission.get("min_chars_exec", 2000)
        if report_type == "exec"
        else mission.get("min_chars_analyst", 5000)
    )
    if count_text_units(report_text, mode) >= threshold:
        return report_text
    lines = [report_text.rstrip(), "", "## 自動補寫（資料驅動）", ""]
    lines.append("以下內容為根據本次回合輸出補寫，目的在補足讀者理解，不引入外部推測。")
    lines.append("")
    for row in _build_turn_sequence_summary(turn_results):
        lines.append(f"- {row}")
    lines.append("")
    for idx, judgment in enumerate(key_judgments[:5], start=1):
        lines.append(
            f"- KJ#{idx}: {judgment.get('claim', '')}；支持證據 {', '.join(judgment.get('supporting_evidence_ids', []))}；"
            f"反證 {', '.join(judgment.get('contradicting_evidence_ids', []))}；"
            f"機率/信心 {judgment.get('probability_range', '')}/{judgment.get('confidence_level', '')}。"
        )
    lines.append("")
    return "\n".join(lines)


def render_exec_report_markdown(
    mission: dict[str, Any],
    final_state: dict[str, float],
    indicators: dict[str, Any],
    key_judgments: list[dict[str, Any]],
    ach_detail: dict[str, Any],
    turn_results: list[Any] | None = None,
) -> str:
    annotation_profile = mission.get("term_annotation", "inline_glossary")
    hypotheses = ach_detail.get("hypothesis_summaries", [])
    most_likely = hypotheses[0]["statement"] if hypotheses else "資料不足"
    second_likely = hypotheses[1]["statement"] if len(hypotheses) > 1 else "資料不足"
    critical_trigger = "M 或 I 指標連續兩回合 >= 80，且航運衝擊事件同步上升。"
    recommendations = _derive_execution_recommendations(final_state)
    resolved_turns = turn_results or ach_detail.get("turn_results", [])
    sequence_summary = _build_turn_sequence_summary(resolved_turns)

    lines = [
        "# PMESII 決策摘要（管理層）",
        "",
        f"- 主題: {mission.get('topic', '')}",
        f"- 地理範圍: {mission.get('geo_scope', '')}",
        f"- 分級: {mission.get('classification', '')}",
        f"- 模式: report_profile={mission.get('report_profile', 'dual_layer')}, ach_profile={mission.get('ach_profile', 'full')}, narrative_mode={mission.get('narrative_mode', 'event_cards')}, baseline_mode={mission.get('baseline_mode', 'public_auto')}, event_granularity={mission.get('event_granularity', 'semi_tactical')}",
        "",
    ]
    lines.extend(render_quick_parameter_brief(mission))
    lines.extend(render_role_legend(mission))
    lines.extend(
        [
            "## 局勢摘要",
            "本局顯示出高壓競逐下的有限可控態勢：軍事與資訊維度持續擠壓，經濟與基礎設施維度緩慢傳導，政治與社會維度在多重信號下震盪。這代表系統尚未全面失控，但已進入需要精準控制的臨界帶。",
            "以下序列摘要直接對照回合輸出，說明各維度如何累積壓力：",
        ]
    )
    for row in sequence_summary:
        lines.append(f"- {row}")
    lines.extend(["", "## 局勢分維解讀"])
    for dimension in DIMENSIONS:
        value = float(final_state[dimension])
        lines.append(
            f"- {dimension}={value:.2f}：{_dimension_interpretation(dimension, value)}"
            f"  這個數值在本局中的策略含義是，{('應優先列入跨部門即時監測清單' if value >= 70 else '需與其他維度聯讀，避免單點過度解釋')}。"
        )
    if resolved_turns:
        lines.extend(["", "## 回合節奏摘要（供領導快速掌握）"])
        for result in resolved_turns[: min(8, len(resolved_turns))]:
            turn_id = int(_read_turn_value(result, "turn_id") or 0)
            adjudication = _read_turn_value(result, "adjudication") or {}
            state_after = _read_turn_value(result, "state_after") or {}
            evidence_rows = _read_turn_value(result, "evidence") or []
            lines.append(
                f"- Turn {turn_id}: 裁決={adjudication.get('decision', '')}；"
                f"M/I={state_after.get('M', '')}/{state_after.get('I', '')}；"
                f"rule_hits={','.join(adjudication.get('rule_hits', [])) or '無'}；"
                f"主要證據={','.join(row.get('evidence_id', '') for row in evidence_rows[:3])}。"
            )
    if resolved_turns:
        lines.extend(["", "## 本回合三大具體事件（事件->風險門檻->行動建議）"])
        for result in resolved_turns[: min(8, len(resolved_turns))]:
            turn_id = int(_read_turn_value(result, "turn_id") or 0)
            event_ledger = _read_turn_value(result, "event_ledger") or []
            top_events = sorted(
                event_ledger,
                key=lambda row: float(row.get("probability", 0.5)) * float(row.get("confidence", 0.5)),
                reverse=True,
            )[:3]
            for row in top_events:
                risk_hint = "高風險門檻" if float(row.get("probability", 0.0)) >= 0.7 else "中風險門檻"
                lines.append(
                    f"- Turn {turn_id} | {row.get('event_id','')} {row.get('event_type','')}: "
                    f"{row.get('action_detail','')} -> {row.get('estimated_outcome','')} -> "
                    f"{risk_hint}；建議 {('立即啟動備援 COA' if risk_hint == '高風險門檻' else '加密監測並保持外交窗口')}。"
                )
    lines.extend(
        [
            "",
            "## 最可能/次可能路徑",
            f"- 最可能路徑: {most_likely}。在目前證據組合下，該路徑顯示各方仍有控制升級節奏的能力，但需要持續壓制誤判風險。",
            f"- 次可能路徑: {second_likely}。若門檻指標被連續突破，次可能路徑會快速轉為主路徑。",
            "",
            "## 當前關鍵判斷（KJ）",
        ]
    )
    for idx, row in enumerate(key_judgments[:5], start=1):
        lines.append(
            f"{idx}. {row['claim']}（機率={row['probability_range']}，信心={row['confidence_level']}）。"
            f"支持證據={','.join(row.get('supporting_evidence_ids', []))}；反證={','.join(row.get('contradicting_evidence_ids', []))}。"
        )
        lines.append(
            f"   管理含義：若此判斷成立，資源配置應偏向{('前沿防護與情報整合' if row.get('probability_range') in {'高', '極高'} else '保留彈性並加強反證蒐集')}，"
            "並設定明確轉向條件以避免路徑依賴。"
        )
    lines.extend(["", "## 證據與反證整合解讀"])
    for summary in hypotheses[:3]:
        lines.append(
            f"- {summary.get('statement', '')}：支持論點={summary.get('why_support', ['無'])[0]}；"
            f"反對論點={summary.get('why_oppose', ['無'])[0]}；最敏感證據={summary.get('most_sensitive_evidence', 'N/A')}。"
            "此段目的在提醒決策層不要只看單一結論，必須同步掌握翻盤條件與反證方向。"
        )
    lines.extend(
        [
            "",
            "## 可執行結論",
            "管理層決策優先順序應放在『控風險鏈而非追單點勝利』：先守住高敏感維度，再對最可能路徑配置資源，最後用反證訊號檢查是否需要快速轉向。",
            "",
            "## 觸發門檻",
            f"- 失控觸發條件: {critical_trigger}",
            f"- M 指標門檻: >= 75（目前 {final_state['M']}），值越高代表軍事摩擦與升級衝動越強。",
            f"- I 指標門檻: >= 75（目前 {final_state['I']}），值越高代表資訊污染與誤判機率越大。",
            f"- Infra 指標門檻: >= 65（目前 {final_state['Infra']}），值越高代表運補與關鍵節點脆弱性上升。",
            "",
            "## 可執行建議",
        ]
    )
    for advice in recommendations:
        lines.append(f"- {advice}")
    lines.extend(
        [
            "",
            "## 精度護欄聲明",
            "- 本報告採半戰術事件敘事（semi_tactical），僅提供區間/等級，不提供精準戰損數字；不可視為戰術級火力解算結果。",
            "",
            "## 錯判代價",
            "- 低估風險會造成局部衝突擴散，並在 1-2 回合內推高軍事與資訊雙維壓力。",
            "- 高估風險會導致過度動員，擠壓經濟與外交空間，反而削弱持久競逐能力。",
            "- 忽略反證會讓決策陷入單一路徑依賴，增加資源錯配與時機錯失成本。",
            "",
            "## 決策問答（給領導 3 分鐘快速過稿）",
            "- 現在最可能發生什麼？答：最可能路徑仍是高壓下的受控競逐，但灰色擴張與局部升級已具備快速切換條件，不能用靜態假設看待。",
            "- 我們為何這樣判斷？答：因為多回合證據在 M/I 維度持續指向高壓，且 ACH 內主要假設的診斷性證據高度集中，支持與反證都可回查。",
            "- 若判斷錯了代價是什麼？答：錯在低估會導致反應延遲、錯在高估會導致過度投入；兩者都會削弱下一輪博弈籌碼，因此必須以門檻化決策控制偏差。",
            "",
            "## 下一步決策節點",
            "- 節點一: 以 24 小時節奏重校 M/I/Infra 門檻與觸發後 SOP。",
            "- 節點二: 對最敏感 KJ 追加反證蒐集，避免過度自信。",
            "- 節點三: 高成本行動若連續兩回合未改善指標，立即切換備援 COA。",
            "",
        ]
    )

    content = "\n".join(lines)
    if mission.get("length_policy", "warn") == "autofill":
        content = grounded_autofill_report(content, "exec", mission, resolved_turns, key_judgments)
    return _annotate_terms(content, annotation_profile)


def render_analyst_report_markdown(
    mission: dict[str, Any],
    final_state: dict[str, float],
    indicators: dict[str, Any],
    key_judgments: list[dict[str, Any]],
    ach_detail: dict[str, Any],
    sensitivity: dict[str, Any],
    turn_results: list["TurnResult"],
    story_cards_by_turn: dict[int, list[dict[str, Any]]] | None = None,
) -> str:
    annotation_profile = mission.get("term_annotation", "inline_glossary")
    lines = [
        "# PMESII 分析報告（分析師）",
        "",
        f"- 主題: {mission.get('topic', '')}",
        f"- 回合數: {len(turn_results)}",
        f"- seed: {mission.get('seed', 20260305)}",
        f"- narrative_mode: {mission.get('narrative_mode', 'event_cards')}",
        "",
    ]
    lines.extend(render_quick_parameter_brief(mission))
    lines.extend(render_role_legend(mission))
    lines.extend(
        [
            "## 模型與限制",
            "本報告採戰略層 PMESII 推演，turn 事件為半戰術敘事（semi_tactical）以降低理解門檻，不涵蓋戰術級射擊解算；白隊裁決由規則命中、機率擾動與反欺敵檢核共同形成。輸出適用於政策與資源配置決策，不可替代機密層級即時情報。",
            "資料來源採公開證據優先與可回溯鏈設計，重點是讓每個關鍵判斷都能被追查、被反駁、被重跑，而不是追求一次性結論。",
            "",
            "## KJ 與證據鏈",
        ]
    )
    for row in key_judgments:
        lines.append(f"### {row['claim']}")
        lines.append(f"- 機率/信心: {row['probability_range']} / {row['confidence_level']}")
        lines.append(f"- supporting_evidence_ids: {', '.join(row.get('supporting_evidence_ids', []))}")
        lines.append(f"- contradicting_evidence_ids: {', '.join(row.get('contradicting_evidence_ids', []))}")
        lines.append(f"- supporting_event_ids: {', '.join(row.get('supporting_event_ids', []))}")
        lines.append(f"- contradicting_event_ids: {', '.join(row.get('contradicting_event_ids', []))}")
        lines.append(f"- baseline_deviation_event_ids: {', '.join(row.get('baseline_deviation_event_ids', []))}")
        lines.append(f"- 推論依據: {', '.join(row.get('inferences', []))}")
        lines.append(f"- 反證摘要: {', '.join(row.get('counterevidence', []))}")
        lines.append(f"- 假設斷點: {', '.join(row.get('assumption_breakpoints', []))}")
        lines.append("")

    lines.extend(["## ACH（競爭假設分析）全矩陣解釋", ""])
    for summary in ach_detail.get("hypothesis_summaries", []):
        lines.append(f"### {summary['hypothesis_id']} - {summary['statement']}")
        lines.append(f"- weighted_total: {summary['weighted_total']}（越高代表在本輪證據下相對更可成立）")
        lines.append(f"- diagnosticity: {summary['diagnosticity']}（越高代表證據越能區分競爭假設）")
        lines.append(f"- 為何支持: {summary['why_support'][0] if summary['why_support'] else '無'}")
        lines.append(f"- 為何反對: {summary['why_oppose'][0] if summary['why_oppose'] else '無'}")
        lines.append(f"- 最敏感證據: {summary['most_sensitive_evidence']}")
        lines.append(f"- 翻盤條件: {summary['flip_condition']}")
        lines.append("")

    lines.extend(["## 逐回合事件卡敘事", ""])
    for result in turn_results:
        turn_id = int(_read_turn_value(result, "turn_id") or 0)
        adjudication = _read_turn_value(result, "adjudication") or {}
        state_before = _read_turn_value(result, "state_before") or {}
        state_after = _read_turn_value(result, "state_after") or {}
        evidence_rows = _read_turn_value(result, "evidence") or []
        lines.append(f"### Turn {turn_id}：回合總覽")
        lines.append(f"- 裁決: {adjudication.get('decision', '')}")
        lines.append(f"- 裁決理由: {'; '.join(adjudication.get('decision_rationale', []))}")
        lines.append(f"- 規則觸發: {', '.join(adjudication.get('rule_hits', []))}")
        lines.append(f"- 主要證據: {', '.join(row.get('evidence_id', '') for row in evidence_rows[:4])}")
        lines.append(f"- 狀態變化: before={state_before} -> after={state_after}")
        event_ledger = _read_turn_value(result, "event_ledger") or []
        lines.append("#### 事件序列")
        for event in event_ledger[:6]:
            lines.append(
                f"- {event.get('event_id','')} {event.get('event_type','')}: {event.get('actor','')} -> {event.get('target','')} @ {event.get('location','')} | p={event.get('probability','')} c={event.get('confidence','')} | 損耗={event.get('casualty_or_loss_band','')}"
            )
        lines.append("#### 交火/制裁/外交結果")
        for event_type in ["simulated_engagement", "sanction_action", "diplomatic_mediation"]:
            selected = [row for row in event_ledger if row.get("event_type") == event_type][:1]
            if selected:
                event = selected[0]
                lines.append(f"- {event_type}: {event.get('estimated_outcome','')}（evidence={','.join(event.get('evidence_ids', [])[:3])}）")
        lines.append("#### ACH 影響")
        lines.append(
            f"- 本回合事件對 ACH 的主要影響證據：{','.join(str(row.get('evidence_id','')) for row in evidence_rows if row.get('linked_event_ids')) or '無'}"
        )
        cards = story_cards_by_turn.get(turn_id, []) if story_cards_by_turn else turn_story_cards(result)
        for card in cards:
            lines.append(f"#### {card.get('title', '')}")
            lines.append(f"- 發生了什麼: {card.get('what_happened', '')}")
            lines.append(f"- 為何發生: {card.get('why_happened', '')}")
            lines.append(f"- 影響維度: {', '.join(card.get('impacted_dimensions', []))}")
            lines.append(f"- 代價/收益: {card.get('cost_benefit', '')}")
            lines.append(f"- 下回觀察: {card.get('next_watch', '')}")
            lines.append(f"- 參照 evidence_ids: {', '.join(card.get('evidence_ids', []))}")
        lines.append("")

    lines.extend(["## 敏感度/反證", ""])
    for row in sensitivity.get("results", [])[:8]:
        lines.append(
            f"- {row['assumption']}: stress_factor={row['stress_factor']}，escalation={row['escalation_score']}，"
            f"probability={row['probability_range']}，breakpoint={row['breakpoint_triggered']}。"
        )
    lines.extend(
        [
            "",
            "## 下輪 tasking",
            "- Intel Cell: 補強對高診斷性但低獨立性的證據類型，降低單來源偏差。",
            "- Blue Command: 檢查高成本行動是否具實質成效，未達標則調整資源投放。",
            "- Red Team: 逆向推演白隊規則邊界，測試可利用空窗與欺敵路徑。",
            "- White Cell: 對 uncertainty_notes 連續擴大情形提高人工覆核權重。",
            "- Guardrail: 維持 semi_tactical 護欄，禁止輸出精準戰損，避免假精度造成決策偏差。",
            "",
            "## 最終 PMESII 狀態",
        ]
    )
    for dimension in DIMENSIONS:
        lines.append(
            f"- {dimension}: {final_state[dimension]}（{_dimension_interpretation(dimension, float(final_state[dimension]))}）"
        )
    lines.append("")
    content = "\n".join(lines)
    if mission.get("length_policy", "warn") == "autofill":
        content = grounded_autofill_report(content, "analyst", mission, turn_results, key_judgments)
    return _annotate_terms(content, annotation_profile)


def render_report_markdown(
    mission: dict[str, Any],
    final_state: dict[str, float],
    indicators: dict[str, Any],
    key_judgments: list[dict[str, Any]],
    ach: dict[str, Any],
) -> str:
    return render_exec_report_markdown(mission, final_state, indicators, key_judgments, ach)


def build_dashboard(
    mission: dict[str, Any],
    state: dict[str, float],
    indicators: dict[str, Any],
    key_judgments: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "mission": {
            "topic": mission.get("topic", ""),
            "geo_scope": mission.get("geo_scope", ""),
            "run_mode": mission.get("run_mode", ""),
            "report_profile": mission.get("report_profile", "dual_layer"),
            "ach_profile": mission.get("ach_profile", "full"),
            "narrative_mode": mission.get("narrative_mode", "event_cards"),
            "baseline_mode": mission.get("baseline_mode", "public_auto"),
            "event_granularity": mission.get("event_granularity", "semi_tactical"),
            "fidelity_guardrail": mission.get("fidelity_guardrail", "enabled"),
            "length_policy": mission.get("length_policy", "warn"),
            "length_counting": mission.get("length_counting", "cjk_chars"),
        },
        "pmesii_state": state,
        "indicators": indicators,
        "key_judgments": key_judgments,
        "updated_at": now_iso(),
    }


def _probability_confidence_aligned(probability: str, confidence: str) -> bool:
    if probability in {"高", "極高"} and confidence == "低":
        return False
    if probability in {"低", "極低"} and confidence == "高":
        return False
    return True


def verify_quality_gates(
    mission: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    key_judgments: list[dict[str, Any]],
    ach_detail: dict[str, Any] | None = None,
    report_exec_text: str | None = None,
    event_rows: list[dict[str, Any]] | None = None,
    baseline_deviation_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    evidence_by_id = {row["evidence_id"]: row for row in evidence_rows}
    event_by_id = {str(row.get("event_id", "")): row for row in (event_rows or []) if row.get("event_id")}
    strict_threshold = int(mission.get("strict_kj_threshold", 3))
    start = datetime.fromisoformat(mission["time_window"]["start"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(mission["time_window"]["end"]).replace(tzinfo=timezone.utc)

    for idx, judgment in enumerate(key_judgments, start=1):
        evidence_ids = list(dict.fromkeys(judgment.get("evidence_ids", [])))
        support_ids = list(dict.fromkeys(judgment.get("supporting_evidence_ids", [])))
        contradict_ids = list(dict.fromkeys(judgment.get("contradicting_evidence_ids", [])))
        support_event_ids = list(dict.fromkeys(judgment.get("supporting_event_ids", [])))
        contradict_event_ids = list(dict.fromkeys(judgment.get("contradicting_event_ids", [])))
        baseline_event_ids = list(dict.fromkeys(judgment.get("baseline_deviation_event_ids", [])))
        if len(evidence_ids) < 2:
            errors.append(f"KJ#{idx} has fewer than 2 evidence IDs.")
        if not support_ids:
            errors.append(f"KJ#{idx} missing supporting_evidence_ids.")
        if not contradict_ids:
            errors.append(f"KJ#{idx} missing contradicting_evidence_ids.")
        if not judgment.get("facts"):
            errors.append(f"KJ#{idx} missing facts.")
        if not judgment.get("inferences"):
            errors.append(f"KJ#{idx} missing inferences.")
        if not judgment.get("counterevidence"):
            errors.append(f"KJ#{idx} missing counterevidence.")
        if not judgment.get("assumption_breakpoints"):
            errors.append(f"KJ#{idx} missing assumption breakpoints.")
        if event_rows is not None:
            if not support_event_ids:
                errors.append(f"KJ#{idx} missing supporting_event_ids.")
            if not contradict_event_ids:
                errors.append(f"KJ#{idx} missing contradicting_event_ids.")
            if not baseline_event_ids:
                errors.append(f"KJ#{idx} missing baseline_deviation_event_ids.")
            for event_id in support_event_ids + contradict_event_ids:
                event = event_by_id.get(str(event_id))
                if event is None:
                    errors.append(f"KJ#{idx} references unknown event ID {event_id}.")
                    continue
                if not event.get("evidence_ids"):
                    errors.append(f"KJ#{idx} event {event_id} missing evidence linkage.")
        if not _probability_confidence_aligned(
            str(judgment.get("probability_range", "")), str(judgment.get("confidence_level", ""))
        ):
            errors.append(f"KJ#{idx} probability and confidence mismatch.")

        groups: set[str] = set()
        for evidence_id in evidence_ids:
            row = evidence_by_id.get(evidence_id)
            if not row:
                errors.append(f"KJ#{idx} references unknown evidence ID {evidence_id}.")
                continue
            groups.add(str(row.get("independence_group", "unknown")))
            timestamp = datetime.fromisoformat(str(row["timestamp"]))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timestamp < start or timestamp > end:
                errors.append(f"KJ#{idx} evidence {evidence_id} outside mission time window.")
        if len(groups) < 2:
            errors.append(f"KJ#{idx} does not meet independent-source minimum (>=2).")

        if judgment.get("probability_range") in {"高", "極高"} and judgment.get("confidence_level") == "高":
            strict_groups: set[str] = set()
            for evidence_id in support_ids:
                row = evidence_by_id.get(evidence_id)
                if row:
                    strict_groups.add(str(row.get("independence_group", "unknown")))
            if len(strict_groups) < strict_threshold:
                errors.append(
                    f"KJ#{idx} high-prob/high-confidence requires >={strict_threshold} independent groups."
                )

    if ach_detail is not None:
        if not ach_detail.get("elimination_trace"):
            errors.append("ACH missing elimination_trace.")
        if not ach_detail.get("diagnosticity"):
            errors.append("ACH missing diagnosticity.")
    if baseline_deviation_rows is not None and not baseline_deviation_rows:
        errors.append("baseline_deviation_report is empty.")

    if report_exec_text is not None:
        if "可執行建議" not in report_exec_text:
            errors.append("report_exec.md missing actionable recommendations section.")
        if "監測指標門檻" not in report_exec_text and "觸發門檻" not in report_exec_text:
            errors.append("report_exec.md missing trigger threshold section.")

    return errors

def export_schemas(target_dir: str | Path) -> dict[str, Any]:
    schemas: dict[str, Any] = {
        "MissionSpec": {
            "type": "object",
            "required": ["topic", "decision_questions", "geo_scope", "time_window", "classification", "run_mode", "success_criteria"],
            "properties": {
                "topic": {"type": "string"},
                "decision_questions": {"type": "array", "items": {"type": "string"}},
                "geo_scope": {"type": "string"},
                "time_window": {
                    "type": "object",
                    "required": ["start", "end"],
                    "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
                },
                "classification": {"type": "string"},
                "run_mode": {"type": "string", "enum": ["quick", "deep", "custom"]},
                "success_criteria": {"type": "array", "items": {"type": "string"}},
                "seed": {"type": "integer"},
                "turns": {"type": "integer"},
                "output_lang": {"type": "string"},
                "report_profile": {"type": "string", "enum": sorted(REPORT_PROFILES)},
                "ach_profile": {"type": "string", "enum": sorted(ACH_PROFILES)},
                "term_annotation": {"type": "string", "enum": sorted(TERM_ANNOTATION_PROFILES)},
                "narrative_mode": {"type": "string", "enum": sorted(NARRATIVE_MODES)},
                "baseline_mode": {"type": "string", "enum": sorted(BASELINE_MODES)},
                "event_granularity": {"type": "string", "enum": sorted(EVENT_GRANULARITIES)},
                "fidelity_guardrail": {"type": "string", "enum": sorted(FIDELITY_GUARDRAILS)},
                "length_policy": {"type": "string", "enum": sorted(LENGTH_POLICIES)},
                "min_chars_exec": {"type": "integer"},
                "min_chars_analyst": {"type": "integer"},
                "length_counting": {"type": "string", "enum": sorted(LENGTH_COUNTING_MODES)},
                "strict_kj_threshold": {"type": "integer"},
            },
        },
        "ScenarioPack": {
            "type": "object",
            "required": ["baseline", "excursions", "assumption_tree", "termination_conditions", "shock_library"],
            "properties": {
                "baseline": {"type": "string"},
                "excursions": {"type": "array", "items": {"type": "object"}},
                "assumption_tree": {"type": "array", "items": {"type": "object"}},
                "termination_conditions": {"type": "array", "items": {"type": "string"}},
                "shock_library": {"type": "array", "items": {"type": "object"}},
                "initial_state": {"type": "object"},
            },
        },
        "TurnPacket": {
            "type": "object",
            "required": ["turn_id", "prior_state_hash", "intel_digest", "constraints", "tasking"],
            "properties": {
                "turn_id": {"type": "integer"},
                "prior_state_hash": {"type": "string"},
                "intel_digest": {"type": "array", "items": {"type": "object"}},
                "constraints": {"type": "array", "items": {"type": "string"}},
                "tasking": {"type": "object"},
            },
        },
        "COA": {
            "type": "object",
            "required": ["actor_id", "intent", "action_bundle", "subagent_actions", "resource_cost", "expected_effect", "confidence"],
            "properties": {
                "actor_id": {"type": "string"},
                "intent": {"type": "string"},
                "action_bundle": {"type": "array", "items": {"type": "object"}},
                "subagent_actions": {"type": "array", "items": {"type": "object"}},
                "resource_cost": {"type": "number"},
                "expected_effect": {"type": "array", "items": {"type": "object"}},
                "confidence": {"type": "number"},
            },
        },
        "AdjudicationRecord": {
            "type": "object",
            "required": [
                "turn_id",
                "decision",
                "rule_hits",
                "rule_fires",
                "decision_rationale",
                "counterdeception_findings",
                "uncertainty_notes",
                "stochastic_seed",
                "override_note",
                "evidence_ids",
            ],
            "properties": {
                "turn_id": {"type": "integer"},
                "decision": {"type": "string"},
                "rule_hits": {"type": "array", "items": {"type": "string"}},
                "rule_fires": {"type": "array", "items": {"type": "object"}},
                "decision_rationale": {"type": "array", "items": {"type": "string"}},
                "counterdeception_findings": {"type": "array", "items": {"type": "object"}},
                "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
                "stochastic_seed": {"type": "integer"},
                "override_note": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
        "EvidenceItem": {
            "type": "object",
            "required": [
                "evidence_id",
                "timestamp",
                "source",
                "source_tier",
                "independence_group",
                "claim",
                "reliability_score",
                "independence_score",
                "recency_score",
                "relevance_to_hypotheses",
            ],
            "properties": {
                "evidence_id": {"type": "string"},
                "timestamp": {"type": "string"},
                "source": {"type": "string"},
                "source_tier": {"type": "string"},
                "independence_group": {"type": "string"},
                "claim": {"type": "string"},
                "reliability_score": {"type": "number"},
                "independence_score": {"type": "number"},
                "recency_score": {"type": "number"},
                "relevance_to_hypotheses": {"type": "array", "items": {"type": "string"}},
            },
        },
        "ACHDetailed": {
            "type": "object",
            "required": [
                "hypotheses",
                "evidence_rows",
                "cell_scores",
                "diagnosticity",
                "weighted_totals",
                "sensitivity_runs",
                "elimination_trace",
            ],
            "properties": {
                "hypotheses": {"type": "array", "items": {"type": "object"}},
                "evidence_rows": {"type": "array", "items": {"type": "object"}},
                "cell_scores": {"type": "array", "items": {"type": "object"}},
                "diagnosticity": {"type": "object"},
                "weighted_totals": {"type": "object"},
                "sensitivity_runs": {"type": "array", "items": {"type": "object"}},
                "elimination_trace": {"type": "array", "items": {"type": "object"}},
            },
        },
        "KeyJudgment": {
            "type": "object",
            "required": [
                "claim",
                "facts",
                "inferences",
                "probability_range",
                "confidence_level",
                "counterevidence",
                "assumption_breakpoints",
                "evidence_ids",
                "supporting_evidence_ids",
                "contradicting_evidence_ids",
                "supporting_event_ids",
                "contradicting_event_ids",
                "baseline_deviation_event_ids",
            ],
            "properties": {
                "claim": {"type": "string"},
                "facts": {"type": "array", "items": {"type": "string"}},
                "inferences": {"type": "array", "items": {"type": "string"}},
                "probability_range": {"type": "string", "enum": PROBABILITY_BUCKETS},
                "confidence_level": {"type": "string", "enum": CONFIDENCE_LEVELS},
                "counterevidence": {"type": "array", "items": {"type": "string"}},
                "assumption_breakpoints": {"type": "array", "items": {"type": "string"}},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}},
                "contradicting_evidence_ids": {"type": "array", "items": {"type": "string"}},
                "supporting_event_ids": {"type": "array", "items": {"type": "string"}},
                "contradicting_event_ids": {"type": "array", "items": {"type": "string"}},
                "baseline_deviation_event_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
        "ActorBaselineProfile": {
            "type": "object",
            "required": ["actor_id", "name", "role"],
            "properties": {
                "actor_id": {"type": "string"},
                "name": {"type": "string"},
                "role": {"type": "string"},
                "links": {"type": "string"},
            },
        },
        "BaselineDeviationRecord": {
            "type": "object",
            "required": ["deviation_id", "turn_id", "actor", "dimension", "event_id", "severity_score", "evidence_ids"],
            "properties": {
                "deviation_id": {"type": "string"},
                "turn_id": {"type": "integer"},
                "actor": {"type": "string"},
                "dimension": {"type": "string"},
                "event_id": {"type": "string"},
                "event_type": {"type": "string"},
                "severity_score": {"type": "number"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
        "TurnEvent": {
            "type": "object",
            "required": [
                "event_id",
                "turn_id",
                "actor",
                "target",
                "location",
                "time_window",
                "event_type",
                "action_detail",
                "estimated_outcome",
                "casualty_or_loss_band",
                "pmesii_delta",
                "probability",
                "confidence",
                "evidence_ids",
                "assumption_links",
            ],
            "properties": {
                "event_id": {"type": "string"},
                "turn_id": {"type": "integer"},
                "actor": {"type": "string"},
                "target": {"type": "string"},
                "location": {"type": "string"},
                "time_window": {"type": "object"},
                "event_type": {"type": "string", "enum": SEMI_TACTICAL_EVENT_TYPES},
                "action_detail": {"type": "string"},
                "estimated_outcome": {"type": "string"},
                "casualty_or_loss_band": {"type": "string"},
                "pmesii_delta": {"type": "object"},
                "probability": {"type": "number"},
                "confidence": {"type": "number"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "assumption_links": {"type": "array", "items": {"type": "string"}},
            },
        },
        "RunArtifact": {
            "type": "object",
            "required": ["report_md", "report_exec_md", "report_analyst_md", "dashboard_json", "ach_json", "ach_detailed_json", "run_log_jsonl", "replay_bundle"],
            "properties": {
                "report_md": {"type": "string"},
                "report_exec_md": {"type": "string"},
                "report_analyst_md": {"type": "string"},
                "report_metrics_json": {"type": "string"},
                "quality_gate_warnings_json": {"type": "string"},
                "dashboard_json": {"type": "string"},
                "ach_json": {"type": "string"},
                "ach_detailed_json": {"type": "string"},
                "run_log_jsonl": {"type": "string"},
                "replay_bundle": {"type": "string"},
            },
        },
    }
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name, schema in schemas.items():
        write_json(target / f"{name}.schema.json", schema)
    return schemas


@dataclass
class TurnResult:
    turn_id: int
    turn_packet: dict[str, Any]
    blue_coa: dict[str, Any]
    red_coa: dict[str, Any]
    adjudication: dict[str, Any]
    state_before: dict[str, float]
    state_after: dict[str, float]
    indicators: dict[str, Any]
    evidence: list[dict[str, Any]]
    event_ledger: list[dict[str, Any]]
    baseline_deviations: list[dict[str, Any]]
    baseline_deviation_score: float
    agent_log: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "turn_packet": self.turn_packet,
            "blue_coa": self.blue_coa,
            "red_coa": self.red_coa,
            "adjudication": self.adjudication,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "indicators": self.indicators,
            "evidence": self.evidence,
            "event_ledger": self.event_ledger,
            "baseline_deviations": self.baseline_deviations,
            "baseline_deviation_score": self.baseline_deviation_score,
            "agent_log": self.agent_log,
        }


def execute_turn(
    mission: dict[str, Any],
    scenario: dict[str, Any],
    actor_config: dict[str, Any],
    state: dict[str, float],
    turn_id: int,
    seed: int,
    collection_plan: dict[str, Any] | None = None,
) -> TurnResult:
    prior_hash = stable_hash(state)
    baseline_db_path = mission.get("baseline_db_path") or str(
        Path(mission.get("working_dir", ".")) / "actor_baseline_db.sqlite"
    )
    ensure_actor_baseline_db(baseline_db_path, mission, collection_plan)
    raw_evidence = collect_intel(mission, scenario, turn_id, collection_plan, seed)
    vetted_evidence = source_vetting(raw_evidence)
    fused_evidence = fuse_evidence(vetted_evidence)

    blue_subactions = generate_subagent_actions(
        "Blue",
        turn_id,
        state,
        actor_config.get("blue_priorities", {}),
        seed,
    )
    red_subactions = generate_subagent_actions(
        "Red",
        turn_id,
        state,
        actor_config.get("red_priorities", {}),
        seed,
    )
    blue_coa = consolidate_coa("Blue", turn_id, blue_subactions, seed)
    red_coa = consolidate_coa("Red", turn_id, red_subactions, seed)
    provisional_event_ledger = build_turn_event_ledger(
        mission=mission,
        scenario=scenario,
        turn_id=turn_id,
        state_before=state,
        state_after=state,
        blue_coa=blue_coa,
        red_coa=red_coa,
        evidence_rows=fused_evidence,
        seed=seed,
    )
    fused_evidence = attach_event_metadata_to_evidence(fused_evidence, provisional_event_ledger)

    turn_packet = {
        "turn_id": turn_id,
        "prior_state_hash": prior_hash,
        "intel_digest": [{"evidence_id": row["evidence_id"], "claim": row["claim"]} for row in fused_evidence[:10]],
        "constraints": ["public-source-only", "strategic-level", "human-review-eligible"],
        "tasking": {
            "blue": "produce PMESII-aligned stabilization COA",
            "red": "produce PMESII-aligned coercive COA",
            "white": "adjudicate with legal, probability, and counterdeception checks",
        },
    }
    baseline_deviations, baseline_deviation_score = compare_events_with_baseline(
        db_path=baseline_db_path,
        turn_id=turn_id,
        event_ledger=provisional_event_ledger,
        state_after=state,
    )

    adjudication, next_state = adjudicate_turn(
        mission,
        turn_packet,
        state,
        blue_coa,
        red_coa,
        fused_evidence,
        seed,
        event_ledger=provisional_event_ledger,
        baseline_deviation_score=baseline_deviation_score,
    )
    event_ledger = build_turn_event_ledger(
        mission=mission,
        scenario=scenario,
        turn_id=turn_id,
        state_before=state,
        state_after=next_state,
        blue_coa=blue_coa,
        red_coa=red_coa,
        evidence_rows=fused_evidence,
        seed=seed,
    )
    fused_evidence = attach_event_metadata_to_evidence(fused_evidence, event_ledger)
    baseline_deviations, baseline_deviation_score = compare_events_with_baseline(
        db_path=baseline_db_path,
        turn_id=turn_id,
        event_ledger=event_ledger,
        state_after=next_state,
    )
    adjudication["baseline_deviation_score"] = round(baseline_deviation_score, 3)
    adjudication["event_ids"] = [str(row.get("event_id", "")) for row in event_ledger[:12]]
    indicators = indicator_from_state(next_state)
    agent_log = {
        "turn_id": turn_id,
        "blue_subagents": blue_subactions,
        "red_subagents": red_subactions,
        "white_rule_fires": adjudication.get("rule_fires", []),
        "white_decision_rationale": adjudication.get("decision_rationale", []),
        "counterdeception_findings": adjudication.get("counterdeception_findings", []),
        "event_ledger": event_ledger,
        "baseline_deviation_score": round(baseline_deviation_score, 3),
    }
    return TurnResult(
        turn_id=turn_id,
        turn_packet=turn_packet,
        blue_coa=blue_coa,
        red_coa=red_coa,
        adjudication=adjudication,
        state_before=state,
        state_after=next_state,
        indicators=indicators,
        evidence=fused_evidence,
        event_ledger=event_ledger,
        baseline_deviations=baseline_deviations,
        baseline_deviation_score=baseline_deviation_score,
        agent_log=agent_log,
    )
