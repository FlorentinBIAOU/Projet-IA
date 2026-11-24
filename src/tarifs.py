"""Tarifs et situation actuelle (milestone 2).

La grille de prix donne le prix **final** d'un camion (marge et diesel deja appliques) :
une ligne par tranche de distance, une colonne par tranche de poids. On lit simplement la case.
"""
import numpy as np
import pandas as pd

from .config import CAP_POIDS, CAP_VOLUME, TRANCHES_KG, TRANCHES_KM


def tranche_poids(kg):
    """Colonne de la grille : la tranche de poids juste au-dessus (au-dela de 4000 -> '>4000')."""
    for t in TRANCHES_KG:
        if kg <= t:
            return str(t)
    return ">4000"


def ligne_depuis_distance(km):
    """Ligne de la grille : la tranche de distance juste au-dessus (moins de 30 -> '30')."""
    for t in TRANCHES_KM:
        if km <= t:
            return str(t)
    return ">650"


def ligne_texte(ligne_grille):
    """Nom de la ligne de grille : '150' pour 150.0 ou '150', et '>650' pour la derniere ligne (distances au-dela de 650 km)."""
    texte = str(ligne_grille)
    return texte if texte.startswith(">") else str(int(float(texte)))


def prix_camion(grille, ligne_grille, poids_kg):
    """Prix final d'un camion : la case (ligne de distance, colonne de poids) de la grille."""
    return float(grille.loc[ligne_texte(ligne_grille), tranche_poids(poids_kg)])


def prix_camion_plein(grille, ligne_grille):
    """Prix d'un camion plein : colonne '>4000' sur cette ligne de grille (utilise pour les lignes inconnues, H16)."""
    return float(grille.loc[ligne_texte(ligne_grille), ">4000"])


def nb_camions(poids, volume):
    """Nombre de camions d'un envoi : la premiere limite atteinte, poids ou volume (R2)."""
    return max(1, int(np.ceil(poids / CAP_POIDS)), int(np.ceil(volume / CAP_VOLUME)))


def cout_envoi(poids, volume, ligne_grille, grille):
    """Cout d'un envoi (H13) : camions pleins au tarif >4000 + dernier camion au poids restant."""
    n = nb_camions(poids, volume)
    if n <= 1:
        return prix_camion(grille, ligne_grille, poids)
    pleins = int(poids // CAP_POIDS)
    reste = poids - pleins * CAP_POIDS
    cout = pleins * prix_camion(grille, ligne_grille, CAP_POIDS)
    if reste > 1e-6:
        cout += prix_camion(grille, ligne_grille, reste)
    return cout


def envois_actuels(planning, grille):
    """Situation actuelle : un envoi = fournisseur x usine x date, avec son nombre de camions, son remplissage et son cout.

    Ne porte que sur le perimetre optimise (lignes dont le poids, le volume et la distance sont connus).
    """
    optimise = planning[planning["statut"] == "optimise"]
    envois = optimise.groupby(["supplier_id", "plant", "date"]).agg(
        semaine=("semaine", "first"), jour=("jour", "first"),
        nb_lignes=("weight", "size"), nb_pieces=("schedule_quantity", "sum"),
        poids=("weight", "sum"), volume=("volume", "sum"),
        distance=("distance", "first"), ligne_grille=("ligne_grille", "first")).reset_index()
    envois["nb_camions"] = [nb_camions(p, v) for p, v in zip(envois["poids"], envois["volume"])]
    envois["remplissage_poids_%"] = envois["poids"] / (envois["nb_camions"] * CAP_POIDS) * 100
    envois["remplissage_volume_%"] = envois["volume"] / (envois["nb_camions"] * CAP_VOLUME) * 100
    envois["cout"] = [cout_envoi(p, v, l, grille) for p, v, l in zip(envois["poids"], envois["volume"], envois["ligne_grille"])]
    return envois


def lignes_inconnues(planning, grille):
    """Lignes non optimisees (poids, volume ou distance manquants) : chacune est estimee a un camion plein, seul (H16, pire cas)."""
    non_optimise = planning[planning["statut"] != "optimise"].copy()
    distance_max = planning["distance"].max()
    ligne_distance_max = float(next((t for t in TRANCHES_KM if distance_max <= t), 650))   # (au-dela de 650 km : ligne '>650', voir ligne_texte)

    def raison(r):
        motifs = []
        if r["poids_manquant"]:
            motifs.append("poids manquant")
        if r["volume_manquant"]:
            motifs.append("volume manquant")
        if r["sans_distance"]:
            motifs.append("distance manquante")
        return " + ".join(motifs)

    inconnues = non_optimise.copy()
    inconnues["raison"] = inconnues.apply(raison, axis=1) if len(inconnues) else ""
    lignes = np.where(inconnues["sans_distance"], ligne_distance_max, inconnues["ligne_grille"])
    try:
        inconnues["ligne_grille"] = lignes.astype(float)
    except ValueError:                       # une ligne ">650" : on garde le texte
        inconnues["ligne_grille"] = lignes
    inconnues["nb_camions"] = 1
    inconnues = inconnues[["supplier_id", "plant", "date", "raison", "ligne_grille", "nb_camions"]].reset_index(drop=True)
    inconnues["cout"] = [prix_camion_plein(grille, l) for l in inconnues["ligne_grille"]]
    return inconnues


def potentiel_couples(envois, grille, nb_semaines=None):
    """Potentiel de regroupement de chaque couple (estimation volontairement simple du milestone 2).

    Pour chaque couple et chaque semaine, tous les besoins actuels sont regroupes sur un seul envoi (le lundi) ; le gain
    est la difference avec le cout actuel. C'est un ordre de grandeur pour classer les couples, pas l'optimisation du moteur.
    `envois` : le resultat de `envois_actuels`.
    """
    nb_semaines = nb_semaines or envois["semaine"].nunique()
    cs = envois.groupby(["supplier_id", "plant", "semaine"]).agg(
        poids=("poids", "sum"), volume=("volume", "sum"), ligne_grille=("ligne_grille", "first"),
        envois=("cout", "size"), cout_actuel=("cout", "sum")).reset_index()
    cs["cout_regroupe"] = [cout_envoi(p, v, l, grille) for p, v, l in zip(cs["poids"], cs["volume"], cs["ligne_grille"])]
    pot = cs.groupby(["supplier_id", "plant"]).agg(
        envois=("envois", "sum"), poids=("poids", "sum"),
        cout_actuel=("cout_actuel", "sum"), cout_regroupe=("cout_regroupe", "sum")).reset_index()
    pot = pot.merge(envois.groupby(["supplier_id", "plant"])["distance"].first().reset_index(), on=["supplier_id", "plant"])
    pot["envois_par_sem"] = pot["envois"] / nb_semaines
    pot["gain_eur"] = pot["cout_actuel"] - pot["cout_regroupe"]
    pot["gain_%"] = np.where(pot["cout_actuel"] > 0, pot["gain_eur"] / pot["cout_actuel"] * 100, 0)
    return pot.sort_values("gain_eur", ascending=False).reset_index(drop=True)
