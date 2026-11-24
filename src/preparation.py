"""Preparation des donnees (milestone 1) : du planning brut a une base propre, une ligne par vrai besoin.

Le pipeline nettoie, complete et marque, mais ne prend **aucune decision d'optimisation**.
Il tourne sur n'importe quel nouveau planning : ses controles ne dependent jamais de chiffres connus d'avance,
seulement de regles toujours vraies.
"""
import io
import logging

import numpy as np
import pandas as pd

from . import config

log = logging.getLogger("consolidation")


def parametres_preparation():
    """Les parametres de la preparation, tires de config.py (dictionnaire modifiable avant l'appel)."""
    return {
        "CAP_POIDS": config.CAP_POIDS, "CAP_VOLUME": config.CAP_VOLUME,
        "MARGE": config.MARGE, "DIESEL": config.DIESEL,
        "DATES_FOURRE_TOUT": list(config.DATES_FOURRE_TOUT), "TRANCHES_KM": list(config.TRANCHES_KM),
        "COLONNES_PLANNING": list(config.COLONNES_PLANNING), "COLONNES_DISTANCES": list(config.COLONNES_DISTANCES),
    }


def charger_planning(chemin):
    """Lit un planning (fichier CSV, encodage utf-8-sig)."""
    return pd.read_csv(chemin, encoding="utf-8-sig")


def charger_distances(chemin):
    """Lit le fichier des distances fournisseur -> usine."""
    return pd.read_csv(chemin)


def charger_grille_pdf(chemin):
    """Lit la grille tarifaire (couts de base) dans le PDF du transporteur."""
    import pdfplumber
    with pdfplumber.open(chemin) as pdf:
        tableau = pdf.pages[0].extract_tables()[0]
    grille = pd.DataFrame(tableau[1:], columns=tableau[0]).set_index(tableau[0][0])
    return grille.apply(lambda col: col.map(lambda x: float(str(x).replace(",", "."))))


def verifier_entree(planning, distances, grille, p):
    """Controle les fichiers recus ; bloque (ValueError) si une regle toujours vraie est violee.

    Les alertes non bloquantes sont ecrites dans le journal (log) : nous savons deja les traiter (H4, H6, H3).
    """
    erreurs = []
    # colonnes attendues presentes
    manque_p = [c for c in p["COLONNES_PLANNING"] if c not in planning.columns]
    manque_d = [c for c in p["COLONNES_DISTANCES"] if c not in distances.columns]
    if manque_p:
        erreurs.append("colonnes manquantes dans le planning : " + str(manque_p))
    if manque_d:
        erreurs.append("colonnes manquantes dans les distances : " + str(manque_d))
    if erreurs:                                     # sans les colonnes, les controles suivants n'ont pas de sens
        raise ValueError("Pipeline arrete, fichier a corriger :\n- " + "\n- ".join(erreurs))
    # valeurs numeriques convertibles (pas de texte la ou on attend un nombre)
    for col in ["schedule_quantity", "weight", "volume"]:
        nb_casse = pd.to_numeric(planning[col], errors="coerce").isna().sum() - planning[col].isna().sum()
        if nb_casse > 0:
            erreurs.append("valeurs non numeriques dans " + col)
    nb_casse = pd.to_numeric(distances["distance"], errors="coerce").isna().sum() - distances["distance"].isna().sum()
    if nb_casse > 0:
        erreurs.append("valeurs non numeriques dans distance")
    # dates convertibles
    nb_casse = pd.to_datetime(planning["date"], errors="coerce").isna().sum() - planning["date"].isna().sum()
    if nb_casse > 0:
        erreurs.append("dates non convertibles dans date")
    # aucune valeur negative
    for col in ["schedule_quantity", "weight", "volume"]:
        if (pd.to_numeric(planning[col], errors="coerce") < 0).any():
            erreurs.append("valeurs negatives dans " + col)
    if (pd.to_numeric(distances["distance"], errors="coerce") < 0).any():
        erreurs.append("distances negatives")
    # aucun doublon sur la cle
    cle = ["date", "supplier_id", "material", "plant", "unloading_point"]
    if planning.duplicated(subset=cle).any():
        erreurs.append("doublons sur la cle " + str(cle))
    # grille complete et numerique
    if grille.isna().any().any():
        erreurs.append("la grille contient des cases vides ou non numeriques")
    if erreurs:
        raise ValueError("Pipeline arrete, fichier a corriger :\n- " + "\n- ".join(erreurs))

    # alertes non bloquantes
    actifs = set(planning.loc[pd.to_numeric(planning["schedule_quantity"], errors="coerce") > 0, "supplier_id"])
    avec_dist = set(distances.loc[distances["distance"].notna(), "supplier_id"])
    log.info("Controles bloquants : tous OK")
    log.info("ALERTE poids vides : %d", int(planning["weight"].isna().sum()))
    log.info("ALERTE volumes vides : %d", int(planning["volume"].isna().sum()))
    log.info("ALERTE fournisseurs actifs sans distance : %d", len(actifs - avec_dist))
    log.info("ALERTE lignes plus lourdes qu'un camion : %d", int((pd.to_numeric(planning["weight"], errors="coerce") > p["CAP_POIDS"]).sum()))


def retirer_lignes(planning, p):
    """Retire les lignes a quantite 0 (H1) et les dates fourre-tout (H9)."""
    q = pd.to_numeric(planning["schedule_quantity"], errors="coerce")
    sans_zero = planning[q > 0].copy()
    return sans_zero[~sans_zero["date"].astype(str).isin(p["DATES_FOURRE_TOUT"])].copy()


def completer(df):
    """Met a 0 les poids/volumes vides et marque les lignes completees (H4). Aucune valeur n'est inventee."""
    df = df.copy()
    df["poids_manquant"] = df["weight"].isna()
    df["volume_manquant"] = df["volume"].isna()
    df["weight"] = df["weight"].fillna(0.0)
    df["volume"] = df["volume"].fillna(0.0)
    return df


def tranche_grille(km, tranches):
    """Renvoie la ligne de grille (tranche superieure) pour une distance."""
    if pd.isna(km):
        return None
    for t in tranches:
        if km <= t:
            return str(t)
    return ">650"


def enrichir(df, distances, p):
    """Ajoute date, semaine, jour, distance, ligne_grille, les marqueurs H3/H6 et le statut d'optimisation (H15)."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["semaine"] = df["date"].dt.to_period("W").dt.start_time
    noms_jours = {0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi", 4: "vendredi", 5: "samedi", 6: "dimanche"}
    df["jour"] = df["date"].dt.weekday.map(noms_jours)
    df = df.merge(distances[["supplier_id", "distance"]], on="supplier_id", how="left")
    df["ligne_grille"] = df["distance"].apply(lambda km: tranche_grille(km, p["TRANCHES_KM"]))
    df["sans_distance"] = df["distance"].isna()
    df["ligne_trop_lourde"] = df["weight"] > p["CAP_POIDS"]
    # H15 : une ligne sans poids, sans volume ou sans distance n'est pas optimisee
    non_optimise = df["poids_manquant"] | df["volume_manquant"] | df["sans_distance"]
    df["statut"] = np.where(non_optimise, "non optimise : info manquante", "optimise")
    return df


def preparer_grille(grille, p):
    """Renvoie la grille des prix finaux = cout x (1 + MARGE) x DIESEL (R5)."""
    return grille * (1 + p["MARGE"]) * p["DIESEL"]


def relire_grille(grille_prix):
    """La grille de prix telle qu'elle est enregistree puis relue (grille_prix.csv).

    A cout egal, le moteur departage deux profils au dernier chiffre des prix : relue depuis le fichier, la grille differe de
    celle gardee en memoire de 1e-16 sur quelques cases, ce qui peut changer le profil choisi (le cout total reste le meme).
    Le moteur travaille donc toujours sur la grille relue, comme les notebooks : les resultats sont les memes que ceux publies.
    """
    return pd.read_csv(io.StringIO(grille_prix.to_csv()), index_col=0)


def verifier_sortie(n_entree, n_retirees, propre, grille_prix, p):
    """Verifie la sortie avec des regles toujours vraies. Renvoie la liste des controles [(libelle, ok)]."""
    q = pd.to_numeric(propre["schedule_quantity"], errors="coerce")
    dates_str = pd.to_datetime(propre["date"]).dt.strftime("%Y-%m-%d")
    return [
        ("plus aucune quantite a 0", bool((q > 0).all())),
        ("plus aucune date fourre-tout", bool((~dates_str.isin(p["DATES_FOURRE_TOUT"])).all())),
        ("plus aucun poids/volume vide", bool(propre["weight"].notna().all() and propre["volume"].notna().all())),
        ("lignes entree = sortie + retirees", n_entree == len(propre) + n_retirees),
        ("ligne_grille presente sauf sans_distance", bool((propre["ligne_grille"].notna() | propre["sans_distance"]).all())),
        ("chaque ligne a un statut valide", bool(propre["statut"].isin(["optimise", "non optimise : info manquante"]).all())),
        ("statut non optimise si et seulement si un marqueur vrai", bool((
            (propre["statut"] == "non optimise : info manquante")
            == (propre["poids_manquant"] | propre["volume_manquant"] | propre["sans_distance"])).all())),
    ]


def preparer_donnees(planning, distances, grille, p=None):
    """Enchaine les etapes de preparation. Renvoie (planning_propre, grille_prix, journal).

    planning, distances, grille : DataFrames bruts (voir charger_planning, charger_distances, charger_grille_pdf).
    """
    p = p or parametres_preparation()
    verifier_entree(planning, distances, grille, p)

    n_brut = len(planning)
    q = pd.to_numeric(planning["schedule_quantity"], errors="coerce")
    apres_zero = planning[q > 0].copy()
    apres_ft = apres_zero[~apres_zero["date"].astype(str).isin(p["DATES_FOURRE_TOUT"])].copy()
    n0, nft = len(apres_zero), len(apres_ft)

    propre = completer(apres_ft)
    propre = enrichir(propre, distances, p)
    grille_prix = preparer_grille(grille, p)
    tri = ["date", "supplier_id", "plant", "material", "unloading_point"]      # ordre stable : la sortie est reproductible
    propre = propre.sort_values(tri).reset_index(drop=True)

    journal = pd.DataFrame([
        {"etape": "charger", "lignes_avant": n_brut, "lignes_apres": n_brut, "retirees_ou_marquees": 0, "regle": "-"},
        {"etape": "retirer quantite 0", "lignes_avant": n_brut, "lignes_apres": n0, "retirees_ou_marquees": n_brut - n0, "regle": "H1"},
        {"etape": "retirer dates fourre-tout", "lignes_avant": n0, "lignes_apres": nft, "retirees_ou_marquees": n0 - nft, "regle": "H9"},
        {"etape": "completer poids/volume", "lignes_avant": nft, "lignes_apres": nft,
         "retirees_ou_marquees": int(propre["poids_manquant"].sum() + propre["volume_manquant"].sum()), "regle": "H4"},
        {"etape": "enrichir", "lignes_avant": nft, "lignes_apres": len(propre),
         "retirees_ou_marquees": int(propre["sans_distance"].sum() + propre["ligne_trop_lourde"].sum()), "regle": "H2/H3/H6/H11"},
        {"etape": "statut optimisation", "lignes_avant": len(propre), "lignes_apres": len(propre),
         "retirees_ou_marquees": int((propre["statut"] == "non optimise : info manquante").sum()), "regle": "H15"},
    ])

    controles = verifier_sortie(n_brut, n_brut - nft, propre, grille_prix, p)
    echecs = [nom for nom, ok in controles if not ok]
    if echecs:
        raise ValueError("Controles de sortie en echec : " + "; ".join(echecs))
    return propre, grille_prix, journal
