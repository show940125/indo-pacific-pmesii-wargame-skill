from __future__ import annotations

import argparse
import json
import os
import re
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


def _resolve_language_server() -> Path:
    user_profile = os.environ.get("USERPROFILE", "C:\\Users\\a0953041880")
    ls_bin = Path(user_profile) / "AppData" / "Local" / "Programs" / "Antigravity" / "resources" / "bin" / "language_server.exe"
    if not ls_bin.exists():
        ls_bin = Path(user_profile) / ".gemini" / "antigravity" / "bin" / "agentapi.bat"
        if not ls_bin.exists():
            raise FileNotFoundError("Could not find language_server.exe or agentapi.bat")
    return ls_bin


def test_native_subagent(prompt: str, timeout_sec: int = 60) -> dict[str, Any]:
    started = time.monotonic()
    try:
        ls_bin = _resolve_language_server()
        cmd = [str(ls_bin), "agentapi", "new-conversation", "--model=flash", prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
        payload = json.loads(result.stdout)
        convo_id = payload["response"]["newConversation"]["conversationId"]
        
        user_profile = os.environ.get("USERPROFILE", "C:\\Users\\a0953041880")
        transcript_path = Path(user_profile) / ".gemini" / "antigravity" / "brain" / convo_id / ".system_generated" / "logs" / "transcript.jsonl"
        
        final_response = None
        while time.monotonic() - started < timeout_sec:
            if not transcript_path.exists():
                time.sleep(1)
                continue
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except IOError:
                time.sleep(0.5)
                continue
                
            parsed_steps = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed_steps.append(json.loads(line))
                except Exception:
                    pass
            if parsed_steps:
                last_step = parsed_steps[-1]
                if last_step.get("type") == "PLANNER_RESPONSE":
                    content = last_step.get("content")
                    tool_calls = last_step.get("tool_calls")
                    if content and not tool_calls:
                        final_response = content
                        break
            time.sleep(1)
            
        if final_response is None:
            return {
                "success": False,
                "error": f"Timeout waiting for response. Convo ID: {convo_id}",
                "elapsed_sec": round(time.monotonic() - started, 3)
            }
        return {
            "success": True,
            "convo_id": convo_id,
            "response": final_response,
            "elapsed_sec": round(time.monotonic() - started, 3)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "elapsed_sec": round(time.monotonic() - started, 3)
        }


def env_presence() -> dict[str, Any]:
    keys = [
        "ANTIGRAVITY_LS_ADDRESS",
        "ANTIGRAVITY_CSRF_TOKEN",
        "USERPROFILE",
    ]
    result: dict[str, Any] = {}
    for key in keys:
        value = os.environ.get(key)
        if value is None:
            result[key] = {"set": False}
        elif "TOKEN" in key:
            result[key] = {"set": True, "length": len(value)}
        else:
            result[key] = {"set": True, "value": value}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Antigravity Language Server Native Subagent API.")
    parser.add_argument("--out", default=str(skill_dir() / "out" / "gemini_cli_diagnostics.json"))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    out_path = Path(args.out)
    
    ls_path = None
    try:
        ls_path = str(_resolve_language_server())
    except Exception:
        pass
        
    payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cwd": str(Path.cwd()),
        "skill_dir": str(skill_dir()),
        "language_server_path": ls_path,
        "environment": env_presence(),
        "tests": []
    }
    
    subagent_test = test_native_subagent("Return exactly OK_DIRECT_DIAGNOSTIC and nothing else.", args.timeout)
    payload["tests"].append({
        "name": "native_subagent_api_test",
        **subagent_test
    })
    
    write_json(out_path, payload)
    print(f"Wrote Language Server diagnostics: {out_path}")
    return 0 if subagent_test["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
