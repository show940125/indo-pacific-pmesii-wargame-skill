# SQLite Knowledge Schema

`wargame_knowledge.sqlite` is the V3 shared knowledge layer for Gemini actors and Codex controller checks.

Main tables:

- `actors`: identity, faction, goals, redlines, command style, risk tolerance.
- `actor_doctrine`: PMESII preferences, taboos, escalation logic, de-escalation conditions.
- `pmesii_indicators`: dimension definitions and normal stress bands.
- `capabilities`: actor capability and limitation records.
- `constraints`: source, fidelity, legal/ROE, format, and controller rules.
- `sources`: source registry with independence and reliability priors.
- `scenario_facts`: mission/scenario/reference facts separated from durable baselines.
- `turn_memory`: accepted actor decisions, state deltas, controller rationale, and violations.

The helper entrypoint is:

```powershell
python scripts/knowledge_db.py --db out/run_001/wargame_knowledge.sqlite --mission in/mission.json --scenario in/scenario_pack.json --actor-config in/actor_config.json --collection-plan in/collection_plan.json --references-dir references
```
