# Controller And Adjudicator Rules

Codex/Python controls the V4.5 run.

Rules:

- Actor responses must be JSON objects.
- Concrete actor actions must bind to PMESII dimensions.
- Concrete actor actions should cite database references through `db_refs`.
- Concrete actor actions should cite seeded capabilities and platforms when they use military, cyber, economic, or infrastructure effects.
- White must include dissent or uncertainty.
- Intel must expose claims or an assessment.
- High-severity actor violations freeze the state transition for that turn.
- Controller must flag alliance dissent when actors in the same bloc diverge on escalation, cost, or risk acceptance.
- Controller must flag proxy autonomy risk when Houthis, Hezbollah, or other non-state actors can outrun principal actor redlines.
- Live Gemini failures must be recorded as fallback metadata; fallback output cannot be presented as a clean live actor call.
- Reports must keep actor claims, controller decisions, evidence, inference, confidence, and uncertainty separate.

Codex may downgrade, freeze, or flag actor outputs. Codex does not supply actor intent in the V4.5 path.
