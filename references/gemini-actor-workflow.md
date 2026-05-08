# Gemini Actor Workflow

V4.5 makes Gemini the concrete actor engine and keeps Codex/Python as the controller.

Per turn:

1. Python builds or updates `wargame_knowledge.sqlite`.
2. Python selects concrete scenario actors and maps them to Blue/Red/Neutral/Non-state roles.
3. Python creates `ActorContextPack` for each concrete actor plus Intel and White support roles.
4. Python renders actor prompts from `assets/prompts/`.
5. Gemini returns one JSON object per concrete actor/support role.
6. Python parses, validates, and records `prompt.md`, `raw_response.txt`, `parsed.json`, and `validation.json` under `turn_*_actor_calls/`.
7. Python writes multi-actor synthesis, alliance dissent, proxy autonomy risk, controller decision, and violations artifacts.
8. Validated concrete actor outputs are aggregated into Blue/Red COAs for adjudication and report rendering.

Live route selection uses `--gemini-launch-mode auto|popen_headless|pty_interactive|mcp`. `auto` tries PTY interactive first, then headless `-p`, then MCP fallback metadata. `--mock-gemini` provides deterministic test responses. Any live failure must be recorded in `validation.json` with a precise fallback kind such as `auth_required`, `auth_consent_loop`, `timeout_no_output`, `timeout_after_partial_output`, or `mcp_transport_closed`.

Use `scripts/diagnose_gemini_cli.py` before long live runs to separate OAuth/Google One CLI issues from actor pipeline defects.
