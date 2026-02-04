# Codex Waybar Module

Custom Waybar module that shows Codex daily + weekly usage from your local Codex auth.

## Files
- `codexbar.py`: Script that outputs Waybar JSON.
- `waybar/codexbar.jsonc`: Config fragment for the module.
- `waybar/codexbar.css`: Style fragment.
- `load.sh`: Installs the script and auto-merges Waybar config/styles safely.

## Install
```bash
./load.sh
```

The installer will:
- Copy the script into `~/.config/waybar/scripts/codexbar.py`
- Drop config/style fragments into `~/.config/waybar/`
- Insert `custom/codex` into your Waybar config without reformatting it
- Append styles if missing

Then reload Waybar:
```bash
pkill -SIGUSR2 waybar
# or
systemctl --user restart waybar
```

## Notes
- Requires `~/.codex/auth.json` from `codex login`.
- Refreshes the OAuth token if `last_refresh` is older than 8 days.