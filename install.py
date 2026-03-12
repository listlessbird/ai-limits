#!/usr/bin/env python3
"""Install agent-limits waybar integration.

Usage:
  python install.py           # install
  python install.py --dry-run # preview actions without writing anything
  python install.py --uninstall
"""

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent.resolve()
WAYBAR_DIR = Path.home() / ".config" / "waybar"
SCRIPTS_DIR = WAYBAR_DIR / "scripts"
ICONS_DIR = WAYBAR_DIR / "icons"

CONFIG_CANDIDATES = [
    WAYBAR_DIR / "config.jsonc",
    WAYBAR_DIR / "config.json",
    WAYBAR_DIR / "config",
]
STYLE_CANDIDATES = [WAYBAR_DIR / "style.css"]

OLD_MODULE = "custom/ai-limits"
NEW_MODULES = ("custom/codex-limits", "custom/claude-limits")
CSS_SENTINEL = "#custom-codex-limits"
OLD_CSS_SENTINEL = "#custom-ai-limits"

# ── Module definitions to inject into waybar config ───────────────────────────

CODEX_MODULE_DEF = """\
  "custom/codex-limits": {
    "exec": "~/.config/waybar/scripts/limitsbar.py codex",
    "return-type": "json",
    "interval": 300,
    "format": "{text}",
    "tooltip": true,
    "markup": true
  }"""

CLAUDE_MODULE_DEF = """\
  "custom/claude-limits": {
    "exec": "~/.config/waybar/scripts/limitsbar.py claude",
    "return-type": "json",
    "interval": 300,
    "format": "{text}",
    "tooltip": true,
    "markup": true
  }"""


def _log(msg: str, *, dry: bool = False):
    prefix = "[dry-run] " if dry else ""
    print(f"{prefix}{msg}")


def _backup(path: Path, *, dry: bool):
    backup = path.with_suffix(path.suffix + f".bak.{int(time.time())}")
    if not dry:
        shutil.copy2(path, backup)
    _log(f"  backup → {backup.name}", dry=dry)
    return backup


def _write(path: Path, content: str, *, dry: bool):
    if not dry:
        path.write_text(content, encoding="utf-8")


def _find_first(candidates: list[Path]) -> Path | None:
    return next((p for p in candidates if p.is_file()), None)


# ── Config.jsonc manipulation ─────────────────────────────────────────────────


def _find_array_bounds(text: str, key: str) -> tuple[int, int] | None:
    """Return (start, end) indices of the content inside `"key": [...]`."""
    pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*\[', re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return None
    i = m.end()
    depth = 1
    in_str = False
    esc = False
    while i < len(text):
        ch = text[i]
        if in_str:
            esc = (ch == "\\") if not esc else False
            if not esc and ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return (m.end(), i)
        i += 1
    return None


def _migrate_modules_array(text: str) -> str:
    """Replace old module name with new pair in modules-right array."""
    bounds = _find_array_bounds(text, "modules-right")
    if not bounds:
        return text
    start, end = bounds
    body = text[start:end]

    if OLD_MODULE in body:
        # Replace single old entry with two new entries
        body = re.sub(
            rf'"custom/ai-limits"',
            '"custom/codex-limits", "custom/claude-limits"',
            body,
        )
        return text[:start] + body + text[end:]

    already = all(f'"{m}"' in body for m in NEW_MODULES)
    if already:
        return text

    # Append new modules before closing bracket
    body_trimmed = body.rstrip()
    needs_comma = body_trimmed and not body_trimmed.endswith(",")
    insertion = (
        "," if needs_comma else ""
    ) + '\n    "custom/codex-limits", "custom/claude-limits"'
    return text[:start] + body_trimmed + insertion + "\n  " + text[end:]


def _remove_module_def(text: str, name: str) -> str:
    """Remove a `"name": { ... }` block (handles nested braces)."""
    pattern = re.compile(rf',?\s*"{re.escape(name)}"\s*:\s*\{{', re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return text
    i = m.end()
    depth = 1
    in_str = False
    esc = False
    while i < len(text) and depth > 0:
        ch = text[i]
        if in_str:
            esc = (ch == "\\") if not esc else False
            if not esc and ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        i += 1
    # Swallow optional trailing comma + newline
    tail = text[i:]
    tail = re.sub(r"^\s*,?\s*\n?", "\n", tail)
    return text[: m.start()] + tail


def _add_module_defs(text: str) -> str:
    """Append module definitions before the final closing brace."""
    for name, defn in [
        ("custom/codex-limits", CODEX_MODULE_DEF),
        ("custom/claude-limits", CLAUDE_MODULE_DEF),
    ]:
        # Check for a definition block (not just a reference in an array)
        if re.search(rf'"{re.escape(name)}"\s*:', text):
            continue
        trimmed = text.rstrip()
        last = trimmed.rfind("}")
        if last == -1:
            continue
        before = trimmed[:last].rstrip()
        comma = "" if before.endswith(",") or before.endswith("{") else ","
        text = before + comma + "\n" + defn + "\n" + trimmed[last:] + "\n"
    return text


def _patch_config(raw: str) -> tuple[str, list[str]]:
    """Apply all config mutations, return (new_text, list_of_changes)."""
    changes = []
    text = raw

    new_text = _migrate_modules_array(text)
    if new_text != text:
        changes.append(
            "modules-right: replaced custom/ai-limits → codex-limits + claude-limits"
        )
        text = new_text

    if OLD_MODULE in text:
        new_text = _remove_module_def(text, OLD_MODULE)
        if new_text != text:
            changes.append(f"removed old {OLD_MODULE} definition")
            text = new_text

    new_text = _add_module_defs(text)
    if new_text != text:
        changes.append("added custom/codex-limits and custom/claude-limits definitions")
        text = new_text

    return text, changes


# ── CSS manipulation ──────────────────────────────────────────────────────────


def _build_css(waybar_dir: Path) -> str:
    template = (PROJECT_DIR / "waybar" / "ai-limits.css").read_text(encoding="utf-8")
    return template.replace("{WAYBAR_DIR}", str(waybar_dir))


def _patch_style(raw: str, css_block: str) -> tuple[str, str]:
    """Return (new_style, action_description)."""
    if CSS_SENTINEL in raw:
        return raw, "already present — skipped"

    if OLD_CSS_SENTINEL in raw:
        # Find the old block: from the sentinel line to the next blank line.
        # We do NOT use re.DOTALL to avoid consuming the whole file.
        old_pattern = re.compile(
            rf"^#custom-ai-limits[\s\S]*?(?=\n\n|\Z)",
            re.MULTILINE,
        )
        new_raw = old_pattern.sub("", raw).rstrip() + "\n\n" + css_block + "\n"
        return new_raw, "replaced old #custom-ai-limits block"

    return raw.rstrip() + "\n\n" + css_block + "\n", "appended"


# ── Uninstall ─────────────────────────────────────────────────────────────────


def _uninstall(*, dry: bool):
    _log("Uninstalling agent-limits…", dry=dry)

    script = SCRIPTS_DIR / "limitsbar.py"
    if script.exists():
        _log(f"  remove {script}", dry=dry)
        if not dry:
            script.unlink()

    for icon in ("claude.svg", "openai.svg"):
        p = ICONS_DIR / icon
        if p.exists():
            _log(f"  remove {p}", dry=dry)
            if not dry:
                p.unlink()

    config = _find_first(CONFIG_CANDIDATES)
    if config:
        raw = config.read_text(encoding="utf-8")
        changed = False
        for name in (*NEW_MODULES, OLD_MODULE):
            new = _remove_module_def(raw, name)
            if new != raw:
                raw = new
                changed = True
        if changed:
            _backup(config, dry=dry)
            _log(f"  patched {config}", dry=dry)
            _write(config, raw, dry=dry)

    style = _find_first(STYLE_CANDIDATES)
    if style:
        raw = style.read_text(encoding="utf-8")
        cleaned = (
            re.sub(
                rf"(/\*.*?\*/\s*)?#{re.escape('custom-codex-limits')}.*?(?=\n\s*\n|\Z)",
                "",
                raw,
                flags=re.DOTALL,
            ).rstrip()
            + "\n"
        )
        if cleaned != raw:
            _backup(style, dry=dry)
            _log(f"  cleaned {style}", dry=dry)
            _write(style, cleaned, dry=dry)

    _log("Done.", dry=dry)


# ── Install ───────────────────────────────────────────────────────────────────


def _install(*, dry: bool):
    if not shutil.which("waybar"):
        print("ERROR: waybar not found in PATH. Install Waybar first.", file=sys.stderr)
        sys.exit(1)

    _log("Installing agent-limits…", dry=dry)

    # Dirs
    for d in (SCRIPTS_DIR, ICONS_DIR):
        if not d.exists():
            _log(f"  mkdir {d}", dry=dry)
            if not dry:
                d.mkdir(parents=True, exist_ok=True)

    # Script
    src = PROJECT_DIR / "limitsbar.py"
    dst = SCRIPTS_DIR / "limitsbar.py"
    _log(f"  install {src.name} → {dst}", dry=dry)
    if not dry:
        shutil.copy2(src, dst)
        dst.chmod(0o755)

    # Icons
    for name in ("claude.svg", "openai.svg"):
        src = PROJECT_DIR / "waybar" / "icons" / name
        dst = ICONS_DIR / name
        _log(f"  install {name} → {dst}", dry=dry)
        if not dry:
            shutil.copy2(src, dst)

    # Waybar config
    config = _find_first(CONFIG_CANDIDATES)
    if config:
        raw = config.read_text(encoding="utf-8")
        patched, changes = _patch_config(raw)
        if changes:
            _backup(config, dry=dry)
            _log(f"  patched {config}:", dry=dry)
            for c in changes:
                _log(f"    • {c}", dry=dry)
            _write(config, patched, dry=dry)
        else:
            _log(f"  {config}: nothing to change", dry=dry)
    else:
        _log(
            "  WARNING: no waybar config found — merge waybar/ai-limits.jsonc manually",
            dry=dry,
        )

    # Style
    style = _find_first(STYLE_CANDIDATES)
    if style:
        raw = style.read_text(encoding="utf-8")
        css = _build_css(WAYBAR_DIR)
        patched_style, action = _patch_style(raw, css)
        _log(f"  style.css: {action}", dry=dry)
        if patched_style != raw:
            _backup(style, dry=dry)
            _write(style, patched_style, dry=dry)
    else:
        _log(
            "  WARNING: no style.css found — add waybar/ai-limits.css contents manually",
            dry=dry,
        )

    _log("Done. Reload Waybar: killall -SIGUSR2 waybar", dry=dry)


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview actions without writing anything",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove installed files and config patches",
    )
    args = parser.parse_args()

    if args.uninstall:
        _uninstall(dry=args.dry_run)
    else:
        _install(dry=args.dry_run)


if __name__ == "__main__":
    main()
