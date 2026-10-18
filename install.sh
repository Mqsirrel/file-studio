#!/usr/bin/env bash
set -e

echo "=== Installing File Studio (Obsidian & Cobalt Slate) ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
SERVICE_MENUS_DIR="$HOME/.local/share/kio/servicemenus"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$SERVICE_MENUS_DIR" "$SYSTEMD_USER_DIR"

# 1. Setup virtual environment if missing
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv --system-site-packages "$SCRIPT_DIR/.venv"
    "$SCRIPT_DIR/.venv/bin/pip" install -q -U pip
    "$SCRIPT_DIR/.venv/bin/pip" install -q pymupdf pyvips pillow pillow-heif python-docx pypdf
fi

# 2. Install launcher binary
cat << EOF > "$BIN_DIR/convertwheel"
#!/bin/sh
export QT_QPA_PLATFORM="\${QT_QPA_PLATFORM:-xcb}"
export VIPS_WARNING=0
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/run.py" "\$@"
EOF
chmod +x "$BIN_DIR/convertwheel"
ln -sf "$BIN_DIR/convertwheel" "$BIN_DIR/file-studio"

# 3. Install desktop file
cat << EOF > "$DESKTOP_DIR/convertwheel.desktop"
[Desktop Entry]
Type=Application
Name=File Studio
GenericName=Intelligent File Converter & Studio
Comment=Convert, compress, crop, frame, annotate, redact, and inspect files
Exec=$BIN_DIR/convertwheel --studio %F
Icon=applications-graphics
Terminal=false
Categories=Utility;Graphics;Office;AudioVideo;
MimeType=image/png;image/jpeg;image/webp;image/avif;image/heic;image/bmp;image/tiff;image/gif;image/svg+xml;application/pdf;video/mp4;video/x-matroska;video/webm;audio/mpeg;audio/wav;audio/flac;application/zip;
EOF

# 4. Install KDE ServiceMenus
cp -f "$SCRIPT_DIR/servicemenus/"*.desktop "$SERVICE_MENUS_DIR/"
chmod +x "$SERVICE_MENUS_DIR/"*.desktop

# 5. Install systemd user service
cat << EOF > "$SYSTEMD_USER_DIR/convertwheel.service"
[Unit]
Description=File Studio (Obsidian & Cobalt Slate) – Intelligent File Studio & Converter
After=graphical-session.target

[Service]
Type=simple
Environment=QT_QPA_PLATFORM=xcb
Environment=XDG_CURRENT_DESKTOP=KDE
Environment=QT_QPA_PLATFORMTHEME=kde
Environment=VIPS_WARNING=0
ExecStart=$BIN_DIR/convertwheel
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF

# 6. Reload KDE cache and restart service
kbuildsycoca6 --noincremental 2>/dev/null || true
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable --now convertwheel.service 2>/dev/null || true

echo "✓ File Studio successfully installed and running!"
echo "  - Launcher: $BIN_DIR/convertwheel"
echo "  - Right-click: Available in KDE Dolphin context menus"
echo "  - Daemon: systemctl --user status convertwheel"
