# SQLite Knowledge Schema

`data/wargame_knowledge.sqlite` is the V4 shared knowledge layer for Gemini actors and Codex controller checks.

Main table groups:

- `actors`, `actor_doctrine`, `pmesii_indicators`, `capabilities`, `constraints`, `sources`, `scenario_facts`, `turn_memory`: V3/V4 compatibility and controller context.
- `world_actors`, `actor_aliases`, `actor_bloc_roles`: concrete country, organization, and non-state actor registry.
- `actor_pmesii_metrics`, `metric_sources`: PMESII raw values, normalized scores, confidence, and provenance.
- `military_platforms`, `platform_capabilities`, `weapon_interactions`, `force_posture`: strategic military grounding.
- `capability_rules`, `capability_triggers`, `capability_effects`, `capability_constraints`: capability preconditions, triggers, effects, risks, and countermeasures.
- `source_documents`, `source_claims`, `field_provenance`: source traceability and field-level provenance.
- `quality_diagnostics`, `benchmark_cases`: coverage and scenario benchmark checks.

Build or refresh the DB:

```powershell
python scripts/world_kb_import.py --db data/wargame_knowledge.sqlite --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --references-dir references --context-actor Blue
```

Use `scripts/query_knowledge_db.py` as the formal LLM-facing query interface. Gemini, GPT, and controller wrappers should call this CLI instead of writing ad hoc SQL:

```powershell
python scripts/query_knowledge_db.py manifest --format json --pretty
python scripts/query_knowledge_db.py actor-search --keyword Taiwan --format json
python scripts/query_knowledge_db.py scenario-actors --mission in/mission.json --scenario in/scenario_pack.json --format json
python scripts/query_knowledge_db.py actor-context --actor China --mission in/mission.json --scenario in/scenario_pack.json --question "台海壓力行動" --format json --pretty
python scripts/query_knowledge_db.py pmesii --actor PRC --dimension M --format json
python scripts/query_knowledge_db.py capabilities --actor China --format json
python scripts/query_knowledge_db.py platforms --actor Taiwan --format json
python scripts/query_knowledge_db.py interactions --family air_defense --format json
python scripts/query_knowledge_db.py sources --actor Taiwan --format json
```

Query CLI guarantees:

- Actor inputs may be actor ids, aliases, display names, or scenario roles.
- Scenario roles such as `Blue` and `Red` require `--mission` and `--scenario`.
- Output defaults to JSON for machine use; `--format md` is for humans.
- No arbitrary SQL mode is exposed.
- Errors are structured JSON and should be safe for Gemini/GPT tool loops.
