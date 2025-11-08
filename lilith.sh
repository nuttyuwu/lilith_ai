#!/bin/bash
# Lilith one-command launcher 🖤 (CLI version)

if [ -d "$HOME/Lilith_ai" ]; then
  BASE_DIR="$HOME/Lilith_ai"
else
  BASE_DIR="$HOME/lilith_ai"
fi
SERVER_URL="http://localhost:1234/v1/models"
LMS_PATH="$HOME/.lmstudio/bin/lms" 

echo "🌙 Waking up Lilith's mind..."

# Start LM Studio server via CLI if not running
if curl -s "$SERVER_URL" >/dev/null 2>&1; then
    echo "Server already running."
else

    lms server start >/dev/null 2>&1 &
fi

# Wait until API is reachable
echo -n "Waiting for Lilith's consciousness"
for i in {1..40}; do
    if curl -s "$SERVER_URL" >/dev/null 2>&1; then
        echo " ✓"
        break
    fi
    echo -n "."
    sleep 1
done
echo

# Activate virtual environment
source "$BASE_DIR/venv/bin/activate"

# Run Lilith terminal
echo "🖤 Lilith is awakening..."
python "$BASE_DIR/lilith.py"

# When you exit Lilith, close LM Studio
echo "💤 Putting Lilith to sleep..."
pkill -f "LM-Studio-0.3.30-2-x64.AppImage" 
