#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "🔨 Building Dudum Dashboard.app..."

.venv/bin/pyinstaller \
  --name "Dudum Dashboard" \
  --windowed \
  --onedir \
  --noconfirm \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --hidden-import "flask" \
  --hidden-import "webview" \
  --hidden-import "webview.platforms.cocoa" \
  --hidden-import "requests" \
  --hidden-import "sqlite3" \
  app.py

echo ""
echo "✅ Done! App is at: dist/Dudum Dashboard.app"
echo "   Drag it to your Applications folder or double-click to run."
