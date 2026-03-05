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

    def run_campaign_once(self, out_dir: Path) -> dict:
        cmd = [
            "python",
            str(self.run_campaign),
            "--mission",
            str(self.mission),
            "--scenario",
            str(self.scenario),
            "--actor-config",
            str(self.actor),
            "--collection-plan",
            str(self.collection),
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


if __name__ == "__main__":
    unittest.main()
