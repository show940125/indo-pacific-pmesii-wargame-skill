# World KB Source Policy

V4 uses layered provenance.

- Wikipedia/Wikidata provide broad baseline coverage and aliases.
- SIPRI military expenditure data has higher priority for defense-spending fields.
- CIA World Factbook and official government pages have higher priority for country/economic/security facts.
- IISS Military Balance style references have higher priority for order-of-battle and military inventory fields when available.
- Every modeled field must keep source id, URL, data year, confidence, and notes in `field_provenance`.

The database supports strategic simulation. It is not a real-time targeting database and must not be used to produce precise casualty, kill-probability, or operational strike predictions.
