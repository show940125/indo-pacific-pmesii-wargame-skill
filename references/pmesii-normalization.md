# PMESII Normalization

V4 PMESII metrics store both raw evidence and normalized scores.

Each metric should include:

- `actor_id`
- `metric`
- `dimension`
- `raw_value`
- `normalized_score`
- `source_id`
- `data_year`
- `confidence`
- `model_notes`

The normalized score is an explainable modeling aid. Raw values and field provenance remain the authority. When source confidence is low or data is stale, Gemini may use the metric only with uncertainty language, and Codex should downgrade overconfident actor claims.
