# Controller And Adjudicator Rules

Codex/Python controls the V3 run.

Rules:

- Actor responses must be JSON objects.
- Blue and Red actions must bind to PMESII dimensions.
- Blue and Red actions should cite database references through `db_refs`.
- White must include dissent or uncertainty.
- Intel must expose claims or an assessment.
- High-severity actor violations freeze the state transition for that turn.
- Reports must keep actor claims, controller decisions, evidence, inference, confidence, and uncertainty separate.

Codex may downgrade, freeze, or flag actor outputs. Codex does not supply actor intent in the V3 path.
