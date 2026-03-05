---
name: indo-pacific-pmesii-wargame
description: Use when planning or running strategic-level Indo-Pacific PMESII wargames with multi-agent red/blue/white adjudication, replayable turn logs, evidence traceability, ACH, and sensitivity analysis.
---

# Indo-Pacific PMESII Wargame

Use this skill to run a strategic, think-tank-style PMESII campaign simulation with layered agents and strict quality gates.

Default output language is Traditional Chinese (`zh-TW`) for reports and key judgments.

## When To Use

- User asks for CSIS/RAND-style strategic simulation.
- User needs red/blue/white adjudication with traceability.
- User needs repeatable runs, excursions, and sensitivity outputs.
- User needs both briefing output and machine-readable evidence chain.

## Core Topology

- `Supreme Orchestrator`
- `Control Cell`
- `Blue Command` + PMESII subagents
- `Red Command` + PMESII subagents
- `White Cell` (`Legal/ROE`, `Probability`, `Counterdeception`)
- `Intel Cell` (`Collector`, `Source-Vetting`, `Fusion`)
- `Analysis Cell`
- `Report Cell`

## Primary Commands

Run a full campaign (v2 defaults):

```powershell
python scripts/run_campaign.py --mission in/mission.json --scenario in/scenario_pack.json --out out/run_001 --report-profile dual_layer --ach-profile full --term-annotation inline_glossary --strict-kj-threshold 3
```

Run V2.2 narrative + readability profile:

```powershell
python scripts/run_campaign.py --mission in/mission.json --scenario in/scenario_pack.json --out out/run_001 --report-profile dual_layer --ach-profile full --term-annotation inline_glossary --narrative-mode event_cards --length-policy warn --min-chars-exec 2000 --min-chars-analyst 5000 --length-counting cjk_chars
```

Run V2.3 baseline + semi-tactical events:

```powershell
python scripts/run_campaign.py --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --out out/run_001 --baseline-mode public_auto --event-granularity semi_tactical --fidelity-guardrail enabled --report-profile dual_layer --ach-profile full --term-annotation inline_glossary --narrative-mode event_cards --length-policy warn --min-chars-exec 2000 --min-chars-analyst 5000 --length-counting cjk_chars
```

Single-turn workflow:

```powershell
python scripts/run_turn.py --mission in/mission.json --scenario in/scenario_pack.json --turn-packet out/run_001/replay_bundle/turn_01_turn_packet.json --state out/run_001/replay_bundle/turn_00_state.json --out out/turn_01_result.json
```

Quality gate check (v2 strict):

```powershell
python scripts/verify_trace.py --mission in/mission.json --evidence out/run_001/evidence.json --key-judgments out/run_001/key_judgments.json --ach out/run_001/ach_detailed.json --report-exec out/run_001/report_exec.md
```

Readability-aware verification:

```powershell
python scripts/verify_trace.py --mission in/mission.json --evidence out/run_001/evidence.json --key-judgments out/run_001/key_judgments.json --ach out/run_001/ach_detailed.json --report-exec out/run_001/report_exec.md --report-analyst out/run_001/report_analyst.md --length-policy warn --min-chars-exec 2000 --min-chars-analyst 5000 --length-counting cjk_chars
```

V2.3 event-linkage verification:

```powershell
python scripts/verify_trace.py --mission in/mission.json --evidence out/run_001/evidence.json --event-ledger out/run_001/event_ledger.json --baseline-deviation out/run_001/baseline_deviation_report.json --key-judgments out/run_001/key_judgments.json --ach out/run_001/ach_detailed.json --report-exec out/run_001/report_exec.md --report-analyst out/run_001/report_analyst.md --length-policy warn --min-chars-exec 2000 --min-chars-analyst 5000 --length-counting cjk_chars
```

## Mandatory Quality Gates

Fail run if any condition is unmet:

1. Each key judgment has at least 2 independent evidence sources.
2. Facts and inferences are separated.
3. Probability and confidence are aligned.
4. Counterevidence exists.
5. Assumption breakpoints are present.

## Outputs

- `report_exec.md` (management brief)
- `report_analyst.md` (analyst full report)
- `report.md` (alias to `report_exec.md` for compatibility)
- `dashboard.json` (machine-readable dashboard)
- `ach.json`
- `ach_detailed.json`
- `sensitivity.json`
- `run_log.jsonl`
- `replay_bundle/`
- `turn_timeline.md`
- `event_timeline.md`
- `terms_and_parameters.md`
- `turn_*_agent_log.json`
- `turn_*_story_cards.json`
- `turn_*_event_ledger.json`
- `report_metrics.json`
- `quality_gate_warnings.json`
- `baseline_deviation_report.json`
- `event_ledger.json`
- `actor_baseline_db.sqlite`
- `run_artifact.json`

## V2 Contracts

- `MissionSpec` supports `report_profile`, `ach_profile`, `term_annotation`, `strict_kj_threshold`.
- `MissionSpec` also supports `narrative_mode`, `baseline_mode`, `event_granularity`, `fidelity_guardrail`, `length_policy`, `min_chars_exec`, `min_chars_analyst`, `length_counting`.
- `COA` includes `subagent_actions[]` with `rationale` and `expected_delta`.
- `AdjudicationRecord` includes `decision_rationale[]`, `rule_fires[]`, `counterdeception_findings[]`, `uncertainty_notes[]`, `baseline_deviation_score`, `event_ids[]`.
- `TurnEvent` includes `event_id`, `event_type`, `actor`, `target`, `location`, `estimated_outcome`, `casualty_or_loss_band`, `pmesii_delta`, `probability`, `confidence`, `evidence_ids[]`.
- `KeyJudgment` includes `supporting_evidence_ids[]`, `contradicting_evidence_ids[]`, `supporting_event_ids[]`, `contradicting_event_ids[]`, `baseline_deviation_event_ids[]`.

## References

- `references/methodology.md`
- `references/adjudication-rules.md`
- `references/source-policy.md`
- `references/pmesii-indicator-dictionary.md`
- `references/red-team-playbook.md`
- `references/agent-handoffs.md`
