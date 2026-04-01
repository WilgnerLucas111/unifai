#!/usr/bin/env python3
"""
UnifAI Telegram Bridge (C2)
Receives authorized commands and executes local governance actions.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

KEY_STATUS_VALID = "VALID"
KEY_STATUS_INVALID = "INVALID"

SUPERVISOR_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = Path(__file__).resolve().parents[3]

BUDGET_FILE = Path(os.getenv("UNIFAI_BUDGET_FILE", "/tmp/unifai_budget.json"))
SIGNAL_SCRIPT = Path(os.getenv("UNIFAI_SIGNAL_SCRIPT", str(ROOT_DIR / "scripts" / "signal_alert.sh")))
FUSE_TRIP_BIN = Path(os.getenv("UNIFAI_FUSE_TRIP_BIN", str(SUPERVISOR_DIR / "bin" / "fuse-trip")))
KEYMAN_CLI = Path(os.getenv("UNIFAI_KEYMAN_CLI", str(SUPERVISOR_DIR / "plugins" / "keyman_guardian" / "keyman_auth_cli.py")))
WASH_SCRIPT = Path(os.getenv("UNIFAI_WASH_SCRIPT", str(ROOT_DIR / "scripts" / "wash_and_sleep.sh")))
GRANT_PATH_FILE = os.getenv("UNIFAI_GRANT_PATH_FILE", "/tmp/unifai_grant_path.current")
KEY_ROTATE_ALIAS = os.getenv("UNIFAI_KEY_ROTATE_ALIAS", "codex-oauth")
KEY_ROTATE_TTL = os.getenv("UNIFAI_KEY_ROTATE_TTL", "300")

SECRETVAULT_CLI = Path(os.getenv("SECRETVAULT_CLI_PATH", str(SUPERVISOR_DIR / "supervisor-secretvault" / "src" / "cli.js")))
MASTER_KEY_FILE = Path(os.getenv("SECRETVAULT_MASTER_KEY_FILE", "/etc/little7/secretvault_master.key"))

SECURITY_UNAUTHORIZED_MSG = "🚨 UNIF_AI SECURITY: Unauthorized command attempt from [{chat_id}]."
AUDIT_LOG_FILE = Path(os.getenv("UNIFAI_AUDIT_LOG", "/var/log/unifai/audit.log"))

def log_audit(action, chat_id, details=""):
    try:
        AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        log_entry = json.dumps({"timestamp": timestamp, "action": action, "chat_id": chat_id, "details": details})
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"Failed to write audit log: {e}", file=sys.stderr)

def read_state():
    if not BUDGET_FILE.exists():
        state = {"budget": 1000, "key_status": KEY_STATUS_VALID}
        write_state(state)
        return state
    try:
        raw = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"budget": 0, "key_status": KEY_STATUS_VALID}
        return {
            "budget": int(raw.get("budget", 0)),
            "key_status": raw.get("key_status", KEY_STATUS_VALID),
            "key_status_reason": raw.get("key_status_reason"),
        }
    except Exception:
        return {"budget": 0, "key_status": KEY_STATUS_VALID}


def write_state(state):
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(state), encoding="utf-8")


def trigger_signal_alert(message):
    if SIGNAL_SCRIPT.exists() and os.access(SIGNAL_SCRIPT, os.X_OK):
        subprocess.Popen([str(SIGNAL_SCRIPT), message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def is_authorized_chat(chat_id):
    authorized = os.getenv("AUTHORIZED_CHAT_ID", "").strip()
    if not authorized:
        return False
    return str(chat_id) == authorized


def enforce_authorization(chat_id):
    if is_authorized_chat(chat_id):
        return True, ""
    message = SECURITY_UNAUTHORIZED_MSG.format(chat_id=chat_id)
    trigger_signal_alert(message)
    return False, "Unauthorized command source."


def command_status():
    state = read_state()
    budget = int(state.get("budget", 0))
    key_status = state.get("key_status", KEY_STATUS_VALID)
    reason = state.get("key_status_reason")
    if reason:
        return f"UnifAI status: budget={budget}, key_status={key_status}, reason={reason}"
    return f"UnifAI status: budget={budget}, key_status={key_status}"


def command_add_budget(value):
    try:
        delta = int(value)
    except ValueError:
        return "Invalid value. Use: /add_budget <integer>"

    if delta <= 0:
        return "Invalid value. Budget increment must be > 0."

    state = read_state()
    state["budget"] = int(state.get("budget", 0)) + delta
    write_state(state)
    return f"Budget increased by {delta}. New budget={state['budget']}"


def command_rotate():
    if not KEYMAN_CLI.exists():
        return f"Rotation failed: keyman cli not found at {KEYMAN_CLI}"

    env = os.environ.copy()
    if SECRETVAULT_CLI.exists():
        env["SECRETVAULT_CLI_PATH"] = str(SECRETVAULT_CLI)

    result = subprocess.run(
        [
            sys.executable,
            str(KEYMAN_CLI),
            "rotate",
            "--alias",
            KEY_ROTATE_ALIAS,
            "--grant-path-file",
            GRANT_PATH_FILE,
            "--ttl",
            str(KEY_ROTATE_TTL),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    payload = {}
    try:
        payload = json.loads((result.stdout or "{}").strip())
    except json.JSONDecodeError:
        payload = {"ok": False, "details": (result.stdout or "").strip()}

    if result.returncode == 0 and payload.get("ok") is True:
        state = read_state()
        state["key_status"] = KEY_STATUS_VALID
        state.pop("key_status_reason", None)
        write_state(state)
        return "Key rotation completed. key_status set to VALID."

    details = payload.get("details") or (result.stderr or result.stdout or "rotate-error").strip()
    return f"Rotation failed: {details}"


def command_kill():
    if not FUSE_TRIP_BIN.exists():
        return f"Kill failed: fuse-trip not found at {FUSE_TRIP_BIN}"

    command = [str(FUSE_TRIP_BIN), "600", "TELEGRAM_MANUAL_TRIP", "telegram-bridge-command"]
    if os.geteuid() != 0:
        command = [os.getenv("SUDO_BIN", "sudo"), "-n"] + command

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return "Fuse trip executed. OpenClaw process tree neutralized."
    error = (result.stderr or result.stdout or "unknown error").strip()
    return f"Kill failed: {error}"


def command_wash(chat_id):
    if not WASH_SCRIPT.exists():
        return f"Wash failed: script not found at {WASH_SCRIPT}"

    if not os.access(WASH_SCRIPT, os.X_OK):
        return f"Wash failed: script is not executable at {WASH_SCRIPT}"

    result = subprocess.run(
        [
            str(WASH_SCRIPT),
            "--operator",
            str(chat_id),
            "--reason",
            "telegram-wash",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        output = (result.stdout or "wash completed").strip()
        return f"Wash executed: {output}"

    details = (result.stderr or result.stdout or "wash-error").strip()
    return f"Wash failed: {details}"


def handle_command(chat_id, text):
    command_line = (text or "").strip()
    log_audit("COMMAND_RECEIVED", chat_id, command_line)
    
    allowed, denied_message = enforce_authorization(chat_id)
    if not allowed:
        log_audit("COMMAND_DENIED_UNAUTHORIZED", chat_id, command_line)
        return denied_message

    if not command_line:
        return "Empty command."

    parts = command_line.split()
    command = parts[0]
    args = parts[1:]

    try:
        if command == "/status":
            result = command_status()
        elif command == "/add_budget":
            if not args:
                result = "Usage: /add_budget <integer>"
            else:
                result = command_add_budget(args[0])
        elif command == "/rotate":
            result = command_rotate()
        elif command == "/kill":
            result = command_kill()
        elif command == "/wash":
            result = command_wash(chat_id)
        else:
            result = "Unknown command. Available: /status, /add_budget, /rotate, /kill, /wash"
            
        log_audit("COMMAND_EXECUTED", chat_id, f"cmd={command} result={result}")
        return result
    except Exception as e:
        log_audit("COMMAND_FAILED", chat_id, f"cmd={command} error={str(e)}")
        return f"Command failed: {e}"


def request_grant_path_from_secretvault():
    if not SECRETVAULT_CLI.exists() or not MASTER_KEY_FILE.exists():
        return None

    master_key = MASTER_KEY_FILE.read_text(encoding="utf-8").strip()
    if not master_key:
        return None

    env = os.environ.copy()
    env["SECRETVAULT_MASTER_KEY"] = master_key
    result = subprocess.run(
        [
            os.getenv("NODE_BIN", "node"),
            str(SECRETVAULT_CLI),
            "request",
            "--alias",
            "telegram-bot-token",
            "--purpose",
            "telegram-bridge-polling",
            "--agent",
            "oracle",
            "--ttl",
            "300",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        return None

    try:
        payload = json.loads((result.stdout or "{}").strip())
    except json.JSONDecodeError:
        return None

    if not payload.get("ok"):
        return None
    return payload.get("path")


def resolve_telegram_token():
    env_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if env_token:
        return env_token

    grant_path = request_grant_path_from_secretvault()
    if not grant_path:
        return None

    token_file = Path(grant_path)
    if not token_file.exists():
        return None
    return token_file.read_text(encoding="utf-8").strip()


def telegram_api_call(token, method, payload):
    data = urllib.parse.urlencode(payload).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/{method}"
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def send_telegram_message(token, chat_id, text):
    if os.getenv("UNIFAI_TELEGRAM_TEST_MODE", "0") == "1":
        return True
    try:
        telegram_api_call(token, "sendMessage", {"chat_id": str(chat_id), "text": text})
        return True
    except Exception:
        return False


def format_oracle_delivery_message(payload):
    incident_type = payload.get("incident_type", "unknown")
    severity = payload.get("severity", "low")
    stage = payload.get("stage", "unknown")
    source = payload.get("source", "Supervisor")
    summary = payload.get("summary", "")
    rationale = payload.get("rationale", "")
    recommended_state = payload.get("recommended_supervisor_state", "observe")
    execute_actions = bool(payload.get("execute_actions", False))
    proposed_actions = payload.get("proposed_actions") or []
    if isinstance(proposed_actions, str):
        proposed_actions = [proposed_actions]
    elif not isinstance(proposed_actions, (list, tuple)):
        proposed_actions = [str(proposed_actions)]
    task_id = payload.get("task_id")

    lines = [
        "[ORACLE INCIDENT]",
        f"type={incident_type}",
        f"severity={severity}",
        f"stage={stage}",
        f"source={source}",
        f"task_id={task_id if task_id is not None else 'n/a'}",
        f"recommended_state={recommended_state}",
        f"execute_actions={str(execute_actions).lower()}",
    ]
    if proposed_actions:
        lines.append(f"proposed_actions={','.join(str(action) for action in proposed_actions)}")
    if summary:
        lines.append(f"summary={summary}")
    if rationale:
        lines.append(f"rationale={rationale}")
    return "\n".join(lines)[:3500]


def deliver_oracle_payload(payload_json, chat_id_override=None):
    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception as exc:
        return False, f"Invalid oracle payload: {exc}"

    authorized_chat_id = os.getenv("AUTHORIZED_CHAT_ID", "").strip()
    target_chat_id = str(chat_id_override or authorized_chat_id).strip()
    if not target_chat_id:
        return False, "Missing target chat id. Set AUTHORIZED_CHAT_ID or provide --deliver-oracle-chat-id."

    if authorized_chat_id and target_chat_id != authorized_chat_id:
        return False, "Target chat id does not match AUTHORIZED_CHAT_ID."

    token = resolve_telegram_token()
    if not token:
        return False, "Telegram token unavailable."

    message = format_oracle_delivery_message(payload)
    log_audit("ORACLE_DELIVERY_ATTEMPT", target_chat_id, payload.get("incident_type", "unknown"))
    sent = send_telegram_message(token, target_chat_id, message)
    if not sent:
        log_audit("ORACLE_DELIVERY_FAILED", target_chat_id, payload.get("incident_type", "unknown"))
        return False, "Telegram send failed."

    log_audit("ORACLE_DELIVERY_SENT", target_chat_id, payload.get("incident_type", "unknown"))
    return True, "Oracle delivery sent."


def run_polling_loop():
    offset = 0
    while True:
        token = resolve_telegram_token()
        if not token:
            time.sleep(5)
            continue

        try:
            response = telegram_api_call(token, "getUpdates", {"timeout": "25", "offset": str(offset)})
        except Exception:
            time.sleep(3)
            continue

        for item in response.get("result", []):
            update_id = item.get("update_id")
            if isinstance(update_id, int):
                offset = max(offset, update_id + 1)

            message = item.get("message") or {}
            text = message.get("text")
            chat = message.get("chat") or {}
            chat_id = chat.get("id")

            if not text or chat_id is None or not text.startswith("/"):
                continue

            reply = handle_command(chat_id, text)
            send_telegram_message(token, chat_id, reply)


def run_local_command(local_chat_id, local_command):
    reply = handle_command(local_chat_id, local_command)
    print(json.dumps({"ok": True, "reply": reply}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="UnifAI Telegram C2 bridge")
    parser.add_argument("--local-chat-id", type=str, help="Run one local command as this chat id")
    parser.add_argument("--local-command", type=str, help="Run one local command and exit")
    parser.add_argument("--deliver-oracle-json", type=str, help="Deliver an Oracle JSON payload to Telegram")
    parser.add_argument("--deliver-oracle-chat-id", type=str, help="Override destination chat id for Oracle delivery")
    args = parser.parse_args()

    if args.deliver_oracle_json is not None:
        ok, details = deliver_oracle_payload(args.deliver_oracle_json, args.deliver_oracle_chat_id)
        print(json.dumps({"ok": ok, "details": details}, ensure_ascii=False))
        raise SystemExit(0 if ok else 1)

    if args.local_chat_id is not None and args.local_command is not None:
        run_local_command(args.local_chat_id, args.local_command)
        return

    run_polling_loop()


if __name__ == "__main__":
    main()
