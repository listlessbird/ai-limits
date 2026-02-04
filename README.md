# AI Limits Waybar Module

Single Waybar widget that shows Codex (daily/weekly) and Claude (session/weekly) limits.

## Files
- `limitsbar.py`: Combined script that outputs Waybar JSON.
- `waybar/ai-limits.jsonc`: Config fragment for the module.
- `waybar/ai-limits.css`: Style fragment.
- `load.sh`: Installs the script and auto-merges Waybar config/styles safely.

## Install
```bash
./load.sh
```

The installer will:
- Copy the script into `~/.config/waybar/scripts/limitsbar.py`
- Drop config/style fragments into `~/.config/waybar/`
- Insert `custom/ai-limits` into your Waybar config without reformatting it
- Append styles if missing

Then reload Waybar:
```bash
pkill -SIGUSR2 waybar
# or
systemctl --user restart waybar
```

## Notes
- Codex requires `~/.codex/auth.json` from `codex login`.
- Claude requires `~/.claude/.credentials.json` with `user:profile` scope from `claude login`.
- Claude usage is fetched via `https://api.anthropic.com/api/oauth/usage` using the CLI OAuth token.
- Codex usage defaults to `https://chatgpt.com/backend-api/wham/usage` 

