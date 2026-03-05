# Agent Handoffs

The orchestrator enforces these contracts:

- `MissionSpec`
- `ScenarioPack`
- `TurnPacket`
- `COA`
- `AdjudicationRecord`
- `PMESIIState`
- `IndicatorBoard`
- `KeyJudgment`
- `RunArtifact`

Handoff policy:

- Every field must be machine-parseable JSON.
- Every key judgment references evidence IDs.
- Every adjudication decision stores rule hits and seed.
