#!/bin/sh
# Installs the rankine-tuned system service from this checkout (run with sudo).
# The code is copied to a root-owned directory: a root service must never run files the user can edit.
# Does not enable the service; afterwards run: sudo systemctl enable --now rankine-tuned.service
# Remove with: sudo scripts/install-tuned.sh --uninstall
set -eu
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
repo=$(cd "$(dirname "$0")/.." && pwd)
lib=/usr/local/lib/rankine-tuned
bin=/usr/local/bin/rankine-tuned
unit=/etc/systemd/system/rankine-tuned.service
policy=/etc/dbus-1/system.d/io.github.iferxar.Rankine.Tuned.conf
# polkit only reads actions from /usr/share; this file is not owned by any package.
actions=/usr/share/polkit-1/actions/io.github.iferxar.Rankine.Tuned.policy

if [ "${1:-}" = "--uninstall" ]; then
    systemctl disable --now rankine-tuned.service 2>/dev/null || true
    rm -rf "$lib" "$bin" "$unit" "$policy" "$actions"
    systemctl daemon-reload
    systemctl reload dbus.service || true
    echo "Removed rankine-tuned."
    exit 0
fi

rm -rf "$lib"
mkdir -p "$lib"
cp -r "$repo/rankine" "$lib/"
find "$lib" -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root "$lib"
chmod -R u=rwX,go=rX "$lib"
python3 -m compileall -q "$lib"

# -I ignores PYTHONPATH and the user's site-packages, so only the root-owned copy is imported.
cat > "$bin" <<LAUNCHER
#!/bin/sh
exec python3 -I -c 'import sys; sys.path.insert(0, "$lib"); from rankine.tuned.service import main; sys.exit(main())' "\$@"
LAUNCHER
chmod 755 "$bin"

sed "s|/usr/bin/rankine-tuned|$bin|" "$repo/data/systemd/rankine-tuned.service" > "$unit"
install -m644 "$repo/data/dbus/io.github.iferxar.Rankine.Tuned.conf" "$policy"
install -Dm644 "$repo/data/polkit/io.github.iferxar.Rankine.Tuned.policy" "$actions"
systemctl daemon-reload
systemctl reload dbus.service || true
if systemctl is-active --quiet rankine-tuned.service; then
    systemctl restart rankine-tuned.service
    echo "Updated and restarted rankine-tuned."
else
    echo "Installed rankine-tuned. Enable it with: sudo systemctl enable --now rankine-tuned.service"
fi
