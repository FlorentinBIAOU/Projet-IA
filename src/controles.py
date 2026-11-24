"""Controles independants d'une solution (jalon 4).

Ils recalculent tout a partir du planning d'entree et de la grille, sans utiliser les controles internes du moteur :
exhaustivite (par ligne, par materiau), regles R1, R2, R3, H19, H20, calendrier et cout.
"""
import numpy as np
import pandas as pd

from .config import AVANCE_MAX, CAP_POIDS, CAP_VOLUME, TRANCHES_KG


def controles_solution(contenu, opt, grille, jours_ouvres, cout_annonce=None):
    """Controles independants d'une solution (sortie 2) contre son planning d'entree.

    Renvoie une liste de (nom, ok, detail). Ne depend pas des controles du milestone 3.
    """
    res = []
    def ajout(nom, ok, detail=""):
        res.append((nom, bool(ok), detail))

    cle = ["supplier_id", "plant", "material", "unloading_point"]
    c = contenu.copy()
    c["date_livraison"] = pd.to_datetime(c["date_livraison"])
    c["date_besoin"] = pd.to_datetime(c["date_besoin"])
    exc = c["envoi_exceptionnel"].astype(bool)

    # Exhaustivite : chaque ligne du planning, une seule fois, memes poids et volume
    a = opt.rename(columns={"date": "date_besoin"})[cle + ["date_besoin", "weight", "volume"]]
    m = a.merge(c[cle + ["date_besoin", "poids", "volume"]], on=cle + ["date_besoin"], how="outer",
                suffixes=("_plan", "_camion"), indicator=True)
    ajout("aucune ligne oubliee ni inventee", (m["_merge"] == "both").all(), f"{(m['_merge'] != 'both').sum()} ecart(s)")
    ajout("aucune ligne livree deux fois", not c.duplicated(cle + ["date_besoin"]).any())
    both = m[m["_merge"] == "both"]
    ajout("poids et volumes conserves", np.allclose(both["poids"], both["weight"], atol=0.01)
          and np.allclose(both["volume_camion"], both["volume_plan"], atol=0.001))

    # Exhaustivite par materiau : pour chaque materiau, meme quantite demandee et livree
    q_plan = opt.groupby("material")["schedule_quantity"].sum(); q_liv = c.groupby("material")["quantite"].sum()
    ajout("exhaustivite par materiau : memes materiaux, meme quantite demandee et livree",
          set(q_plan.index) == set(q_liv.index) and np.allclose(q_plan.sort_index(), q_liv.sort_index(), atol=0.01),
          f"{len(q_plan)} materiaux")

    # R1
    av = (c["date_besoin"] - c["date_livraison"]).dt.days
    ajout("R1 : jamais en retard", (av >= 0).all(), f"avance min {av.min()} j")
    ajout("R1 : au plus 7 jours d'avance", (av <= AVANCE_MAX).all(), f"avance max {av.max()} j")

    # R2 / R3 / H19
    pc = c.groupby("camion_id").agg(p=("poids", "sum"), v=("volume", "sum"), f=("supplier_id", "nunique"),
                                    u=("plant", "nunique"), d=("date_livraison", "nunique"), e=("envoi_exceptionnel", "max"))
    norm = pc[~pc["e"].astype(bool)]
    ajout("R2 : capacite poids et volume (camions normaux)",
          (norm["p"] <= CAP_POIDS + 1e-3).all() and (norm["v"] <= CAP_VOLUME + 1e-3).all(),
          f"max {norm['p'].max():.0f} kg, {norm['v'].max():.1f} m3")
    ajout("R3 : un fournisseur, une usine et un jour par camion", ((pc["f"] == 1) & (pc["u"] == 1) & (pc["d"] == 1)).all())
    n = c[~exc].groupby(["supplier_id", "plant", "date_livraison"])["camion_id"].nunique()
    ajout("H19 : au plus un camion normal par couple et par jour", (n <= 1).all() if len(n) else True)

    # Calendrier
    jl = c["date_livraison"]
    ajout("livraisons des jours ouvres du moteur (lundi-vendredi, hors Noel)",
          set(jl.dt.normalize()) <= set(pd.DatetimeIndex(jours_ouvres)))

    # H20
    ex = c[exc].groupby("camion_id").agg(n=("poids", "size"), p=("poids", "sum"), v=("volume", "sum"))
    ajout("H20 : chaque envoi exceptionnel est une seule ligne plus lourde qu'un camion",
          ((ex["n"] == 1) & ((ex["p"] > CAP_POIDS) | (ex["v"] > CAP_VOLUME))).all() if len(ex) else True,
          f"{len(ex)} envoi(s)")

    # Cout recalcule depuis la grille
    tranches = TRANCHES_KG
    ligne = opt.groupby(["supplier_id", "plant"])["ligne_grille"].first()
    info = c.groupby("camion_id").agg(s=("supplier_id", "first"), pl=("plant", "first"), p=("poids", "sum"), e=("envoi_exceptionnel", "max"))
    prix = 0.0
    for r in info.itertuples():
        lg = str(ligne[(r.s, r.pl)])
        col = ">4000" if r.e else next((str(t) for t in tranches if r.p <= t), ">4000")
        prix += float(grille.loc[lg, col])
    if cout_annonce is not None:
        ajout("cout annonce = cout recalcule camion par camion", abs(prix - cout_annonce) < 0.05,
              f"recalcule {prix:,.2f} EUR, annonce {cout_annonce:,.2f} EUR".replace(",", " "))
    return res, prix
