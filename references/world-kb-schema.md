# World KB Schema

V4 adds a world knowledge layer around the V3 actor controller.

Core tables:

- `world_actors`, `actor_aliases`, `actor_bloc_roles`
- `actor_pmesii_metrics`, `metric_sources`
- `military_platforms`, `platform_capabilities`, `weapon_interactions`, `force_posture`
- `capability_rules`, `capability_triggers`, `capability_effects`, `capability_constraints`
- `source_documents`, `source_claims`, `field_provenance`
- `quality_diagnostics`, `benchmark_cases`

Compatibility tables such as `actors`, `actor_doctrine`, and `turn_memory` remain available for the existing V3 pipeline.
