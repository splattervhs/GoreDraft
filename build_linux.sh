#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
$PY -m pip install -r requirements.txt pyinstaller
$PY -m PyInstaller --noconfirm --windowed --name GoreDraft --icon goredraft/icon.png \
  --add-data "goredraft/fonts:goredraft/fonts" --add-data "goredraft/icon.png:goredraft" --add-data "goredraft/splash.jpg:goredraft" --collect-data spellchecker run.py
echo "Done: dist/GoreDraft/GoreDraft"

# package: tarball with a launcher + desktop entry installer
VER=$($PY -c "from goredraft.model import APP_VERSION; print(APP_VERSION)")
cp goredraft/icon.png dist/GoreDraft/goredraft.png
cat > dist/GoreDraft/install.sh <<'INS'
#!/usr/bin/env bash
# Adds GORE DRAFT to your applications menu (no root needed).
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/goredraft.desktop <<DESK
[Desktop Entry]
Type=Application
Name=GORE DRAFT
Comment=Screenwriting for practical horror filmmakers
Exec="$DIR/GoreDraft" %f
Icon=$DIR/goredraft.png
Categories=Office;AudioVideo;
MimeType=application/x-goredraft;
DESK
echo "Installed. Find GORE DRAFT in your applications menu."
INS
chmod +x dist/GoreDraft/install.sh
tar -C dist -czf "dist/GoreDraft-$VER-linux-x86_64.tar.gz" GoreDraft
echo "Package: dist/GoreDraft-$VER-linux-x86_64.tar.gz"
