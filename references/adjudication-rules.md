# Adjudication Rules

## White-Legal/ROE

- Trigger `ROE_ESCALATION_THRESHOLD` when red military pressure exceeds configured severity.
- Trigger `INFO_DECONFLICT_REVIEW` when information operations exceed escalation-safe level.
- Otherwise pass with `ROE_BASELINE_PASS`.

## White-Probability

- Aggregate expected effects from red/blue COA by PMESII dimension.
- Apply bounded stochastic noise from run seed.
- Clamp PMESII state to `0..100`.

## White-Counterdeception

- Trigger `SOURCE_LOOP_RISK` when one independence group dominates evidence.
- Trigger `NARRATIVE_CONVERGENCE_ANOMALY` for excessive claim similarity.
- If no trigger, label `COUNTERDECEPTION_CLEAR`.
