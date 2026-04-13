#!/bin/zsh
# StudioZero Launcher — activates venv and starts the web dashboard

PROJECT_DIR="$HOME/Personal/code_projects/StudioZero"
VENV="$HOME/Personal/code_projects/.venv"

cd "$PROJECT_DIR" || { echo "ERROR: Project folder not found at $PROJECT_DIR"; read; exit 1; }

source "$VENV/bin/activate" || { echo "ERROR: Could not activate venv at $VENV"; read; exit 1; }

echo "Starting StudioZero Web Dashboard..."
echo "Opening browser at http://localhost:8910"
echo ""

python -m src.server_launcher

echo ""
echo "StudioZero has stopped. Press any key to close."
read -k 1
