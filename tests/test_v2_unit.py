from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
import sys
import tempfile
import shutil

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from common import (
    TERMS_AND_PARAMETERS,
    _annotate_terms,
    _calc_ach_cell,
    ai_expert_review_cell,
    attach_event_metadata_to_evidence,
    build_ach_matrix,
    build_turn_event_ledger,
    collect_intel_bundle,
    compare_events_with_baseline,
    count_text_units,
    derive_key_judgments,
    ensure_actor_baseline_db,
    render_analyst_report_markdown,
    render_exec_report_markdown,
    turn_story_cards,
)
from gemini_actor import (
    build_concrete_actor_plan,
    controller_decision,
    detect_alliance_dissent,
    detect_proxy_autonomy_risk,
    synthesize_multi_actor,
    validate_actor_response,
)
from knowledge_db import (
    actor_context_pack,
    connect,
    manifest,
    query_capabilities,
    query_interactions,
    query_platforms,
    query_pmesii,
    resolve_actor_id,
    seed_database,
    select_scenario_actor_ids,
)


class V2UnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mission = {
            "topic": "美伊衝突推演",
            "decision_questions": ["未來兩週最可能路徑為何？"],
            "geo_scope": "中東",
            "time_window": {"start": "2026-03-01T00:00:00+00:00", "end": "2026-03-10T00:00:00+00:00"},
            "classification": "UNCLASSIFIED",
            "run_mode": "quick",
            "success_criteria": ["可追溯"],
            "strict_kj_threshold": 3,
            "report_profile": "dual_layer",
            "ach_profile": "full",
            "term_annotation": "inline_glossary",
            "baseline_mode": "public_auto",
            "event_granularity": "semi_tactical",
            "fidelity_guardrail": "enabled",
        }
        self.scenario = {
            "baseline": "unit baseline",
            "excursions": [],
            "assumption_tree": [{"name": "deconfliction_channel_reliability"}],
            "termination_conditions": ["turn_limit_reached"],
            "shock_library": [],
            "initial_state": {"P": 50, "M": 70, "E": 55, "S": 48, "I": 72, "Infra": 53},
        }
        self.hypotheses = [
            {"id": "H1", "statement": "可控競爭"},
            {"id": "H2", "statement": "灰色擴張"},
            {"id": "H3", "statement": "局部升級"},
        ]
        self.evidence_rows = [
            {
                "evidence_id": "E1",
                "timestamp": "2026-03-02T00:00:00+00:00",
                "source": "official_defense_release",
                "source_tier": "official",
                "independence_group": "gov_defense",
                "claim": "局部升級 交火 報復",
                "credibility_hint": 0.8,
                "reliability_score": 0.9,
                "independence_score": 0.95,
                "recency_score": 0.8,
                "relevance_to_hypotheses": ["H3"],
            },
            {
                "evidence_id": "E2",
                "timestamp": "2026-03-03T00:00:00+00:00",
                "source": "regional_media",
                "source_tier": "public",
                "independence_group": "econ_media",
                "claim": "代理人 灰色 施壓",
                "credibility_hint": 0.7,
                "reliability_score": 0.75,
                "independence_score": 0.75,
                "recency_score": 0.8,
                "relevance_to_hypotheses": ["H2"],
            },
            {
                "evidence_id": "E3",
                "timestamp": "2026-03-04T00:00:00+00:00",
                "source": "multilateral_statement_tracker",
                "source_tier": "official",
                "independence_group": "multilateral_official",
                "claim": "降溫 對話 受控",
                "credibility_hint": 0.75,
                "reliability_score": 0.85,
                "independence_score": 0.95,
                "recency_score": 0.8,
                "relevance_to_hypotheses": ["H1"],
            },
        ]

    def test_ach_cell_scoring_matches_spec(self) -> None:
        support_cell = _calc_ach_cell(self.evidence_rows[0], self.hypotheses[2])
        oppose_cell = _calc_ach_cell(self.evidence_rows[0], self.hypotheses[0])

        self.assertGreaterEqual(support_cell["consistency_score"], 1)
        self.assertLessEqual(oppose_cell["consistency_score"], -1)
        self.assertTrue(oppose_cell["counterevidence_flag"])

        expected_diag = round(
            min(1.0, abs(support_cell["consistency_score"]) / 2.0 * support_cell["confidence_weight"]),
            3,
        )
        self.assertEqual(support_cell["diagnosticity"], expected_diag)

    def test_terms_dictionary_has_required_six_fields(self) -> None:
        required = {"名稱", "定義", "範圍", "預設值", "增減影響方向", "對哪些輸出敏感"}
        for row in TERMS_AND_PARAMETERS:
            self.assertTrue(required.issubset(row.keys()))

    def test_kj_generation_has_support_and_contradict_evidence(self) -> None:
        ach_detail = build_ach_matrix(
            key_judgments=[],
            hypotheses=self.hypotheses,
            evidence_rows=self.evidence_rows,
            mission=self.mission,
        )
        state = {"P": 52.0, "M": 60.0, "E": 49.0, "S": 46.0, "I": 58.0, "Infra": 51.0}
        indicators = {"leading": [], "significant": [], "confirmatory": []}
        judgments = derive_key_judgments(
            mission=self.mission,
            state=state,
            indicators=indicators,
            evidence_rows=self.evidence_rows,
            ach_result=ach_detail,
        )

        self.assertGreaterEqual(len(judgments), 1)
        evidence_by_id = {row["evidence_id"]: row for row in self.evidence_rows}
        for judgment in judgments:
            self.assertGreaterEqual(len(judgment["evidence_ids"]), 2)
            self.assertGreaterEqual(len(judgment["supporting_evidence_ids"]), 1)
            self.assertGreaterEqual(len(judgment["contradicting_evidence_ids"]), 1)
            if judgment["probability_range"] in {"高", "極高"} and judgment["confidence_level"] == "高":
                groups = {
                    evidence_by_id[eid]["independence_group"]
                    for eid in judgment["supporting_evidence_ids"]
                    if eid in evidence_by_id
                }
                self.assertGreaterEqual(len(groups), self.mission["strict_kj_threshold"])

    def test_turn_story_cards_have_six_types_and_required_fields(self) -> None:
        turn_result = {
            "turn_id": 1,
            "state_before": {"P": 50, "M": 70, "E": 55, "S": 48, "I": 72, "Infra": 53},
            "state_after": {"P": 52, "M": 73, "E": 56, "S": 49, "I": 74, "Infra": 55},
            "evidence": self.evidence_rows,
            "blue_coa": {"subagent_actions": [{"dimension": "M", "expected_delta": 1.5}]},
            "red_coa": {"subagent_actions": [{"dimension": "I", "expected_delta": -1.8}]},
            "adjudication": {
                "decision": "localized_escalation_risk",
                "rule_hits": ["ROE_ESCALATION_THRESHOLD"],
                "evidence_ids": ["E1", "E2"],
            },
        }
        cards = turn_story_cards(turn_result)
        self.assertEqual(len(cards), 6)
        self.assertEqual(
            {row["card_type"] for row in cards},
            {"局勢卡", "藍隊行動卡", "紅隊反制卡", "白隊裁決卡", "證據卡", "風險卡"},
        )
        for card in cards:
            self.assertIn("what_happened", card)
            self.assertIn("why_happened", card)
            self.assertIn("impacted_dimensions", card)
            self.assertIn("cost_benefit", card)
            self.assertIn("next_watch", card)

    def test_cjk_counting_and_term_annotation(self) -> None:
        text = "這是一個兵推測試 text 123。"
        self.assertEqual(count_text_units(text, "cjk_chars"), 8)
        self.assertGreater(count_text_units(text, "all_chars"), count_text_units(text, "cjk_chars"))
        annotated = _annotate_terms("ACH 結果與 ACH 追蹤", "inline_glossary")
        self.assertEqual(annotated.count("ACH（競爭假設分析）"), 1)

    def test_baseline_deviation_scoring_and_event_shape(self) -> None:
        state_before = {"P": 50, "M": 70, "E": 55, "S": 48, "I": 72, "Infra": 53}
        state_after = {"P": 53, "M": 78, "E": 57, "S": 47, "I": 79, "Infra": 58}
        blue_coa = {"subagent_actions": [{"dimension": "M", "expected_delta": 2.1}]}
        red_coa = {"subagent_actions": [{"dimension": "I", "expected_delta": -2.3}]}
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v23_unit_"))
        try:
            db_path = tmp / "actor_baseline_db.sqlite"
            ensure_actor_baseline_db(db_path, self.mission, {"sources": [{"name": "source_1", "tier": "public"}]})
            events = build_turn_event_ledger(
                mission=self.mission,
                scenario=self.scenario,
                turn_id=1,
                state_before=state_before,
                state_after=state_after,
                blue_coa=blue_coa,
                red_coa=red_coa,
                evidence_rows=self.evidence_rows,
                seed=20260305,
            )
            self.assertEqual({row["event_type"] for row in events}, {"military_movement", "simulated_engagement", "sanction_action", "diplomatic_mediation", "info_operation", "infrastructure_disruption"})
            for event in events:
                self.assertIn("event_id", event)
                self.assertIn("actor", event)
                self.assertIn("target", event)
                self.assertIn("probability", event)
                self.assertIn("confidence", event)
                self.assertIn("evidence_ids", event)
                self.assertIn("assumption_links", event)
            enriched = attach_event_metadata_to_evidence(self.evidence_rows, events)
            self.assertTrue(any(row.get("linked_event_ids") for row in enriched))
            deviations, score = compare_events_with_baseline(db_path, 1, events, state_after)
            self.assertGreaterEqual(score, 0.0)
            self.assertTrue(all("severity_score" in row for row in deviations))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_semi_tactical_guardrail_no_precise_casualty_numbers(self) -> None:
        turn_result = {
            "turn_id": 1,
            "state_before": {"P": 50, "M": 70, "E": 55, "S": 48, "I": 72, "Infra": 53},
            "state_after": {"P": 52, "M": 76, "E": 56, "S": 49, "I": 78, "Infra": 55},
            "evidence": self.evidence_rows,
            "blue_coa": {"subagent_actions": [{"dimension": "M", "expected_delta": 1.5}]},
            "red_coa": {"subagent_actions": [{"dimension": "I", "expected_delta": -1.8}]},
            "event_ledger": [
                {
                    "event_id": "T01EV02",
                    "event_type": "simulated_engagement",
                    "actor": "Red",
                    "target": "Blue",
                    "location": "波斯灣",
                    "action_detail": "模擬交火",
                    "estimated_outcome": "局部摩擦上升",
                    "casualty_or_loss_band": "中損耗帶",
                    "pmesii_delta": {"M": 1.2},
                    "probability": 0.71,
                    "confidence": 0.66,
                    "evidence_ids": ["E1"],
                    "assumption_links": ["a1"],
                    "time_window": {"start": "2026-03-01", "end": "2026-03-02"},
                }
            ],
            "adjudication": {
                "decision": "localized_escalation_risk",
                "rule_hits": ["ROE_ESCALATION_THRESHOLD"],
                "evidence_ids": ["E1", "E2"],
            },
        }
        cards = turn_story_cards(turn_result)
        serialized = " ".join(card["what_happened"] + card["cost_benefit"] for card in cards)
        self.assertNotRegex(serialized, r"\d+\s*(人|名)傷亡")

    def test_hybrid_live_capture_preserves_provenance_and_clusters(self) -> None:
        mission = dict(self.mission)
        mission["evidence_mode"] = "hybrid"
        mission["max_live_sources_per_turn"] = 2
        mission["capture_policy"] = "warn"
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v25_capture_"))
        try:
            sample = tmp / "feed.txt"
            sample.write_text("軍事摩擦升高。外交窗口仍在。", encoding="utf-8")
            bundle = collect_intel_bundle(
                mission=mission,
                scenario=self.scenario,
                turn_id=1,
                collection_plan={
                    "sources": [
                        {
                            "name": "local_osint_feed",
                            "tier": "public",
                            "independence_group": "local_file",
                            "url": sample.resolve().as_uri(),
                            "publisher": "Local Monitor",
                            "focus": "軍事摩擦",
                            "capture_mode": "static",
                            "priority": 1,
                        }
                    ]
                },
                seed=20260305,
            )
            self.assertTrue(bundle["source_capture_manifest"])
            self.assertTrue(bundle["claim_registry"])
            self.assertTrue(bundle["evidence_clusters"])
            live_rows = [row for row in bundle["evidence"] if row.get("capture_mode") == "live_capture"]
            self.assertTrue(live_rows)
            for row in live_rows:
                self.assertTrue(row.get("source_url"))
                self.assertTrue(row.get("captured_at"))
                self.assertTrue(row.get("excerpt"))
                self.assertTrue(row.get("cluster_id"))
                self.assertEqual(row.get("claim_extraction_method"), "sentence_focus_extract")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ai_panel_review_produces_consensus_and_dissent(self) -> None:
        mission = dict(self.mission)
        mission["review_mode"] = "ai_panel"
        turn_packet = {
            "turn_id": 1,
            "prior_state_hash": "abc",
            "intel_digest": [{"evidence_id": "E1", "claim": "局部升級 交火 報復"}],
            "constraints": ["public-source-only", "strategic-level"],
            "tasking": {"white": "review"},
        }
        adjudication = {
            "turn_id": 1,
            "decision": "localized_escalation_risk",
            "rule_hits": ["ROE_ESCALATION_THRESHOLD"],
            "rule_fires": [],
            "decision_rationale": ["military pressure elevated"],
            "counterdeception_findings": [],
            "uncertainty_notes": [],
            "stochastic_seed": 20260305,
            "override_note": "",
            "evidence_ids": ["E1"],
        }
        review = ai_expert_review_cell(
            mission=mission,
            turn_packet=turn_packet,
            evidence_rows=[
                {
                    "evidence_id": "E1",
                    "source": "local_osint_feed",
                    "source_family": "localmonitor",
                    "claim": "局部升級 交火 報復",
                    "capture_mode": "synthetic_fallback",
                    "provenance_confidence": 0.42,
                    "source_url": "file:///tmp/feed.txt",
                }
            ],
            adjudication=adjudication,
            event_ledger=[
                {
                    "event_id": "T01EV01",
                    "event_type": "simulated_engagement",
                    "probability": 0.79,
                    "confidence": 0.66,
                    "estimated_outcome": "局部摩擦升高",
                }
            ],
            seed=20260305,
        )
        self.assertEqual(review["review_mode"], "ai_panel")
        self.assertEqual(len(review["expert_packets"]), 4)
        self.assertIn("panel_consensus", review)
        self.assertIn("structured_dissent", review)
        self.assertIn("confidence_adjustment", review)
        self.assertTrue(review["review_trace_ids"])

    def test_reports_include_ai_review_sections(self) -> None:
        mission = dict(self.mission)
        mission["review_mode"] = "ai_panel"
        ach_detail = {"hypothesis_summaries": [], "turn_results": []}
        turn_results = [
            {
                "turn_id": 1,
                "state_after": {"P": 51, "M": 72, "E": 56, "S": 49, "I": 73, "Infra": 55},
                "evidence": [{"evidence_id": "E1", "claim": "局部升級 交火 報復"}],
                "event_ledger": [],
                "adjudication": {
                    "decision": "localized_escalation_risk",
                    "rule_hits": ["ROE_ESCALATION_THRESHOLD"],
                    "decision_rationale": ["military pressure elevated"],
                    "panel_summary": "多數支持原裁決，但要求下調信心。",
                    "expert_dissent": ["OSINT reviewer: source independence weak."],
                    "evidence_insufficiency_warning": True,
                },
            }
        ]
        exec_text = render_exec_report_markdown(
            mission=mission,
            final_state={"P": 51, "M": 72, "E": 56, "S": 49, "I": 73, "Infra": 55},
            indicators={"leading": [], "significant": [], "confirmatory": []},
            key_judgments=[
                {
                    "claim": "局部升級風險上升",
                    "probability_range": "高",
                    "confidence_level": "中",
                    "supporting_evidence_ids": ["E1"],
                    "contradicting_evidence_ids": ["E2"],
                }
            ],
            ach_detail=ach_detail,
            turn_results=turn_results,
        )
        analyst_text = render_analyst_report_markdown(
            mission=mission,
            final_state={"P": 51, "M": 72, "E": 56, "S": 49, "I": 73, "Infra": 55},
            indicators={"leading": [], "significant": [], "confirmatory": []},
            key_judgments=[
                {
                    "claim": "局部升級風險上升",
                    "probability_range": "高",
                    "confidence_level": "中",
                    "supporting_evidence_ids": ["E1"],
                    "contradicting_evidence_ids": ["E2"],
                    "supporting_event_ids": [],
                    "contradicting_event_ids": [],
                    "baseline_deviation_event_ids": [],
                    "inferences": ["軍事與資訊壓力同步上行"],
                    "counterevidence": ["外交窗口尚未完全關閉"],
                    "assumption_breakpoints": ["若外交事件連兩回合升高則翻盤"],
                }
            ],
            ach_detail={"hypothesis_summaries": []},
            sensitivity={"results": []},
            turn_results=turn_results,
            story_cards_by_turn={1: []},
        )
        self.assertIn("本回合 AI 專家覆核結論", exec_text)
        self.assertIn("主要分歧點", exec_text)
        self.assertIn("panel consensus vs dissent", analyst_text)

    def test_v3_knowledge_db_seed_and_context_pack(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v3_kb_"))
        try:
            db_path = tmp / "wargame_knowledge.sqlite"
            meta = seed_database(
                db_path=db_path,
                mission=self.mission,
                scenario=self.scenario,
                actor_config={"blue_priorities": {"M": 0.9}, "red_priorities": {"I": 0.9}},
                collection_plan={"sources": [{"name": "unit_source", "tier": "public", "independence_group": "unit"}]},
                references_dir=SKILL_DIR / "references",
            )
            self.assertEqual(meta["schema_version"], 5)
            self.assertGreaterEqual(meta["tables"]["actors"], 4)
            self.assertGreaterEqual(meta["tables"]["world_actors"], 20)
            self.assertGreaterEqual(meta["tables"]["military_platforms"], 10)
            self.assertGreaterEqual(meta["tables"]["weapon_interactions"], 5)
            pack = actor_context_pack(
                db_path,
                "Blue",
                1,
                {"P": 50, "M": 70, "E": 55, "S": 48, "I": 72, "Infra": 53},
                decision_questions=["unit question"],
            )
            self.assertEqual(pack["actor"]["actor_id"], "Blue")
            self.assertTrue(pack["concrete_actor_id"])
            self.assertTrue(pack["concrete_actor_context"]["military_platforms"])
            self.assertTrue(pack["concrete_actor_context"]["capability_rules"])
            self.assertTrue(pack["pmesii_indicators"])
            self.assertTrue(pack["capabilities"])
            self.assertTrue(pack["constraints"])
            self.assertEqual(manifest(db_path)["schema_version"], 5)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_v3_actor_validation_and_controller_freeze(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v4_validate_"))
        try:
            db_path = tmp / "wargame_knowledge.sqlite"
            seed_database(db_path, self.mission, self.scenario, {}, {}, SKILL_DIR / "references")
            pack = actor_context_pack(db_path, "Blue", 1, {"P": 50, "M": 70, "E": 55, "S": 48, "I": 72, "Infra": 53})
            invalid_capability = {
                "actor_id": "Blue",
                "turn_id": 1,
                "subagent_actions": [
                    {
                        "dimension": "M",
                        "action": "use_impossible_platform",
                        "db_refs": ["world_actors:US"],
                        "capability_refs": ["CAP_DOES_NOT_EXIST"],
                        "platform_refs": ["PLATFORM_DOES_NOT_EXIST"],
                    }
                ],
                "constraints_considered": ["C_CAPABILITY_EXISTS"],
            }
            capability_violations = validate_actor_response("Blue", invalid_capability, pack)
            self.assertTrue(any(row["rule_id"] == "CAPABILITY_NOT_SEEDED" for row in capability_violations))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        invalid_blue = {
            "actor_id": "Blue",
            "turn_id": 1,
            "subagent_actions": [{"dimension": "bad", "action": "x"}],
            "constraints_considered": [],
        }
        violations = validate_actor_response("Blue", invalid_blue)
        self.assertTrue(any(row["rule_id"] == "PMESII_DIMENSION_REQUIRED" for row in violations))
        decision = controller_decision(
            {"Blue": {"validation": {"violations": violations}}, "White": {"validation": {"violations": []}}},
            {"P": 50, "M": 70, "E": 55, "S": 48, "I": 72, "Infra": 53},
        )
        self.assertFalse(decision["accepted"])
        self.assertIn("freeze", decision["state_transition_policy"])

    def test_v4_scenario_actor_selection_cases(self) -> None:
        taiwan = select_scenario_actor_ids({"topic": "Taiwan Strait blockade", "geo_scope": "台海"}, {})
        self.assertIn("TW", taiwan["Blue"])
        self.assertIn("CN", taiwan["Red"])
        middle_east = select_scenario_actor_ids({"topic": "Iran Israel escalation", "geo_scope": "中東 波斯灣"}, {})
        self.assertIn("IR", middle_east["Red"])
        self.assertIn("IL", middle_east["Blue"])
        korea = select_scenario_actor_ids({"topic": "Korean Peninsula crisis", "geo_scope": "Korea"}, {})
        self.assertIn("KP", korea["Red"])
        self.assertIn("KR", korea["Blue"])

    def test_v4_query_helpers_resolve_and_return_grounding(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v4_query_"))
        try:
            db_path = tmp / "wargame_knowledge.sqlite"
            seed_database(db_path, self.mission, self.scenario, {}, {}, SKILL_DIR / "references")
            with connect(db_path) as conn:
                self.assertEqual(resolve_actor_id(conn, "US")["actor_id"], "US")
                self.assertEqual(resolve_actor_id(conn, "PRC")["actor_id"], "CN")
                self.assertEqual(resolve_actor_id(conn, "Taiwan")["actor_id"], "TW")
                blue = resolve_actor_id(conn, "Blue", self.mission, self.scenario)
                self.assertIn(blue["actor_id"], {"US", "IL", "SA", "AE", "GCC"})
                self.assertTrue(query_pmesii(conn, "CN", max_items=5))
                self.assertTrue(query_capabilities(conn, "CN", max_items=5))
                self.assertTrue(query_platforms(conn, "TW", max_items=5))
                self.assertTrue(query_interactions(conn, "air_defense", max_items=5))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_v4_query_cli_actor_context_and_errors(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v4_query_cli_"))
        try:
            db_path = tmp / "wargame_knowledge.sqlite"
            seed_database(db_path, self.mission, self.scenario, {}, {}, SKILL_DIR / "references")
            query_cli = SKILL_DIR / "scripts" / "query_knowledge_db.py"
            base = ["python", str(query_cli), "--db", str(db_path)]
            result = subprocess.run(
                base
                + [
                    "actor-context",
                    "--actor",
                    "China",
                    "--mission",
                    str(SKILL_DIR / "in" / "mission.json"),
                    "--scenario",
                    str(SKILL_DIR / "in" / "scenario_pack.json"),
                    "--question",
                    "台海壓力行動",
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["resolved_actor"]["actor_id"], "CN")
            concrete = payload["context_pack"]["concrete_actor_context"]
            self.assertTrue(concrete["pmesii_metrics"])
            self.assertTrue(concrete["capability_rules"])
            self.assertTrue(concrete["military_platforms"])
            self.assertTrue(concrete["weapon_interactions"])

            error = subprocess.run(
                base + ["pmesii", "--actor", "Blue", "--format", "json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(error.returncode, 0)
            self.assertFalse(json.loads(error.stdout)["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_v45_reseed_clears_current_role_map_and_concrete_context(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v45_roles_"))
        try:
            db_path = tmp / "wargame_knowledge.sqlite"
            seed_database(db_path, {"topic": "Taiwan Strait blockade", "geo_scope": "台海"}, {}, {}, {}, SKILL_DIR / "references")
            with connect(db_path) as conn:
                self.assertTrue(any(row["actor_id"] == "TW" for row in conn.execute("SELECT actor_id FROM actor_bloc_roles WHERE scenario_id='current'").fetchall()))
            mission_me = json.loads((SKILL_DIR / "in" / "mission_us_iran_20260508.json").read_text(encoding="utf-8"))
            scenario_me = json.loads((SKILL_DIR / "in" / "scenario_pack_us_iran_20260508.json").read_text(encoding="utf-8"))
            seed_database(db_path, mission_me, scenario_me, {}, {}, SKILL_DIR / "references")
            with connect(db_path) as conn:
                rows = [dict(row) for row in conn.execute("SELECT role, actor_id FROM actor_bloc_roles WHERE scenario_id='current'").fetchall()]
            self.assertFalse(any(row["actor_id"] == "TW" for row in rows))
            self.assertTrue(any(row["actor_id"] == "IR" and row["role"] == "Red" for row in rows))
            pack = actor_context_pack(db_path, "IR", 1, {"P": 50, "M": 80, "E": 70, "S": 50, "I": 75, "Infra": 70}, scenario_role="Red")
            self.assertEqual(pack["concrete_actor_id"], "IR")
            self.assertEqual(pack["scenario_role"], "Red")
            self.assertIn("HOUTHIS", pack["role_peers"])
            self.assertIn("US", pack["opposing_actors"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_v45_actor_plan_and_synthesis_diagnostics(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v45_plan_"))
        try:
            db_path = tmp / "wargame_knowledge.sqlite"
            mission_me = json.loads((SKILL_DIR / "in" / "mission_us_iran_20260508.json").read_text(encoding="utf-8"))
            scenario_me = json.loads((SKILL_DIR / "in" / "scenario_pack_us_iran_20260508.json").read_text(encoding="utf-8"))
            seed_database(db_path, mission_me, scenario_me, {}, {}, SKILL_DIR / "references")
            plan = build_concrete_actor_plan(db_path, "core")
            self.assertEqual(len(plan), 7)
            self.assertEqual({row["actor_id"] for row in plan}, {"US", "IL", "SA", "AE", "IR", "HOUTHIS", "HEZBOLLAH"})
            payloads = {
                "US_Blue": {"parsed": {"actor_id": "US_Blue", "scenario_role": "Blue", "concrete_actor_id": "US", "subagent_actions": [{"dimension": "M"}], "risk_acceptance": 0.4}, "validation": {}},
                "IL_Blue": {"parsed": {"actor_id": "IL_Blue", "scenario_role": "Blue", "concrete_actor_id": "IL", "subagent_actions": [{"dimension": "M"}], "risk_acceptance": 0.8, "dissent_from_bloc": ["prefers wider strike window"]}, "validation": {}},
                "HOUTHIS_Red": {"parsed": {"actor_id": "HOUTHIS_Red", "scenario_role": "Red", "concrete_actor_id": "HOUTHIS", "subagent_actions": [{"dimension": "Infra"}], "risk_acceptance": 0.7}, "validation": {}},
            }
            synthesis = synthesize_multi_actor(payloads, plan)
            self.assertEqual(synthesis["bloc_action_counts"]["Blue"], 2)
            self.assertTrue(detect_alliance_dissent(synthesis))
            self.assertTrue(detect_proxy_autonomy_risk(synthesis))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sqlite_v5_schema(self):
        import sqlite3
        import tempfile
        import shutil
        from pathlib import Path
        
        tmp = Path(tempfile.mkdtemp(prefix="pmesii_v5_schema_test_"))
        try:
            db_path = tmp / "wargame_knowledge.sqlite"
            meta = seed_database(
                db_path=db_path,
                mission=self.mission,
                scenario=self.scenario,
                actor_config={"blue_priorities": {"M": 0.9}, "red_priorities": {"I": 0.9}},
                collection_plan={"sources": [{"name": "unit_source", "tier": "public", "independence_group": "unit"}]},
                references_dir=SKILL_DIR / "references",
            )
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Check new tables exist
            tables = ["geographic_theaters", "theater_connections", "actor_deployments", "platform_inventories"]
            for table in tables:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                self.assertIsNotNone(cursor.fetchone(), f"Table {table} should exist in V5")
            
            # Check new columns exist in military_platforms and contain correct seeded values.
            cursor.execute("PRAGMA table_info(military_platforms)")
            columns = [row[1] for row in cursor.fetchall()]
            self.assertIn("initial_ammo_stock", columns, "initial_ammo_stock should exist in military_platforms")
            
            cursor.execute("SELECT initial_ammo_stock FROM military_platforms LIMIT 1")
            row = cursor.fetchone()
            self.assertIsNotNone(row, "military_platforms should contain seeded rows")
            self.assertEqual(row[0], 1000, "initial_ammo_stock should default to 1000")
            
            # Check new columns exist in weapon_interactions
            cursor.execute("PRAGMA table_info(weapon_interactions)")
            col_names = [row[1] for row in cursor.fetchall()]
            for col in ["p_success_min", "p_success_max", "ammo_consume_attacker", "ammo_consume_defender"]:
                self.assertIn(col, col_names, f"{col} should exist in weapon_interactions")
                
            # Verify seeded values in weapon_interactions
            cursor.execute("SELECT p_success_min, p_success_max, ammo_consume_attacker, ammo_consume_defender FROM weapon_interactions LIMIT 1")
            row = cursor.fetchone()
            self.assertIsNotNone(row, "weapon_interactions should contain seeded rows")
            self.assertGreaterEqual(row[0], 0.0)
            self.assertLessEqual(row[1], 1.0)
            self.assertGreaterEqual(row[2], 1)
            self.assertGreaterEqual(row[3], 1)
            
            # Verify that actor_deployments and platform_inventories are seeded
            cursor.execute("SELECT COUNT(*) FROM actor_deployments")
            self.assertGreater(cursor.fetchone()[0], 0, "actor_deployments should contain seeded rows")
            
            cursor.execute("SELECT COUNT(*) FROM platform_inventories")
            self.assertGreater(cursor.fetchone()[0], 0, "platform_inventories should contain seeded rows")
            
            # Verify a specific platform_inventories entry
            cursor.execute("SELECT stock_current, stock_max, burn_rate_standby, burn_rate_active, resupply_rate_turn FROM platform_inventories LIMIT 1")
            row = cursor.fetchone()
            self.assertEqual(row[0], 1000, "stock_current should match platform initial_ammo_stock")
            self.assertEqual(row[1], 1000, "stock_max should match platform initial_ammo_stock")
            self.assertEqual(row[2], 0.05, "burn_rate_standby should be 0.05")
            self.assertEqual(row[3], 2.5, "burn_rate_active should be 2.5")
            self.assertEqual(row[4], 4, "resupply_rate_turn should be 4")
            
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":

    unittest.main()
