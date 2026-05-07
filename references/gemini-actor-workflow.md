# Gemini Actor Workflow

V3 makes Gemini the actor engine and keeps Codex/Python as the controller.

Per turn:

1. Python builds or updates `wargame_knowledge.sqlite`.
2. Python creates `ActorContextPack` for Intel, Blue, Red, and White.
3. Python renders actor prompts from `assets/prompts/`.
4. Gemini returns one JSON object per actor.
5. Python parses, validates, and records `prompt.md`, `raw_response.txt`, `parsed.json`, and `validation.json`.
6. Codex controller writes `turn_*_controller_decision.json` and `turn_*_violations.json`.
7. Validated Blue/Red COAs enter local adjudication and report rendering.

The preferred live route is the Gemini MCP/offload layer. The Python CLI path uses `gemini -p` as a local fallback. `--mock-gemini` provides deterministic test responses.
