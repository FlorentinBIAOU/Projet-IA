"""Parametres du projet : un seul endroit pour toutes les regles et tous les chemins.

Les valeurs viennent du client (capacites, avance maximale) ou de nos hypotheses (H7, H17, H19, H21).
Pour changer une regle, on modifie ce fichier (ou on passe un dictionnaire de parametres a `main.py`).
"""
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "data"
DOCS = RACINE / "docs"

# ----- Fichiers d'entree par defaut (ceux du client)
CHEMIN_PLANNING = DONNEES / "released_schedule.csv"
CHEMIN_DISTANCES = DONNEES / "distances.csv"
CHEMIN_GRILLE = DOCS / "rate_sheet.pdf"
DOSSIER_SORTIE = RACINE / "resultats"

# ----- Regles du client
CAP_POIDS = 24500.0       # kg par camion (R2)
CAP_VOLUME = 110.4        # m3 par camion (R2)
AVANCE_MAX = 7            # R1 : au plus 7 jours d'avance, jamais de retard

# ----- Tarification (R5) : prix final = cout de base x (1 + MARGE) x DIESEL
MARGE = 2.3923
DIESEL = 1.1943
TRANCHES_KG = [50, 100, 200, 300, 400, 500, 750, 1000, 1500, 2000, 2500, 3000, 3500, 4000]   # au-dela : ">4000"
TRANCHES_KM = [30, 50, 75, 100, 125, 150, 175, 200, 250, 300, 400, 500, 650]                  # au-dela : ">650"

# ----- Preparation des donnees
DATES_FOURRE_TOUT = ["2027-01-01"]       # H9 : dates a retirer
COLONNES_PLANNING = ["date", "supplier_id", "material", "plant", "unloading_point",
                     "schedule_quantity", "weight", "volume", "transmission_date", "version_date"]
COLONNES_DISTANCES = ["supplier_id", "distance"]

# ----- Moteur
JOURS = {0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi", 4: "vendredi"}
VERSIONS = ("libre", "intermediaire", "strict")

PARAMETRES_MOTEUR = {
    "CAP_POIDS": CAP_POIDS,
    "CAP_VOLUME": CAP_VOLUME,
    "AVANCE_MAX": AVANCE_MAX,
    "TRANCHES_KG": TRANCHES_KG,
    "TRANCHES_KM": TRANCHES_KM,
    "JOURS": JOURS,
    "SEMAINES_FERMEES": ["2026-12-21"],   # H7 : lundi des semaines sans livraison (Noel)
    "TOLERANCE_LISSAGE": 0.02,            # H17 : pour lisser, on accepte +2 % de cout au plus
    "UN_CAMION_PAR_JOUR": True,           # H19 : au plus un camion par couple et par jour
    "MODE_PROFIL": "strict",              # H21 : version du moteur ; "strict" recommandee (un profil est un engagement), "libre" et "intermediaire" en comparaison
    "MIN_SEMAINES_RESPECTEES": 4,         # H21 : semaines respectees au minimum en version intermediaire
    "PREMIER_JOUR_LIVRAISON": None,       # None : premier besoin - AVANCE_MAX (le 02/11 pour un premier besoin le 09/11) ; ou une date "AAAA-MM-JJ"
    "TEMPS_MAX_SECONDES": 90,             # budget de temps du moteur complet (par version)
}
