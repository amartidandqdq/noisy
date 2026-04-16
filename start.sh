#!/usr/bin/env bash
# start.sh - One-click launcher pour macOS/Linux
# Cree le venv, installe les deps, lance Noisy + Dashboard

set -e

cd "$(dirname "$0")"

echo ""
echo "  ========================================"
echo "   NOISY - Traffic Noise Generator"
echo "  ========================================"
echo ""

# Detect Python
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "  [ERREUR] Python 3 n'est pas installe."
    echo "  macOS  : brew install python3   (ou) https://www.python.org/downloads/"
    echo "  Linux  : sudo apt install python3 python3-venv"
    echo ""
    read -n 1 -s -r -p "Appuie sur une touche pour quitter..."
    exit 1
fi

# Create venv if missing
if [ ! -d "venv" ]; then
    echo "  [1/3] Creation de l'environnement virtuel..."
    "$PY" -m venv venv
fi

# Activate venv
# shellcheck disable=SC1091
source venv/bin/activate

# Install deps if needed
if [ ! -f "venv/.deps_installed" ]; then
    echo "  [2/3] Installation des dependances..."
    pip install -r requirements.txt --quiet
    touch venv/.deps_installed
else
    echo "  [2/3] Dependances deja installees."
fi

echo "  [3/3] Demarrage de Noisy + Dashboard..."
echo ""
echo "  Dashboard : http://localhost:8080"
echo "  Appuie sur Ctrl+C pour arreter."
echo ""

python noisy.py --dashboard "$@"
