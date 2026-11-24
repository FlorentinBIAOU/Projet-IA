"""Outils communs aux tests du jalon 4 (notebook milestone4_tests.ipynb et tests/test_moteur.py).

Le moteur du milestone 3 vit dans le notebook milestone3.ipynb. Ce module le recharge tel quel,
sans rien ecrire dans data/, pour pouvoir le relancer et le tester. Au milestone 5, quand le moteur
sera dans des fichiers .py, `charger_moteur` sera remplace par un simple import.
"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parent.parent if "__file__" in globals() else Path.cwd().parent   # notebook : lance depuis notebooks/
NOTEBOOKS = RACINE / "notebooks"
CAP_POIDS, CAP_VOLUME, AVANCE_MAX = 24500.0, 110.4, 7
TRANCHES_KG = [50, 100, 200, 300, 400, 500, 750, 1000, 1500, 2000, 2500, 3000, 3500, 4000]   # au-dela : ">4000"

if str(RACINE) not in sys.path:                                                     # [src] pour les tests : retire dans le notebook
    sys.path.insert(0, str(RACINE))                                                 # [src]
from src.controles import controles_solution  # noqa: E402,F401  (controles independants) [src]


def charger_moteur(chemin_planning=None, jusqu_a="def lancer_moteur", tolerant=False):
    """Execute les cellules du notebook milestone3 jusqu'a la definition du moteur complet.

    - chemin_planning : un autre planning (pour tester le moteur sur des donnees modifiees) ;
    - les cellules qui ecrivent des fichiers (to_csv) sont ignorees : data/ n'est jamais modifie ;
    - les graphiques sont supprimes ;
    - tolerant=True : une cellule qui echoue est ignoree (utile sur des donnees modifiees : les cellules de demonstration
      citent des couples precis, et le controle de la baseline du milestone 2 ne peut pas valoir sur d'autres donnees).
      Les echecs sont listes dans ns["_cellules_ignorees"].
    Renvoie l'espace de noms du moteur (fonctions, parametres, donnees).
    """
    nb = json.loads((NOTEBOOKS / "milestone3.ipynb").read_text(encoding="utf-8"))
    ns = {"display": lambda *a, **k: None, "_cellules_ignorees": []}
    ancien = os.getcwd()
    os.chdir(NOTEBOOKS)                       # les chemins du notebook sont relatifs a notebooks/
    # `valider` (milestone 3) utilise semaine_de, definie dans une cellule d'exemple : nous la fournissons d'avance.
    exec("import pandas as pd\n"
         "def semaine_de(d):\n"
         "    dt = pd.Timestamp(d); return (dt - pd.Timedelta(dt.weekday(), 'D')).date()", ns)
    try:
        for cellule in nb["cells"]:
            if cellule["cell_type"] != "code":
                continue
            src = "".join(cellule["source"])
            if "to_csv" in src or "savefig" in src:
                continue
            if chemin_planning is not None:
                src = src.replace("../data/processed/planning_propre.csv", str(chemin_planning).replace("\\", "/"))
            src = src.replace("plt.show()", "plt.close('all')")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(src, ns)
            except Exception as e:
                if not tolerant:
                    raise
                ns["_cellules_ignorees"].append(f"{type(e).__name__}: {str(e)[:100]}")
            if jusqu_a in src:
                break
    finally:
        os.chdir(ancien)
    return ns


def lancer_version(ns, mode):
    """Lance le moteur complet dans une version ('libre', 'intermediaire', 'strict')."""
    ns_mode = {"UN_CAMION_PAR_JOUR": True, "MODE_PROFIL": mode,
               "TOLERANCE_LISSAGE": ns["TOLERANCE_LISSAGE"], "TEMPS_MAX_SECONDES": ns["TEMPS_MAX_SECONDES"]}
    with contextlib.redirect_stdout(io.StringIO()):
        return ns["lancer_moteur"](ns_mode, afficher=False)


class MoteurSrc:
    """Donne a un `src.moteur.Moteur` l'interface de l'espace de noms du notebook (moteur["nom"]).

    Les memes tests peuvent ainsi s'appliquer au moteur du notebook milestone3 et au moteur structure en modules (milestone 5).
    """
    ALIAS = {"idx_tous": "IDX_TOUS", "grille": "grille"}

    def __init__(self, moteur):
        self.moteur = moteur

    def __getitem__(self, nom):
        if nom == "lancer_moteur":
            return self.lancer_moteur
        return getattr(self.moteur, self.ALIAS.get(nom, nom))

    def lancer_moteur(self, parametres, afficher=False):
        r = self.moteur.lancer(mode=parametres.get("MODE_PROFIL"), un_camion=parametres.get("UN_CAMION_PAR_JOUR"),
                               tolerance=parametres.get("TOLERANCE_LISSAGE"), limite_secondes=parametres.get("TEMPS_MAX_SECONDES"))
        return {"mode": r.mode, "choix": r.choix, "cout": r.cout, "etape1": r.etape1, "contenu": r.contenu,
                "temps": r.temps, "total": r.total, "controles": len(r.controles)}


def charger_moteur_src(chemin_planning=None):
    """Le moteur structure en modules (src/), construit sur le planning propre et la grille de data/processed/."""
    from src.moteur import Moteur
    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    planning = pd.read_csv(chemin_planning or RACINE / "data" / "processed" / "planning_propre.csv", parse_dates=["date", "semaine"])
    grille = pd.read_csv(RACINE / "data" / "processed" / "grille_prix.csv", index_col=0)
    return MoteurSrc(Moteur(planning, grille))


