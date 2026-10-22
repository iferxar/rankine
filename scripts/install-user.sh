#!/bin/sh
# Adds Rankine to the app menu for the current user, running from this checkout.
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)
bin="$HOME/.local/bin"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$bin" "$apps" "$icons"

cat > "$bin/rankine" <<LAUNCHER
#!/bin/sh
PYTHONPATH="$repo\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m rankine "\$@"
LAUNCHER
chmod 755 "$bin/rankine"

# Absolute Exec: ~/.local/bin is not always on the graphical session's PATH.
sed "s|^Exec=rankine|Exec=$bin/rankine|" "$repo/data/rankine.desktop" > "$apps/rankine.desktop"
install -m644 "$repo/rankine/icons/rankine.svg" "$icons/rankine.svg"

command -v update-desktop-database >/dev/null && update-desktop-database "$apps" || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
echo "Installed: $bin/rankine, $apps/rankine.desktop"
