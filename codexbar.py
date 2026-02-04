#!/usr/bin/env python3
import json
import os
import sys
import time
import datetime
import urllib.request
import urllib.error

AUTH_REFRESH_INTERVAL_SECONDS = 8 * 24 * 60 * 60
DEFAULT_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
REFRESH_URL = "https://auth.openai.com/oauth/token"
REFRESH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_iso8601(value):
    if not value:
        return None
    try:
        # Handle Z suffix
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(value)
    except Exception:
        return None


def _auth_path():
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return os.path.join(codex_home, "auth.json")
    return os.path.join(os.path.expanduser("~"), ".codex", "auth.json")


def _read_auth():
    path = _auth_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"auth.json not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f), path


def _write_auth(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _needs_refresh(last_refresh):
    if last_refresh is None:
        return True
    age = (_now_utc() - last_refresh).total_seconds()
    return age > AUTH_REFRESH_INTERVAL_SECONDS


def _refresh_tokens(refresh_token):
    payload = {
        "client_id": REFRESH_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "openid profile email",
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        REFRESH_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def _fetch_usage(access_token, account_id=None):
    url = os.environ.get("CODEX_USAGE_URL", DEFAULT_USAGE_URL)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "codex-cli",
        "Accept": "application/json",
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def _format_reset(ts):
    if not ts:
        return "unknown"
    try:
        dt = datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc)
    except Exception:
        return "unknown"
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def _format_eta(ts):
    if not ts:
        return "unknown"
    try:
        target = datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc)
    except Exception:
        return "unknown"
    delta = target - _now_utc()
    total = int(delta.total_seconds())
    if total <= 0:
        return "now"
    hours = total // 3600
    minutes = (total % 3600) // 60
    return f"{hours}h {minutes}m"


def _class_for(percent):
    if percent is None:
        return "unknown"
    if percent >= 90:
        return "critical"
    if percent >= 70:
        return "warn"
    return "ok"


def _emit(payload):
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))
    sys.stdout.flush()


def main():
    try:
        auth, path = _read_auth()
        tokens = auth.get("tokens") or {}
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        account_id = tokens.get("account_id")

        if not access_token:
            raise RuntimeError("Missing access_token in auth.json")

        last_refresh = _parse_iso8601(auth.get("last_refresh"))

        if refresh_token and _needs_refresh(last_refresh):
            refreshed = _refresh_tokens(refresh_token)
            tokens["access_token"] = refreshed.get("access_token", access_token)
            tokens["refresh_token"] = refreshed.get("refresh_token", refresh_token)
            if refreshed.get("id_token"):
                tokens["id_token"] = refreshed.get("id_token")
            auth["tokens"] = tokens
            auth["last_refresh"] = _now_utc().isoformat().replace("+00:00", "Z")
            _write_auth(path, auth)
            access_token = tokens.get("access_token")

        usage = _fetch_usage(access_token, account_id)
        rate_limit = usage.get("rate_limit") or {}
        primary = rate_limit.get("primary_window") or {}
        secondary = rate_limit.get("secondary_window") or {}

        daily_percent = primary.get("used_percent")
        weekly_percent = secondary.get("used_percent")

        daily_reset = primary.get("reset_at")
        weekly_reset = secondary.get("reset_at")

        daily_text = "--" if daily_percent is None else f"{int(daily_percent)}%"
        weekly_text = "--" if weekly_percent is None else f"{int(weekly_percent)}%"

        text = f"D {daily_text} · W {weekly_text}"
        top_percent = None
        for p in [daily_percent, weekly_percent]:
            if p is None:
                continue
            if top_percent is None or p > top_percent:
                top_percent = p

        tooltip_lines = [
            f"Daily used: {daily_text}",
            f"Daily reset: {_format_reset(daily_reset)} ({_format_eta(daily_reset)})",
            f"Weekly used: {weekly_text}",
            f"Weekly reset: {_format_reset(weekly_reset)} ({_format_eta(weekly_reset)})",
            f"Updated: {_now_utc().astimezone().strftime('%Y-%m-%d %H:%M')}"
        ]
        tooltip = "\r".join(tooltip_lines)

        payload = {
            "text": text,
            "tooltip": tooltip,
            "class": _class_for(top_percent),
            "percentage": int(top_percent) if top_percent is not None else 0,
            "alt": "codex",
        }
        _emit(payload)
    except urllib.error.HTTPError as e:
        _emit({
            "text": "Codex --",
            "tooltip": f"HTTP error: {e.code}",
            "class": "error",
            "percentage": 0,
            "alt": "codex",
        })
    except Exception as e:
        _emit({
            "text": "Codex --",
            "tooltip": f"Error: {e}",
            "class": "error",
            "percentage": 0,
            "alt": "codex",
        })


if __name__ == "__main__":
    main()
