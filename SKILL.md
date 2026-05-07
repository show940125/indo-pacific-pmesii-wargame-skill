---
name: indo-pacific-pmesii-wargame
description: Use when planning or running strategic-level Indo-Pacific PMESII wargames with Gemini actor roleplay, Codex controller adjudication, SQLite knowledge context, replayable turn logs, evidence traceability, ACH, and sensitivity analysis.
---

# Indo-Pacific PMESII Wargame

Use this skill to run a strategic PMESII campaign simulation where Gemini performs actor roleplay and Codex/Python acts as observer, controller, judge, rule keeper, and report integrator. V4 adds a SQLite world knowledge layer with concrete country/organization actors, PMESII baselines, model-level military platforms, capability rules, weapon interactions, and source provenance.

Default output language is Traditional Chinese (`zh-TW`) for reports and key judgments.

## When To Use

- User asks for CSIS/RAND-style strategic simulation.
- User needs Gemini actor roleplay with Codex controller discipline.
- User needs SQLite-backed actor doctrine, PMESII context, and scenario facts.
- User needs repeatable runs, replay bundles, evidence chains, ACH, and sensitivity outputs.

## V3 Topology

- `Codex Controller`: prepares packets, queries SQLite, validates actor JSON, freezes unsafe state transitions, renders reports.
- `Gemini Intel`: fuses evidence and source gaps.
- `Gemini Blue`: produces PMESII-grounded stabilization COA.
- `Gemini Red`: produces PMESII-grounded coercive COA.
- `Gemini White`: reviews rules, legal/ROE risk, probability, counterdeception, dissent, and uncertainty.
- `Python Adjudication`: converts accepted COAs into state deltas, event ledgers, ACH, KJs, reports, and replay artifacts.

## Primary Commands

Run a V3 campaign with deterministic mock Gemini actors for validation:

```powershell
python scripts/run_campaign.py --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --out out/v3_mock_run_001 --engine gemini_actor --mock-gemini --turns 1
```

Run a V3 campaign with live Gemini CLI fallback:

```powershell
python scripts/run_campaign.py --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --out out/v3_gemini_run_001 --engine gemini_actor --turns 1
```

Run the legacy deterministic engine:

```powershell
python scripts/run_campaign.py --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --out out/run_001 --engine local_synthetic
```

Single-turn V3 workflow:

```powershell
python scripts/run_turn.py --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --turn-id 1 --out out/turn_01_result.json --engine gemini_actor --mock-gemini
```

Build or inspect the V3 knowledge database:

```powershell
python scripts/knowledge_db.py --db out/run_001/wargame_knowledge.sqlite --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --references-dir references
```

Build and inspect the V4 world knowledge layer:

```powershell
python scripts/world_kb_import.py --db out/run_001/wargame_knowledge.sqlite --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --references-dir references --context-actor Blue
```

Quality gate check:

```powershell
python scripts/verify_trace.py --mission in/mission.json --evidence out/run_001/evidence.json --event-ledger out/run_001/event_ledger.json --baseline-deviation out/run_001/baseline_deviation_report.json --key-judgments out/run_001/key_judgments.json --ach out/run_001/ach_detailed.json --report-exec out/run_001/report_exec.md --report-analyst out/run_001/report_analyst.md --length-policy warn
```

## Mandatory Quality Gates

Fail or freeze a turn if any condition is unmet:

1. Gemini actor output is not parseable JSON.
2. Blue/Red COAs lack PMESII-bound actions.
3. Actor actions lack database grounding when state transition is requested.
4. White omits dissent or uncertainty.
5. Key judgments lack independent supporting evidence.
6. Facts and inferences are mixed without labels.
7. Probability and confidence are misaligned.
8. Counterevidence and assumption breakpoints are absent.

## Outputs

- `report_exec.md`
- `report_analyst.md`
- `report.md`
- `dashboard.json`
- `ach.json`
- `ach_detailed.json`
- `sensitivity.json`
- `run_log.jsonl`
- `replay_bundle/`
- `turn_timeline.md`
- `event_timeline.md`
- `terms_and_parameters.md`
- `source_capture_manifest.json`
- `claim_registry.json`
- `evidence_clusters.json`
- `expert_review.json`
- `adjudication_dissent.json`
- `baseline_deviation_report.json`
- `event_ledger.json`
- `actor_baseline_db.sqlite`
- `wargame_knowledge.sqlite`
- `knowledge_db_manifest.json`
- `turn_*_gemini_calls/`
- `turn_*_actor_context_pack.json`
- `turn_*_controller_decision.json`
- `turn_*_violations.json`
- `run_artifact.json`

## V3 Contracts

- `ActorContextPack` includes actor identity, doctrine, PMESII indicators, capabilities, constraints, sources, scenario facts, and turn memory.
- `GeminiActorResponse` is a JSON object for `Intel`, `Blue`, `Red`, or `White`.
- `ControllerAdjudication` decides whether actor outputs may affect state.
- `KnowledgeDbManifest` records `wargame_knowledge.sqlite` schema version and table counts.
- V4 `ActorContextPack` includes `concrete_actor_id`, `concrete_actor_context`, `scenario_role_map`, military platforms, capability rules, weapon interactions, field provenance, and source documents.
- Codex does not roleplay Blue, Red, White, or Intel actor intent in the V3 path.

## References

- `references/gemini-actor-workflow.md`
- `references/sqlite-knowledge-schema.md`
- `references/world-kb-schema.md`
- `references/world-kb-source-policy.md`
- `references/military-modeling-rules.md`
- `references/pmesii-normalization.md`
- `references/controller-adjudicator-rules.md`
- `references/methodology.md`
- `references/adjudication-rules.md`
- `references/source-policy.md`
- `references/pmesii-indicator-dictionary.md`
- `references/red-team-playbook.md`
- `references/agent-handoffs.md`
