# AI Limits Waybar Module

![Waybar module preview](assets/shot.png)

Single Waybar widget that shows Codex (5‑hour + weekly) and Claude (5‑hour + weekly) limits.

## Install
```bash
python install.py
```

Preview without writing anything:
```bash
python install.py --dry-run
```

Uninstall:
```bash
python install.py --uninstall
```

The installer will:
- Copy `limitsbar.py` to `~/.config/waybar/scripts/limitsbar.py`
- Copy SVG icons to `~/.config/waybar/icons/`
- Inject `custom/codex-limits` and `custom/claude-limits` module definitions into your Waybar config
- Append styles to `style.css` if missing

Then reload Waybar:
```bash
killall -SIGUSR2 waybar
```

## Notes
- Codex requires `~/.codex/auth.json` from `codex login`.
- Claude requires `~/.claude/.credentials.json` with `user:profile` scope from `claude login`.
- Claude usage is fetched via `https://api.anthropic.com/api/oauth/usage` using the CLI OAuth token.
- Codex usage defaults to `https://chatgpt.com/backend-api/wham/usage`