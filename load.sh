#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAYBAR_BIN="$(command -v waybar || true)"

if [[ -z "$WAYBAR_BIN" ]]; then
  echo "Waybar not found in PATH. Install Waybar first." >&2
  exit 1
fi

WAYBAR_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/waybar"
SCRIPT_DIR="$WAYBAR_DIR/scripts"

mkdir -p "$SCRIPT_DIR"
install -m 755 "$PROJECT_DIR/codexbar.py" "$SCRIPT_DIR/codexbar.py"

# Drop config/style fragments to merge manually or via markers.
install -m 644 "$PROJECT_DIR/waybar/codexbar.jsonc" "$WAYBAR_DIR/codexbar.jsonc"
install -m 644 "$PROJECT_DIR/waybar/codexbar.css" "$WAYBAR_DIR/codexbar.css"

CONFIG_CANDIDATES=("$WAYBAR_DIR/config" "$WAYBAR_DIR/config.jsonc" "$WAYBAR_DIR/config.json")
STYLE_CANDIDATES=("$WAYBAR_DIR/style.css")

CONFIG_FILE=""
for f in "${CONFIG_CANDIDATES[@]}"; do
  if [[ -f "$f" ]]; then
    CONFIG_FILE="$f"
    break
  fi
done

STYLE_FILE=""
for f in "${STYLE_CANDIDATES[@]}"; do
  if [[ -f "$f" ]]; then
    STYLE_FILE="$f"
    break
  fi
done

echo "Installed codexbar script to: $SCRIPT_DIR/codexbar.py"
echo "Config fragment: $WAYBAR_DIR/codexbar.jsonc"
echo "Style fragment:  $WAYBAR_DIR/codexbar.css"

if [[ -n "$CONFIG_FILE" ]]; then
  echo "Detected Waybar config: $CONFIG_FILE"

  python3 - "$CONFIG_FILE" <<'PY'
import re
import sys
import time
from pathlib import Path

config_path = Path(sys.argv[1])
raw = config_path.read_text(encoding="utf-8")

if "custom/codex" in raw:
    print("custom/codex already present in config; no merge needed.")
    raise SystemExit(0)

module_block = (
    '  "custom/codex": {\n'
    '    "exec": "~/.config/waybar/scripts/codexbar.py",\n'
    '    "return-type": "json",\n'
    '    "interval": 300,\n'
    '    "format": "{icon} {text}",\n'
    '    "format-icons": ["󰄬", "󰄭", "󰄮", "󰄯", "󰄰"],\n'
    '    "tooltip": true\n'
    '  }\n'
)

# Insert module definition before the final closing brace
trimmed = raw.rstrip()
last_brace = trimmed.rfind('}')
if last_brace == -1:
    print("Failed to find top-level closing brace. Please merge codexbar.jsonc manually.")
    raise SystemExit(2)

# Ensure a trailing comma before inserting
before = trimmed[:last_brace].rstrip()
needs_comma = not before.endswith(',') and not before.endswith('{')
insert = (',' if needs_comma else '') + '\n' + module_block
merged = before + insert + '\n' + trimmed[last_brace:]

# Insert module into modules-right array if present
pattern = re.compile(r'("modules-right"\s*:\s*\[)', re.MULTILINE)
match = pattern.search(merged)
if match:
    start = match.end()
    # Parse to matching closing bracket, respecting strings
    i = start
    depth = 1
    in_string = False
    escape = False
    while i < len(merged):
        ch = merged[i]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        i += 1
    else:
        end = None

    if end is not None:
        array_body = merged[start:end]
        if "custom/codex" not in array_body:
            # Determine indentation from existing entries
            lines = array_body.splitlines()
            indent = "  "
            for line in lines:
                if line.strip().startswith('"'):
                    indent = re.match(r'(\s*)', line).group(1)
                    break
            insertion = ("\n" if array_body.strip() else "") + f"{indent}\"custom/codex\""
            # Add comma if needed before closing
            body_trim = array_body.rstrip()
            if body_trim and not body_trim.rstrip().endswith(','):
                body_trim = body_trim.rstrip() + ','
            new_body = body_trim + insertion + ("\n" if array_body.endswith("\n") else "")
            merged = merged[:start] + new_body + merged[end:]

# Backup then write
backup = config_path.with_suffix(config_path.suffix + f".bak.{int(time.time())}")
backup.write_text(raw, encoding="utf-8")
config_path.write_text(merged + ("\n" if not merged.endswith("\n") else ""), encoding="utf-8")

print(f"Updated {config_path} (backup: {backup.name})")
PY
else
  echo "No Waybar config detected. Create one and merge codexbar.jsonc."
fi

if [[ -n "$STYLE_FILE" ]]; then
  echo "Detected Waybar style: $STYLE_FILE"
  if ! grep -q "#custom-codex" "$STYLE_FILE"; then
    printf "\n%s\n" "$(cat "$WAYBAR_DIR/codexbar.css")" >> "$STYLE_FILE"
    echo "Appended Codex styles to $STYLE_FILE"
  else
    echo "Codex styles already present in $STYLE_FILE"
  fi
else
  echo "No style.css detected. Create one and add codexbar.css contents."
fi

