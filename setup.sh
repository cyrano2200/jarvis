#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "==== Jarvis setup (Linux/macOS) ===="
command -v python3 >/dev/null || { echo "Python 3.10+ required"; exit 1; }
if [[ "$OSTYPE" == "darwin"* ]]; then
  command -v brew >/dev/null && brew install portaudio || echo "Install Homebrew, then: brew install portaudio"
elif command -v apt-get >/dev/null; then
  sudo apt-get update && sudo apt-get install -y python3-venv python3-tk portaudio19-dev espeak-ng ffmpeg playerctl brightnessctl xdotool libgirepository1.0-dev || true
fi
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt || echo "Some packages failed - Jarvis still works in --text mode."
[ -f .env ] || cp .env.example .env
cat > run_jarvis.sh <<'EOS'
#!/usr/bin/env bash
cd "$(dirname "$0")" && source venv/bin/activate && python jarvis.py "$@"
EOS
chmod +x run_jarvis.sh
echo; echo "Done. Test: ./run_jarvis.sh --check   Run: ./run_jarvis.sh   (tray: ./run_jarvis.sh --tray)"
