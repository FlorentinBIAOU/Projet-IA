"""Les sorties du moteur : tableaux de resultats et fichiers.

  - sortie 1 : un profil a appliquer a chaque couple fournisseur x usine (profils_couples.csv) ;
  - sortie 2 : le materiel regroupe dans chaque camion (contenu_camions.csv) ;
  - un resume des economies et, si plusieurs versions sont calculees, leur comparaison.
"""
from pathlib import Path

import numpy as np
import pandas as pd


def totaux(choix):
    """(cout, camions, livraisons) d'un ensemble de profils choisis."""
    return (sum(b["cout"] for b in choix.values()), sum(b["camions"] for b in choix.values()),
            sum(b["livraisons"] for b in choix.values()))


def part_lundi(choix):
    """(livraisons du lundi, livraisons au total, part en %) : un indicateur de la charge du lundi."""
    lun = tot = 0
    for b in choix.values():
        for d in b["jours"]:
            tot += 1
            if pd.Timestamp(d).weekday() == 0:
                lun += 1
    return lun, tot, (lun / tot * 100 if tot else 0)


def profils_couples(moteur, resultat):
    """Sortie 1 : un profil par couple, avec le nombre de livraisons reelles, le cout et l'economie.

    Les couples dont toutes les lignes sont incompletes gardent leur livraison actuelle (H15).
    """
    contenu = resultat.contenu
    nb_semaines = moteur.planning["semaine"].nunique()
    lignes = []
    for (s, pl), b in resultat.choix.items():
        couple = moteur.COUPLES[(s, pl)]; p = moteur.PROFILS[b["idx"]]
        cout_act = moteur.cout_actuel_couple((s, pl))
        poids_cams = [g["poids"].sum() for cid, g in
                      contenu[(contenu.supplier_id == s) & (contenu.plant == pl)
                              & (~contenu.envoi_exceptionnel)].groupby("camion_id")]
        remp_moy = np.mean([w / moteur.CAP_POIDS * 100 for w in poids_cams]) if poids_cams else 0
        lignes.append({"supplier_id": s, "plant": pl, "distance": couple["distance"],
                       "envois_sem_actuels": round(couple["df"].groupby("date").ngroups / nb_semaines, 2),
                       "profil": p["libelle"], "periode": p["periode"],
                       "jours": ",".join(moteur.JOURS[j] for j in sorted(p["jours"])),
                       "livraisons_reelles": b["livraisons"], "camions": b["camions"], "envois_exceptionnels": b["exc"],
                       "remplissage_moyen_%": round(remp_moy, 2), "cout_actuel": round(cout_act, 2),
                       "cout_optimise": round(b["cout"], 2), "economie_eur": round(cout_act - b["cout"], 2),
                       "economie_%": round((cout_act - b["cout"]) / cout_act * 100, 1) if cout_act > 0 else 0})
    tableau = pd.DataFrame(lignes)
    planning = moteur.planning
    inconnus = sorted({(s, pl) for (s, pl) in planning[planning["statut"] != "optimise"]
                       .groupby(["supplier_id", "plant"]).groups} - set(moteur.COUPLES))
    for s, pl in inconnus:
        tableau.loc[len(tableau)] = {"supplier_id": s, "plant": pl, "distance": np.nan,
                                     "envois_sem_actuels": np.nan, "profil": "livraison actuelle conservee (H15)", "periode": np.nan,
                                     "jours": "", "livraisons_reelles": np.nan, "camions": np.nan, "envois_exceptionnels": np.nan,
                                     "remplissage_moyen_%": np.nan, "cout_actuel": np.nan, "cout_optimise": np.nan,
                                     "economie_eur": 0.0, "economie_%": 0.0}
    return tableau


def resume_economies(resultat, baselines, cout_inconnues):
    """Les indicateurs cles : cout avant/apres, camions, livraisons, avec et sans les lignes incompletes."""
    base = baselines["baseline_h20"]
    gain = base - resultat.cout
    camions_apres = sum(b["camions"] for b in resultat.choix.values())
    livraisons_apres = sum(b["livraisons"] for b in resultat.choix.values())
    return pd.DataFrame([
        ("Version du moteur (MODE_PROFIL)", resultat.mode),
        ("Cout avant - baseline H20 (perimetre)", round(base, 2)),
        ("Cout apres (perimetre)", round(resultat.cout, 2)),
        ("Economie (EUR)", round(gain, 2)),
        ("Economie (%)", round(gain / base * 100, 1)),
        ("Camions avant", baselines["camions_h20"]), ("Camions apres", camions_apres),
        ("Livraisons avant", baselines["livraisons_actuelles"]), ("Livraisons apres", livraisons_apres),
        ("Rappel baseline milestone 2", round(baselines["baseline_m2"], 2)),
        ("Cout lignes inconnues (H16, inchange)", round(cout_inconnues, 2)),
        ("Cout total avant (avec inconnues)", round(base + cout_inconnues, 2)),
        ("Cout total apres (avec inconnues)", round(resultat.cout + cout_inconnues, 2)),
    ], columns=["indicateur", "valeur"])


def comparaison_versions(moteur, resultats, baselines, limite_secondes=90):
    """Compare les versions calculees (dictionnaire mode -> Resultat) : cout, camions, semaines du profil respectees, temps."""
    base = baselines["baseline_h20"]
    lignes = []
    for mode, r in resultats.items():
        cout_v, cam_v, liv_v = totaux(r.choix)
        sem = moteur.semaines_par_couple(r.choix, r.contenu)
        resp = sum(a for a, n in sem.values()); nb_sem = sum(n for a, n in sem.values())
        lignes.append({"version": mode, "cout": round(cout_v, 2), "economie EUR": round(base - cout_v, 2),
                       "economie %": round((base - cout_v) / base * 100, 1), "camions": cam_v, "livraisons": liv_v,
                       "part lundi %": round(part_lundi(r.choix)[2], 1), "semaines respectees": resp, "semaines du profil": nb_sem,
                       "part semaines respectees %": round(resp / nb_sem * 100, 1),
                       "temps (s)": round(r.total, 2), f"temps < {limite_secondes} s": "OK" if r.total <= limite_secondes else "ECHEC"})
    return pd.DataFrame(lignes)


def enregistrer(dossier, **tableaux):
    """Ecrit chaque tableau en CSV (nom = nom du parametre) dans le dossier, qui est cree au besoin."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemins = {}
    for nom, tableau in tableaux.items():
        chemins[nom] = dossier / f"{nom}.csv"
        tableau.to_csv(chemins[nom], index=isinstance(tableau.index, pd.Index) and tableau.index.name is not None)
    return chemins
