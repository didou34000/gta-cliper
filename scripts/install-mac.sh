#!/bin/bash
# Installe et lance le bot GTA Clipper sur un Mac, sans droits administrateur.
#  - uv (gestionnaire Python) + Python 3.12 dans un environnement isolé (.venv)
#  - ffmpeg / ffprobe (Homebrew s'il est là, sinon binaires statiques dans ./bin)
#  - un service launchd qui lance « python -m gta_clipper loop » au démarrage de la session
#    et le relance s'il plante. Le Mac ne se met pas en veille tant que le bot tourne
#    (sauf capot fermé sur batterie).
# Relancer ce script ne casse rien : il refait seulement ce qui manque.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LABEL="com.gtaclipper.bot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p bin data logs

echo "== 1/5 Python (uv) =="
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
"$UV" python install 3.12
[ -d .venv ] || "$UV" venv --python 3.12 .venv
"$UV" pip install --python .venv/bin/python -r requirements.txt

echo "== 2/5 ffmpeg =="
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  echo "ffmpeg déjà installé : $(command -v ffmpeg)"
elif command -v brew >/dev/null 2>&1; then
  brew install ffmpeg
else
  ARCH="$(uname -m)"
  if [ "$ARCH" = "arm64" ]; then
    for t in ffmpeg ffprobe; do
      [ -x "bin/$t" ] || { curl -fL "https://www.osxexperts.net/${t}80arm.zip" -o "/tmp/$t.zip" && unzip -o -q "/tmp/$t.zip" -d bin; }
    done
  else
    for t in ffmpeg ffprobe; do
      [ -x "bin/$t" ] || { curl -fL "https://evermeet.cx/ffmpeg/getrelease/$t/zip" -o "/tmp/$t.zip" && unzip -o -q "/tmp/$t.zip" -d bin; }
    done
  fi
  chmod +x bin/ffmpeg bin/ffprobe
  xattr -d com.apple.quarantine bin/ffmpeg bin/ffprobe 2>/dev/null || true
fi
export PATH="$ROOT/bin:$PATH"
ffmpeg -hide_banner -version | head -1
# deno : yt-dlp en a besoin pour télécharger depuis YouTube (mode « lien YouTube »)
if ! command -v deno >/dev/null 2>&1 && [ ! -x "$HOME/.deno/bin/deno" ]; then
  if command -v brew >/dev/null 2>&1; then brew install deno; else curl -fsSL https://deno.land/install.sh | sh -s -- -y; fi
fi
export PATH="$HOME/.deno/bin:$PATH"

echo "== 3/5 Configuration =="
[ -f config.yaml ] || cp config.example.yaml config.yaml
[ -f .env ] || cp .env.example .env
# Police des sous-titres : Arial Black existe sur tous les Mac.
grep -q "^  font:" config.yaml && sed -i '' 's/^  font: .*/  font: "Arial Black"/' config.yaml || true

echo "== 4/5 Vérification =="
MISSING=""
for k in TWITCH_CLIENT_ID TWITCH_CLIENT_SECRET R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_PUBLIC_URL ANTHROPIC_API_KEY; do
  grep -Eq "^$k=.+" .env || MISSING="$MISSING $k"
done
.venv/bin/python -c "import gta_clipper.pipeline, yt_dlp, faster_whisper, anthropic; print('Modules OK')"
if grep -Eq "^R2_SECRET_ACCESS_KEY=.+" .env; then
  .venv/bin/python -m gta_clipper site-test || echo "!! Le test de liaison avec le site a échoué"
fi

echo "== 5/5 Service permanent (launchd) =="
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/caffeinate</string><string>-is</string>
    <string>$ROOT/.venv/bin/python</string><string>-m</string><string>gta_clipper</string>
    <string>loop</string><string>--every</string><string>60</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$ROOT/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>300</integer>
  <key>StandardOutPath</key><string>$ROOT/logs/bot.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/bot.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ -n "$MISSING" ] && echo "$MISSING" | grep -q "TWITCH_CLIENT_SECRET\|R2_SECRET_ACCESS_KEY"; then
  echo ""
  echo "!! Il manque dans .env :$MISSING"
  echo "   Le service est prêt mais PAS démarré. Complète .env puis relance : bash scripts/install-mac.sh"
  exit 2
fi
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo ""
echo "Bot lancé en tâche de fond. Suivi : https://gta-clipper.vercel.app  ·  logs : $ROOT/logs/bot.log"
echo "Arrêt d'urgence : touch $ROOT/STOP   ·   Désinstaller : launchctl bootout gui/\$(id -u)/$LABEL"
[ -n "$MISSING" ] && echo "(Sans ANTHROPIC_API_KEY, les titres seront provisoires.)" || true
