from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_gemini() -> str:
    names = ["gemini.cmd", "gemini.exe", "gemini"] if os.name == "nt" else ["gemini"]
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return "gemini"


def resolve_node() -> str:
    return shutil.which("node.exe" if os.name == "nt" else "node") or "node"


def node_pty_require() -> str | None:
    candidate = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@google" / "gemini-cli" / "node_modules" / "node-pty"
    if candidate.exists():
        return str(candidate).replace("\\", "/")
    return None


def sanitize(text: str, limit: int = 1600) -> str:
    cleaned = re.sub(r"ya29\.[A-Za-z0-9._\-]+", "ya29.[REDACTED]", text)
    cleaned = re.sub(r"1//[A-Za-z0-9._\-]+", "1//[REDACTED]", cleaned)
    cleaned = re.sub(r"AIza[A-Za-z0-9_\-]+", "AIza[REDACTED]", cleaned)
    return cleaned[-limit:]


def env_presence() -> dict[str, Any]:
    keys = [
        "CI",
        "NO_BROWSER",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT_ID",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "TERM",
        "USERPROFILE",
        "HOME",
    ]
    result: dict[str, Any] = {}
    for key in keys:
        value = os.environ.get(key)
        if value is None:
            result[key] = {"set": False}
        elif "KEY" in key or "TOKEN" in key or "CREDENTIAL" in key:
            result[key] = {"set": True, "length": len(value)}
        else:
            result[key] = {"set": True, "value": value}
    return result


def gemini_settings() -> dict[str, Any]:
    gemini_home = Path.home() / ".gemini"
    settings_path = gemini_home / "settings.json"
    trusted_path = gemini_home / "trustedFolders.json"
    oauth_path = gemini_home / "oauth_creds.json"
    accounts_path = gemini_home / "google_accounts.json"
    payload: dict[str, Any] = {
        "gemini_home": str(gemini_home),
        "settings_exists": settings_path.exists(),
        "oauth_creds_exists": oauth_path.exists(),
        "google_accounts_exists": accounts_path.exists(),
        "trusted_folders_exists": trusted_path.exists(),
    }
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            payload["selectedAuthType"] = settings.get("selectedAuthType") or settings.get("security", {}).get("auth", {}).get("selectedType")
            payload["model"] = settings.get("model", {}).get("name")
            payload["previewFeatures"] = settings.get("general", {}).get("previewFeatures")
        except Exception as exc:
            payload["settings_error"] = str(exc)
    if oauth_path.exists():
        try:
            creds = json.loads(oauth_path.read_text(encoding="utf-8"))
            expiry = creds.get("expiry_date")
            payload["oauth_fields"] = {key: (key in creds) for key in ("access_token", "refresh_token", "id_token", "scope", "token_type", "expiry_date")}
            if expiry:
                expiry_dt = datetime.fromtimestamp(int(expiry) / 1000, tz=timezone.utc)
                payload["oauth_expiry_utc"] = expiry_dt.isoformat()
                payload["oauth_minutes_until_expiry"] = round((expiry_dt - datetime.now(timezone.utc)).total_seconds() / 60, 2)
        except Exception as exc:
            payload["oauth_error"] = str(exc)
    if accounts_path.exists():
        try:
            accounts = json.loads(accounts_path.read_text(encoding="utf-8"))
            payload["active_google_account"] = accounts.get("active")
        except Exception as exc:
            payload["accounts_error"] = str(exc)
    if trusted_path.exists():
        try:
            payload["trusted_folders"] = json.loads(trusted_path.read_text(encoding="utf-8"))
        except Exception as exc:
            payload["trusted_error"] = str(exc)
    return payload


def kill_gemini_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -match '@google|gemini-cli|gemini\\.js' } | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps], text=True, capture_output=True, check=False)
    rows: list[dict[str, Any]] = []
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
            rows = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            rows = [{"raw": result.stdout.strip()}]
    for row in rows:
        pid = row.get("ProcessId")
        if pid:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], text=True, capture_output=True, check=False)
    return rows


def run_command(name: str, args: list[str], timeout_sec: int, input_text: str | None = None, close_stdin: bool = True) -> dict[str, Any]:
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")
    env.setdefault("TERM", "xterm-256color")
    env.pop("CI", None)
    started = time.monotonic()
    proc = subprocess.Popen(
        args,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        stdout, stderr = proc.communicate(input=input_text or ("" if close_stdin else None), timeout=timeout_sec)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], text=True, capture_output=True, check=False)
        stdout, stderr = proc.communicate(timeout=10)
    raw = (stdout or "") + "\n" + (stderr or "")
    return {
        "name": name,
        "args": [args[0], *args[1:4]],
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "elapsed_sec": round(time.monotonic() - started, 3),
        "raw_excerpt": sanitize(raw),
        "leftover_gemini_processes_killed": kill_gemini_processes(),
    }


def pty_script() -> str:
    return r"""
const pty = require(process.env.NODE_PTY_REQUIRE);
const gemini = process.env.GEMINI_CMD;
const timeoutMs = Number(process.env.GEMINI_TIMEOUT_MS || '60000');
const prompt = 'Return exactly OK_PTY_DIAGNOSTIC and nothing else.';
const proc = pty.spawn(gemini, ['--skip-trust', '--approval-mode', 'plan', '--output-format', 'text'], {
  name: 'xterm-256color',
  cols: 120,
  rows: 40,
  cwd: process.env.GEMINI_CWD || process.cwd(),
  env: {...process.env, TERM: 'xterm-256color'}
});
let raw = '';
let sent = false;
function stripAnsi(value) {
  return value.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '').replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, '');
}
function finish(status, code) {
  console.log('__PTY_DIAG_START__');
  console.log(JSON.stringify({status, raw: stripAnsi(raw).slice(-4000)}));
  console.log('__PTY_DIAG_END__');
  try { proc.write('/quit\r'); } catch {}
  setTimeout(() => { try { proc.kill(); } catch {}; process.exit(code); }, 500);
}
proc.onData((data) => {
  raw += data;
  const clean = stripAnsi(raw);
  if (!sent && /(Ask Gemini|Type your message|Ready|>)/i.test(clean)) {
    sent = true;
    proc.write(prompt + '\r');
  }
  if (/OK_PTY_DIAGNOSTIC/i.test(clean)) finish('ok', 0);
  if (/How would you like to authenticate|Get started|Authentication consent could not be obtained|Manual authorization is required/i.test(clean)) finish('auth_or_consent_prompt', 3);
});
proc.onExit(({exitCode}) => finish('exit_' + exitCode, exitCode || 1));
setTimeout(() => {
  if (!sent) { sent = true; proc.write(prompt + '\r'); }
}, 8000);
setTimeout(() => finish(raw.trim() ? 'timeout_after_partial_output' : 'timeout_no_output', 2), timeoutMs);
"""


def run_pty(timeout_sec: int, out_dir: Path) -> dict[str, Any]:
    node_pty = node_pty_require()
    if not node_pty:
        return {"name": "pty_interactive", "status": "node_pty_missing"}
    script_path = out_dir / "_gemini_pty_diag.js"
    script_path.write_text(pty_script(), encoding="utf-8")
    env = dict(os.environ)
    env.update(
        {
            "NODE_PTY_REQUIRE": node_pty,
            "GEMINI_CMD": resolve_gemini(),
            "GEMINI_TIMEOUT_MS": str(timeout_sec * 1000),
            "GEMINI_CWD": str(skill_dir()),
            "TERM": "xterm-256color",
        }
    )
    env.pop("CI", None)
    started = time.monotonic()
    try:
        result = subprocess.run([resolve_node(), str(script_path)], text=True, encoding="utf-8", capture_output=True, timeout=timeout_sec + 15, env=env, check=False)
        raw = (result.stdout or "") + "\n" + (result.stderr or "")
    except subprocess.TimeoutExpired as exc:
        raw = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + "\n" + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        result = None
    match = re.search(r"__PTY_DIAG_START__\s*(\{.*?\})\s*__PTY_DIAG_END__", raw, flags=re.DOTALL)
    parsed = json.loads(match.group(1)) if match else {"status": "no_result_marker", "raw": raw}
    return {
        "name": "pty_interactive",
        "returncode": result.returncode if result else None,
        "elapsed_sec": round(time.monotonic() - started, 3),
        "status": parsed.get("status"),
        "raw_excerpt": sanitize(str(parsed.get("raw", raw))),
        "leftover_gemini_processes_killed": kill_gemini_processes(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Gemini CLI OAuth/headless behavior without exposing secrets.")
    parser.add_argument("--out", default=str(skill_dir() / "out" / "gemini_cli_diagnostics.json"))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    out_path = Path(args.out)
    gemini = resolve_gemini()
    prompt = "Return exactly OK_DIRECT_DIAGNOSTIC and nothing else."
    payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cwd": str(Path.cwd()),
        "skill_dir": str(skill_dir()),
        "gemini_command": gemini,
        "node_command": resolve_node(),
        "environment": env_presence(),
        "gemini_settings": gemini_settings(),
        "tests": [],
    }
    payload["tests"].append(run_command("version", [gemini, "--version"], min(args.timeout, 20)))
    payload["tests"].append(run_command("direct_p_prompt", [gemini, "--skip-trust", "-p", prompt, "--output-format", "text", "--approval-mode", "plan"], args.timeout))
    payload["tests"].append(run_command("stdin_pipe", [gemini, "--skip-trust", "--output-format", "text", "--approval-mode", "plan"], args.timeout, input_text=prompt + "\n"))
    payload["tests"].append(run_pty(args.timeout, out_path.parent))
    payload["tests"].append(
        {
            "name": "mcp_wrapper",
            "status": "not_invoked_from_standalone_script",
            "raw_excerpt": "Codex MCP namespaces are not callable from a subprocess; run the MCP smoke from the Codex tool runtime.",
        }
    )
    write_json(out_path, payload)
    print(f"Wrote Gemini CLI diagnostics: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
