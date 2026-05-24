---
name: indo-pacific-pmesii-wargame
description: Use when planning or running strategic-level Indo-Pacific PMESII wargames with Gemini actor roleplay, Codex controller adjudication, SQLite knowledge context, replayable turn logs, evidence traceability, ACH, and sensitivity analysis.
---

# Indo-Pacific PMESII Wargame

Use this skill to run a strategic PMESII campaign simulation where Gemini performs concrete actor roleplay and Codex/Python acts as observer, controller, judge, rule keeper, and report integrator. V4.5 adds per-actor Gemini execution, SQLite world knowledge context, multi-actor synthesis, alliance dissent checks, proxy autonomy risk checks, OAuth diagnostics, and transparent live-call fallback.

Default output language is Traditional Chinese (`zh-TW`) for reports and key judgments.

## When To Use

- User asks for CSIS/RAND-style strategic simulation.
- User needs Gemini actor roleplay with Codex controller discipline.
- User needs SQLite-backed actor doctrine, PMESII context, and scenario facts.
- User needs repeatable runs, replay bundles, evidence chains, ACH, and sensitivity outputs.

## V4.5 Topology

- `Codex Controller`: prepares packets, queries SQLite, validates actor JSON, freezes unsafe state transitions, renders reports.
- `Concrete Gemini Actors`: US, IR, IL, SA, AE, Houthis, Hezbollah, or scenario-selected actors each produce independent JSON.
- `Gemini Intel`: fuses evidence and source gaps.
- `Gemini White`: reviews rules, legal/ROE risk, probability, counterdeception, dissent, and uncertainty.
- `Multi-Actor Synthesis`: aggregates concrete actors into Blue/Red COAs after checking dissent and proxy risk.
- `Python Adjudication`: converts accepted COAs into state deltas, event ledgers, ACH, KJs, reports, and replay artifacts.

## Primary Commands

Run a V3 campaign with deterministic mock Gemini actors for validation:

```powershell
python scripts/run_campaign.py --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --out out/v3_mock_run_001 --engine gemini_actor --mock-gemini --turns 1
```

Run Gemini CLI OAuth diagnostics before a live run:

```powershell
python scripts/diagnose_gemini_cli.py --timeout 60 --out out/gemini_cli_diagnostics.json
```

Confirm Codex can call the already-authenticated Gemini CLI before actor runs:

```powershell
python scripts/gemini_ok_smoke.py --mode popen_headless --timeout 180
```

Expected result: `OK_GEMINI_BRIDGE` and `out/gemini_ok_smoke.json` with `success=true`. On this Windows machine, the live wrapper must launch `gemini.cmd` with `NODE_OPTIONS=--use-system-ca`, remove `CI`, send long prompts through stdin, and parse JSON defensively because Gemini CLI can emit warnings or `update_topic{...}` before the actual JSON.

Open a project-scoped OAuth repair window when `oauth-personal` falls into an auth/consent loop:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_gemini_oauth_repair.ps1
```

Run the May 8, 2026 US-Iran/Hormuz V4.5 example:

```powershell
python scripts/run_campaign.py --mission in/mission_us_iran_20260508.json --scenario in/scenario_pack_us_iran_20260508.json --actor-config in/actor_config_us_iran_20260508.json --collection-plan in/collection_plan_us_iran_20260508.json --out out/us_iran_20260508_v45_example_5turn --engine gemini_actor --actor-execution v45_concrete --actor-scope core --gemini-launch-mode auto --gemini-timeout 180 --turns 5 --report-profile dual_layer --ach-profile full --narrative-mode event_cards --length-policy warn
```

By default, V4 Gemini actor runs use `data/wargame_knowledge.sqlite`. Use `--knowledge-db <path>` only when a scenario needs an isolated local knowledge DB.

Run a V4.5 campaign with live Gemini CLI fallback:

```powershell
python scripts/run_campaign.py --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --out out/v45_gemini_run_001 --engine gemini_actor --gemini-launch-mode auto --gemini-timeout 180 --turns 1
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
python scripts/knowledge_db.py --db data/wargame_knowledge.sqlite --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --references-dir references
```

Build and inspect the V4 world knowledge layer:

```powershell
python scripts/world_kb_import.py --db data/wargame_knowledge.sqlite --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --references-dir references --context-actor Blue
```

Query the V4 knowledge DB for Gemini/GPT/Codex context:

```powershell
python scripts/query_knowledge_db.py actor-context --actor China --mission in/mission.json --scenario in/scenario_pack.json --question "台海壓力行動" --format json --pretty
python scripts/query_knowledge_db.py platforms --actor Taiwan --format json
python scripts/query_knowledge_db.py capabilities --actor PRC --format json
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
- `data/wargame_knowledge.sqlite`
- `out/<run>/knowledge_db_manifest.json`
- `turn_*_gemini_calls/`
- `turn_*_actor_context_pack.json`
- `turn_*_controller_decision.json`
- `turn_*_violations.json`
- `run_artifact.json`

## V3 Contracts

- `ActorContextPack` includes actor identity, doctrine, PMESII indicators, capabilities, constraints, sources, scenario facts, and turn memory.
- `GeminiActorResponse` is a JSON object for `Intel`, `Blue`, `Red`, or `White`.
- `ControllerAdjudication` decides whether actor outputs may affect state.
- `KnowledgeDbManifest` records `data/wargame_knowledge.sqlite` schema version and table counts for the run.
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
