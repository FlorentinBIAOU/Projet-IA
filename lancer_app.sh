#!/usr/bin/env bash
# Lance le dashboard Streamlit de la consolidation des livraisons.
#   ./lancer_app.sh              ouvre http://localhost:8501
#   ./lancer_app.sh --server.port 8600
cd "$(dirname "$0")" || exit 1
if [ -d .venv ]; then
  source .venv/bin/activate
fi
exec streamlit run app.py "$@"
