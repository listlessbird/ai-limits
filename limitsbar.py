#!/usr/bin/env python3
import datetime
import json
import os
import sys
import time
import urllib.request
import urllib.error

AUTH_REFRESH_INTERVAL_SECONDS = 8 * 24 * 60 * 60
DEFAULT_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
REFRESH_URL = "https://auth.openai.com/oauth/token"
REFRESH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

ICON_FIVE_HOUR = "󱦟"
ICON_WEEKLY = "󰃮"

ICON_CLAUDE = '<span font="bootstrap-icons">\uf914</span>'
ICON_OPENAI = '<span font="bootstrap-icons">\uf915</span>'

BRAND_COLOR_CLAUDE = "#da7756"
BRAND_COLOR_OPENAI = "#ffffff"


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_iso8601(value):
    if not value:
        return None
    try:
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


def _format_reset_dt(dt):
    if not dt:
        return "unknown", "unknown"
    try:
        ts = int(dt.timestamp())
    except Exception:
        return "unknown", "unknown"
    return _format_reset(ts), _format_eta(ts)


def _class_for(percent):
    if percent is None:
        return "unknown"
    if percent >= 90:
        return "critical"
    if percent >= 70:
        return "warn"
    return "ok"


def _brand_span(text, color):
    return f'<span foreground="{color}">{text}</span>'


def _claude_credentials_path():
    return os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")


def _read_claude_credentials():
    path = _claude_credentials_path()
    if not os.path.exists(path):
        raise FileNotFoundError("Claude credentials not found")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    inner = data.get("claudeAiOauth") or {}
    return inner, path


def _parse_claude_resets(value):
    if not value:
        return None
    # Example: 2026-02-04T10:59:59.868195+00:00
    dt = _parse_iso8601(value)
    return dt


def _claude_usage_percent(utilization):
    if utilization is None:
        return None
    try:
        val = float(utilization)
    except Exception:
        return None
    if val <= 1.0:
        return int(round(val * 100))
    return int(round(val))


def _get_claude_status():
    try:
        cred, _ = _read_claude_credentials()
    except FileNotFoundError:
        return None, "Claude credentials not found (run `claude login`)"

    access = cred.get("accessToken")
    scopes = cred.get("scopes") or []
    expires_at = cred.get("expiresAt")

    if not access:
        return None, "Claude access token missing"
    if "user:profile" not in scopes:
        return None, "Claude token missing user:profile scope"
    if isinstance(expires_at, (int, float)) and expires_at > 0:
        exp_dt = datetime.datetime.fromtimestamp(expires_at / 1000, tz=datetime.timezone.utc)
        if _now_utc() >= exp_dt:
            return None, "Claude token expired (run `claude login`)"

    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {access}",
            "anthropic-beta": "oauth-2025-04-20",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return None, f"Claude HTTP error: {e.code}"
    except Exception as e:
        return None, f"Claude error: {e}"

    five_hour = data.get("five_hour") or {}
    seven_day = data.get("seven_day") or {}

    session_percent = _claude_usage_percent(five_hour.get("utilization"))
    week_percent = _claude_usage_percent(seven_day.get("utilization"))
    session_reset = _parse_claude_resets(five_hour.get("resets_at"))
    week_reset = _parse_claude_resets(seven_day.get("resets_at"))

    if session_percent is None and week_percent is None:
        return None, "Claude usage unavailable"

    return {
        "session_percent": session_percent,
        "week_percent": week_percent,
        "session_reset": session_reset,
        "week_reset": week_reset,
    }, None


def _get_codex_status():
    try:
        auth, path = _read_auth()
        tokens = auth.get("tokens") or {}
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        account_id = tokens.get("account_id")
        if not access_token:
            return None, "Codex auth.json missing access token"

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

        return {
            "daily_percent": primary.get("used_percent"),
            "weekly_percent": secondary.get("used_percent"),
            "daily_reset": primary.get("reset_at"),
            "weekly_reset": secondary.get("reset_at"),
        }, None
    except FileNotFoundError:
        return None, "Codex auth.json not found (run `codex login`)"
    except urllib.error.HTTPError as e:
        return None, f"Codex HTTP error: {e.code}"
    except Exception as e:
        return None, f"Codex error: {e}"


def _emit(payload):
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))
    sys.stdout.flush()


def _build_codex_payload(codex, codex_err):
    percents = []
    tooltip_lines = ["Codex (OpenAI)", ""]

    if codex:
        d = codex.get("daily_percent")
        w = codex.get("weekly_percent")
        if d is not None:
            percents.append(d)
        if w is not None:
            percents.append(w)

        d_text = "--" if d is None else f"{int(d)}%"
        w_text = "--" if w is None else f"{int(w)}%"
        cls = _class_for(max((v for v in [d, w] if v is not None), default=None))
        text = _brand_span(f"{ICON_FIVE_HOUR} {d_text} {ICON_WEEKLY} {w_text}", BRAND_COLOR_OPENAI)
        tooltip_lines.append(
            f"5h: {d_text} (resets {_format_reset(codex.get('daily_reset'))}, {_format_eta(codex.get('daily_reset'))})"
        )
        tooltip_lines.append(
            f"Weekly: {w_text} (resets {_format_reset(codex.get('weekly_reset'))}, {_format_eta(codex.get('weekly_reset'))})"
        )
    else:
        return {"text": ""}

    top_percent = max(percents) if percents else None
    tooltip_lines += ["", f"Updated: {_now_utc().astimezone().strftime('%Y-%m-%d %H:%M')}", "Refresh: every 5 minutes"]
    return {"text": text, "tooltip": "\r".join(tooltip_lines), "class": cls, "percentage": int(top_percent) if top_percent is not None else 0, "alt": "codex-limits"}


def _build_claude_payload(claude, claude_err):
    percents = []
    tooltip_lines = ["Claude (Anthropic)", ""]

    if claude:
        s = claude.get("session_percent")
        w = claude.get("week_percent")
        if s is not None:
            percents.append(s)
        if w is not None:
            percents.append(w)

        s_text = "--" if s is None else f"{int(s)}%"
        w_text = "--" if w is None else f"{int(w)}%"
        cls = _class_for(max((v for v in [s, w] if v is not None), default=None))
        text = _brand_span(f"{ICON_FIVE_HOUR} {s_text} {ICON_WEEKLY} {w_text}", BRAND_COLOR_CLAUDE)
        s_reset, s_eta = _format_reset_dt(claude.get("session_reset"))
        w_reset, w_eta = _format_reset_dt(claude.get("week_reset"))
        tooltip_lines.append(f"5h: {s_text} (resets {s_reset}, {s_eta})")
        tooltip_lines.append(f"Weekly: {w_text} (resets {w_reset}, {w_eta})")
    else:
        return {"text": ""}

    top_percent = max(percents) if percents else None
    tooltip_lines += ["", f"Updated: {_now_utc().astimezone().strftime('%Y-%m-%d %H:%M')}", "Refresh: every 5 minutes"]
    return {"text": text, "tooltip": "\r".join(tooltip_lines), "class": cls, "percentage": int(top_percent) if top_percent is not None else 0, "alt": "claude-limits"}


def main():
    service = sys.argv[1] if len(sys.argv) > 1 else ""

    if service == "codex":
        codex, codex_err = _get_codex_status()
        _emit(_build_codex_payload(codex, codex_err))
    elif service == "claude":
        claude, claude_err = _get_claude_status()
        _emit(_build_claude_payload(claude, claude_err))
    else:
        print(f"Usage: {sys.argv[0]} codex|claude", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
