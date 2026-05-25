from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_dir = Path(__file__).resolve().parents[1]
        self.mission = self.skill_dir / "in" / "mission.json"
        self.scenario = self.skill_dir / "in" / "scenario_pack.json"
        self.actor = self.skill_dir / "in" / "actor_config.json"
        self.collection = self.skill_dir / "in" / "collection_plan.json"
        self.run_campaign = self.skill_dir / "scripts" / "run_campaign.py"
        self.verify_trace = self.skill_dir / "scripts" / "verify_trace.py"

    def run_campaign_once(self, out_dir: Path, mission: Path | None = None, collection: Path | None = None) -> dict:
        cmd = [
            "python",
            str(self.run_campaign),
            "--mission",
            str(mission or self.mission),
            "--scenario",
            str(self.scenario),
            "--actor-config",
            str(self.actor),
            "--collection-plan",
            str(collection or self.collection),
            "--out",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True)
        return json.loads((out_dir / "run_summary.json").read_text(encoding="utf-8"))

    def test_end_to_end_and_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run_001"
            self.run_campaign_once(out_dir)
            self.assertTrue((out_dir / "run_artifact.json").exists())
            self.assertTrue((out_dir / "report_exec.md").exists())
            self.assertTrue((out_dir / "report_analyst.md").exists())
            self.assertTrue((out_dir / "terms_and_parameters.md").exists())
            self.assertTrue((out_dir / "turn_timeline.md").exists())
            self.assertTrue((out_dir / "event_timeline.md").exists())
            self.assertTrue((out_dir / "ach_detailed.json").exists())
            self.assertTrue((out_dir / "report_metrics.json").exists())
            self.assertTrue((out_dir / "quality_gate_warnings.json").exists())
            self.assertTrue((out_dir / "baseline_deviation_report.json").exists())
            self.assertTrue((out_dir / "event_ledger.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_story_cards.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_event_ledger.json").exists())
            self.assertTrue((out_dir / "report.md").exists())
            report_text = (out_dir / "report.md").read_text(encoding="utf-8")
            self.assertIn("PMESII", report_text)
            self.assertIn("可執行建議", report_text)
            self.assertIn("本回合三大具體事件", report_text)
            verify_cmd = [
                "python",
                str(self.verify_trace),
                "--mission",
                str(self.mission),
                "--evidence",
                str(out_dir / "evidence.json"),
                "--event-ledger",
                str(out_dir / "event_ledger.json"),
                "--baseline-deviation",
                str(out_dir / "baseline_deviation_report.json"),
                "--key-judgments",
                str(out_dir / "key_judgments.json"),
                "--ach",
                str(out_dir / "ach_detailed.json"),
                "--report-exec",
                str(out_dir / "report_exec.md"),
                "--report-analyst",
                str(out_dir / "report_analyst.md"),
                "--length-policy",
                "warn",
            ]
            subprocess.run(verify_cmd, check=True)

    def test_reproducible_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_a = Path(tmp) / "run_a"
            out_b = Path(tmp) / "run_b"
            summary_a = self.run_campaign_once(out_a)
            summary_b = self.run_campaign_once(out_b)
            self.assertEqual(summary_a["final_state_hash"], summary_b["final_state_hash"])

    def test_v25_modes_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sample = tmp_path / "live_feed.txt"
            sample.write_text("灰色地帶施壓升高。外交溝通尚未完全中斷。", encoding="utf-8")
            base_mission = json.loads(self.mission.read_text(encoding="utf-8"))
            base_mission["run_mode"] = "custom"
            base_mission["turns"] = 1
            base_mission["review_mode"] = "ai_panel"
            base_mission["max_live_sources_per_turn"] = 2
            base_mission["capture_policy"] = "warn"
            base_mission["strict_kj_threshold"] = 2

            collection_payload = {
                "sources": [
                    {
                        "name": "local_feed",
                        "tier": "public",
                        "independence_group": "local_file",
                        "url": sample.resolve().as_uri(),
                        "publisher": "Local Feed",
                        "focus": "灰色地帶施壓",
                        "capture_mode": "static",
                        "priority": 1,
                    },
                    {
                        "name": "broken_feed",
                        "tier": "public",
                        "independence_group": "broken_file",
                        "url": (tmp_path / "missing.txt").resolve().as_uri(),
                        "publisher": "Broken Feed",
                        "focus": "外交溝通",
                        "capture_mode": "static",
                        "priority": 2,
                    },
                    {
                        "name": "regional_wire",
                        "tier": "public",
                        "independence_group": "regional_wire",
                        "publisher": "Regional Wire",
                        "focus": "區域盟友姿態",
                        "capture_mode": "static",
                        "priority": 3,
                    },
                ]
            }
            collection_path = tmp_path / "collection_v25.json"
            collection_path.write_text(json.dumps(collection_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            for mode in ["synthetic", "hybrid", "live_limited"]:
                mission_payload = dict(base_mission)
                mission_payload["evidence_mode"] = mode
                mission_path = tmp_path / f"mission_{mode}.json"
                mission_path.write_text(json.dumps(mission_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                out_dir = tmp_path / f"run_{mode}"
                self.run_campaign_once(out_dir, mission=mission_path, collection=collection_path)
                self.assertTrue((out_dir / "source_capture_manifest.json").exists())
                self.assertTrue((out_dir / "claim_registry.json").exists())
                self.assertTrue((out_dir / "evidence_clusters.json").exists())
                self.assertTrue((out_dir / "expert_review.json").exists())
                self.assertTrue((out_dir / "adjudication_dissent.json").exists())
                report_text = (out_dir / "report_exec.md").read_text(encoding="utf-8")
                analyst_text = (out_dir / "report_analyst.md").read_text(encoding="utf-8")
                self.assertIn("本回合 AI 專家覆核結論", report_text)
                self.assertIn("主要分歧點", report_text)
                self.assertIn("panel consensus vs dissent", analyst_text)
                evidence = json.loads((out_dir / "evidence.json").read_text(encoding="utf-8"))
                self.assertTrue(evidence)
                if mode == "hybrid":
                    self.assertTrue(any(row.get("capture_mode") == "synthetic_fallback" for row in evidence))
                if mode == "live_limited":
                    self.assertTrue(any(row.get("capture_mode") == "live_capture" for row in evidence))

    def test_v3_gemini_actor_mock_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            us_iran_mission = self.skill_dir / "in" / "mission_us_iran_20260508.json"
            us_iran_scenario = self.skill_dir / "in" / "scenario_pack_us_iran_20260508.json"
            us_iran_actor = self.skill_dir / "in" / "actor_config_us_iran_20260508.json"
            us_iran_collection = self.skill_dir / "in" / "collection_plan_us_iran_20260508.json"
            mission_payload = json.loads(us_iran_mission.read_text(encoding="utf-8"))
            mission_payload["run_mode"] = "custom"
            mission_payload["turns"] = 1
            mission_payload["strict_kj_threshold"] = 2
            mission_path = tmp_path / "mission_v3.json"
            mission_path.write_text(json.dumps(mission_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            out_dir = tmp_path / "run_v3_mock"
            cmd = [
                "python",
                str(self.run_campaign),
                "--mission",
                str(mission_path),
                "--scenario",
                str(us_iran_scenario),
                "--actor-config",
                str(us_iran_actor),
                "--collection-plan",
                str(us_iran_collection),
                "--out",
                str(out_dir),
                "--engine",
                "gemini_actor",
                "--mock-gemini",
            ]
            subprocess.run(cmd, check=True)
            knowledge_db = self.skill_dir / "data" / "wargame_knowledge.sqlite"
            self.assertTrue(knowledge_db.exists())
            self.assertFalse((out_dir / "wargame_knowledge.sqlite").exists())
            self.assertTrue((out_dir / "knowledge_db_manifest.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_actor_context_pack.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_controller_decision.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_violations.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_actor_calls" / "us_blue" / "parsed.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_actor_calls" / "ir_red" / "parsed.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_actor_calls" / "intel_support" / "parsed.json").exists())
            self.assertTrue((out_dir / "replay_bundle" / "turn_01_multi_actor_synthesis.json").exists())
            synthesis = json.loads((out_dir / "replay_bundle" / "turn_01_multi_actor_synthesis.json").read_text(encoding="utf-8"))
            self.assertEqual(synthesis["actor_count"], 7)
            manifest = json.loads((out_dir / "knowledge_db_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 6)
            self.assertGreaterEqual(manifest["coverage"]["world_actor_count"], 20)
            self.assertGreaterEqual(manifest["coverage"]["military_platform_count"], 10)
            artifact = json.loads((out_dir / "run_artifact.json").read_text(encoding="utf-8"))
            self.assertIn("wargame_knowledge_db", artifact)
            self.assertEqual(Path(artifact["wargame_knowledge_db"]), knowledge_db.resolve())
            summary = json.loads((out_dir / "run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["engine"], "gemini_actor")
            self.assertEqual(summary["actor_execution"], "v45_concrete")
            self.assertEqual(summary["actor_call_count"], 7)


if __name__ == "__main__":
    unittest.main()
