# Methodology Core

This skill implements a strategic-level, human-machine wargame cycle:

1. Mission framing and constraints
2. Red/Blue PMESII course-of-action generation
3. White-cell adjudication (legal, probability, counterdeception)
4. PMESII state transition
5. Indicator and key-judgment generation
6. ACH and sensitivity analysis
7. Replayable audit output

Design principles:

- Reproducible runs via deterministic seed.
- Evidence-backed judgments with independence checks.
- Explicit separation of fact vs inference.
- Assumption breakpoints and counterevidence are mandatory.
