# Changelog

All notable changes to this project are documented in this file.

The entries below distinguish the tagged release from later development milestones.

## [Unreleased]

## [v0.6.0] - 2026-06-02

- Added Apache License 2.0 licensing, project notice, bilingual documentation, and CI guidance.
- Documented the V5 baseline with V6 development additions.
- Added the SQLite-backed world knowledge layer, provenance tracking, and replay artifacts.
- Added named bases, munitions, logistics lanes, inventories, redlines, and saturation-decay combat resolution.
- Added stochastic combat, transit delays, stockpile depletion, and dynamic constraints.
- Added a deterministic synthetic example scenario for replay-pipeline validation.
- Documented the shared-core runtime boundary: Gemini / Antigravity uses native subagents, while the Codex CLI bridge remains planned adapter work.

## V6 development - 2026-05-25

- Migrated the SQLite schema for real-world base, munition, logistics-lane, and redline modeling.
- Added named inventories for 26 actors and saturation-decay combat resolution.
- Added actor-context and narrative integration for bases, munitions, and logistics.
- Expanded regression assertions for seeded Russian naval, munition, and redline data.

## V5 development - 2026-05-24

- Added stochastic combat adjudication, transit delays, stockpile depletion, and dynamic constraints.
- Expanded the world knowledge schema and added database self-healing.
- Added V5 database translation logic and longer analyst-facing reports.

## V4 / V4.5 development - 2026-05-07 to 2026-05-08

- Added the stable SQLite world knowledge database and LLM-facing query CLI.
- Added concrete per-actor execution, multi-actor synthesis, OAuth diagnostics, and transparent fallback handling.
- Added the May 2026 US-Iran / Hormuz scenario.

## V3 development - 2026-03

- Added the Gemini actor pipeline, controller adjudication, JSON validation, and replay artifacts.

## V2.5 development - 2026-03

- Added evidence modes, source capture, AI panel review, baseline deviation reports, and event cards.

## [v2.3.0] - 2026-03-05

- Published the initial Codex skill.
- Added bilingual documentation and CI coverage.

[v2.3.0]: https://github.com/show940125/indo-pacific-pmesii-wargame-skill/releases/tag/v2.3.0
[v0.6.0]: https://github.com/show940125/indo-pacific-pmesii-wargame-skill/releases/tag/v0.6.0
