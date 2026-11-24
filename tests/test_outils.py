"""Le moteur modulaire (src/moteur.py) est genere a partir du notebook du milestone 3 : il doit toujours etre a jour."""
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def test_le_moteur_modulaire_est_a_jour_avec_le_notebook():
    """Si le moteur du notebook change, ce test echoue : relancer `python outils/regenerer_moteur.py`."""
    r = subprocess.run([sys.executable, str(RACINE / "outils" / "regenerer_moteur.py"), "--verifier"], capture_output=True, text=True, cwd=RACINE)
    assert r.returncode == 0, r.stdout + r.stderr
