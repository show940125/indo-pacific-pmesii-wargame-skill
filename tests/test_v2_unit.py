from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
