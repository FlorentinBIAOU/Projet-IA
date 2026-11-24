"""Tests automatiques du moteur de consolidation (jalon 4).

Lancer depuis la racine du projet :

    pytest tests -v

Ces tests reprennent l'essentiel du notebook notebooks/milestone4_tests.ipynb, sous une forme
que le milestone 5 pourra brancher telle quelle sur le moteur structure en fichiers .py.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outils_tests import (AVANCE_MAX, CAP_POIDS, CAP_VOLUME, NOTEBOOKS, RACINE, charger_moteur,  # noqa: E402
                          charger_moteur_src, controles_solution, lancer_version)

DONNEES = RACINE / "data" / "processed"
MODES = ("libre", "intermediaire", "strict")


@pytest.fixture(scope="session", params=["notebook", "src"])
def moteur(request):
    """Le moteur du notebook milestone3 ET le moteur structure en modules (src/) : les memes tests s'appliquent aux deux."""
    return charger_moteur() if request.param == "notebook" else charger_moteur_src()


@pytest.fixture(scope="session")
def versions(moteur):
    return {m: lancer_version(moteur, m) for m in MODES}


def couple_fictif(besoins, ligne="150", volume_par_kg=1 / 300):
    besoins = sorted(besoins)
    return {"besoins": np.array([np.datetime64(d) for d, _ in besoins], dtype="datetime64[D]"),
            "poids": np.array([p for _, p in besoins], dtype=float),
            "volume": np.array([p * volume_par_kg for _, p in besoins], dtype=float),
            "ligne": ligne, "exc_dates": np.array([], dtype="datetime64[D]")}


# ---------------------------------------------------------------- 1. tests unitaires
@pytest.mark.parametrize("kg, attendu", [(0.0, "50"), (50.0, "50"), (50.01, "100"), (4000.0, "4000"),
                                         (4000.01, ">4000"), (24500.0, ">4000")])
def test_tranche_poids_aux_bornes(moteur, kg, attendu):
    assert moteur["tranche_poids"](kg) == attendu


def test_prix_camion_egal_lecture_grille(moteur):
    rng = np.random.default_rng(4)
    grille = moteur["grille"]
    for _ in range(1000):
        ligne = str(rng.choice(grille.index)); kg = float(rng.uniform(0, 24500))
        assert moteur["prix_camion"](ligne, kg) == pytest.approx(grille.loc[ligne, moteur["tranche_poids"](kg)])


def test_prix_ne_baisse_jamais_quand_le_poids_monte(moteur):
    assert (moteur["grille"].diff(axis=1).iloc[:, 1:] >= -1e-9).all().all()


def test_166_profils_dont_26_du_client(moteur):
    profils = moteur["generer_profils"]()
    assert len(profils) == 166
    assert sum(p["type"] == "PDF" for p in profils) == 26


def test_35_jours_ouvres_dont_une_semaine_d_avance_sans_noel(moteur):
    jours = moteur["jours_ouvres"]
    assert len(jours) == 35 and all(d.weekday() < 5 for d in jours)            # 5 jours d'avance (H22) + 30 jours de besoins
    assert jours[0] == pd.Timestamp("2026-11-02") and sum(d < pd.Timestamp("2026-11-09") for d in jours) == 5
    assert pd.Timestamp("2026-12-21") not in set(jours)


def test_dp_un_besoin_le_jour_du_profil(moteur):
    par_nom = {p["libelle"]: i for i, p in enumerate(moteur["PROFILS"])}
    r = moteur["evaluer_dp"](couple_fictif([("2026-11-09", 800)]), par_nom["1 / semaine : lundi"])
    assert r["livraisons"] == 1 and r["cout"] == pytest.approx(moteur["prix_camion"]("150", 800))


def test_dp_jamais_de_retard_ni_plus_de_7_jours(moteur):
    par_nom = {p["libelle"]: i for i, p in enumerate(moteur["PROFILS"])}
    # le premier mercredi est le 04/11 (semaine d'avance, H22) : un besoin du 03/11 n'a aucun jour avant lui
    assert moteur["evaluer_dp"](couple_fictif([("2026-11-03", 800)]), par_nom["1 / semaine : mercredi"]) is None
    # en revanche un besoin du 10/11 part le mercredi 04/11 (6 jours d'avance) : possible depuis H22
    assert moteur["evaluer_dp"](couple_fictif([("2026-11-10", 800)]), par_nom["1 / semaine : mercredi"]) is not None
    un_sur_deux = par_nom["1 semaine sur 2 (semaine 1) : lundi"]        # lundis 02/11, 16/11, 30/11, 14/12
    assert moteur["evaluer_dp"](couple_fictif([("2026-11-09", 800)]), un_sur_deux) is not None   # 7 jours pile apres le 02/11
    assert moteur["evaluer_dp"](couple_fictif([("2026-11-10", 800)]), un_sur_deux) is None       # 8 jours


def test_dp_capacite_24500_pile(moteur):
    lundi = {p["libelle"]: i for i, p in enumerate(moteur["PROFILS"])}["1 / semaine : lundi"]
    assert moteur["evaluer_dp"](couple_fictif([("2026-11-09", 12000), ("2026-11-09", 12500)]), lundi) is not None
    assert moteur["evaluer_dp"](couple_fictif([("2026-11-09", 12000), ("2026-11-09", 12500.01)]), lundi) is None


def _force_brute(moteur, couple, dates):
    dj = dates.astype("datetime64[D]").astype(int); bj = couple["besoins"].astype("datetime64[D]").astype(int)
    meilleur = None
    for masque in range(1, 2 ** len(dj)):
        rj = dj[[k for k in range(len(dj)) if masque >> k & 1]]
        pos = np.searchsorted(rj, bj, side="right") - 1
        if (pos < 0).any() or (bj - rj[pos] > AVANCE_MAX).any():
            continue
        w = np.bincount(pos, weights=couple["poids"], minlength=len(rj))
        v = np.bincount(pos, weights=couple["volume"], minlength=len(rj))
        if (w > CAP_POIDS + 1e-6).any() or (v > CAP_VOLUME + 1e-6).any():
            continue
        cout = sum(moteur["prix_camion"](couple["ligne"], x) for x in w if x > 1e-9)
        meilleur = cout if meilleur is None else min(meilleur, cout)
    return meilleur


def test_dp_egale_force_brute_sur_cas_aleatoires(moteur):
    rng = np.random.default_rng(2026)
    petits = [i for i, d in enumerate(moteur["DATES_PROFIL"]) if 3 <= len(d) <= 9]
    for _ in range(80):
        n = int(rng.integers(2, 9)); ip = int(rng.choice(petits)); base = moteur["DATES_PROFIL"][ip]
        dates = rng.choice(base, size=n) + rng.integers(0, 7, size=n).astype("timedelta64[D]")
        poids = rng.choice([30, 200, 800, 2500, 6000, 9000, 14000], size=n) * rng.uniform(0.8, 1.2, size=n)
        c = couple_fictif(list(zip(dates.astype(str), poids)), ligne=str(rng.choice(list(moteur["grille"].index))))
        r = moteur["evaluer_dp"](c, ip); fb = _force_brute(moteur, c, moteur["DATES_PROFIL"][ip])
        assert (r is None) == (fb is None)
        if r is not None:
            assert r["cout"] == pytest.approx(fb, abs=1e-6)


# ---------------------------------------------------------------- 2. contraintes sur chaque version
@pytest.mark.parametrize("mode", MODES)
def test_contraintes_de_chaque_version(moteur, versions, mode):
    liste, _ = controles_solution(versions[mode]["contenu"], moteur["opt"], moteur["grille"], moteur["jours_ouvres"], versions[mode]["cout"])
    echecs = [(nom, detail) for nom, ok, detail in liste if not ok]
    assert not echecs, echecs


def test_les_versions_coutent_de_plus_en_plus_cher(versions):
    assert versions["libre"]["cout"] <= versions["intermediaire"]["cout"] <= versions["strict"]["cout"]


def test_intermediaire_respecte_au_moins_quatre_semaines(moteur, versions):
    """Intermédiaire : au moins 4 semaines du profil respectées par couple (toutes si le profil en a moins)."""
    sem = moteur["semaines_par_couple"](versions["intermediaire"]["choix"], versions["intermediaire"]["contenu"])
    assert all(a >= min(4, b) for a, b in sem.values())


def test_objectif_de_semaines_par_version(moteur):
    ip = {p["libelle"]: i for i, p in enumerate(moteur["PROFILS"])}
    deux_par_semaine = ip["2 / semaine : lundi, jeudi"]                    # 7 semaines : la semaine du 02/11 compte, puis les 6 de besoins
    un_sur_deux = ip["1 semaine sur 2 (semaine 1) : lundi, jeudi"]          # 4 semaines : 02/11, 16/11, 30/11, 14/12
    assert moteur["objectif_semaines"](deux_par_semaine) == (4, 7)
    assert moteur["objectif_semaines"](un_sur_deux) == (4, 4)               # toutes, car le profil n'en a pas plus de 4


@pytest.mark.parametrize("mode", MODES)
def test_semaine_d_avance_utilisee_sans_depasser_7_jours(versions, mode):
    """H22 : des lignes partent la semaine d'avance (du 02/11 au 06/11), jamais plus de 7 jours avant leur besoin."""
    c = versions[mode]["contenu"]
    liv = pd.to_datetime(c["date_livraison"]); bes = pd.to_datetime(c["date_besoin"])
    assert liv.min() >= pd.Timestamp("2026-11-02")
    assert (liv < pd.Timestamp("2026-11-09")).sum() > 0
    assert ((bes - liv).dt.days <= 7).all()


def test_stricte_respecte_toutes_les_semaines(moteur, versions):
    sem = moteur["semaines_par_couple"](versions["strict"]["choix"], versions["strict"]["contenu"])
    assert all(a == b for a, b in sem.values())


# ---------------------------------------------------------------- 3. moteur relance : reproductibilite, temps, regression
def test_deux_executions_identiques(moteur, versions):
    deuxieme = lancer_version(moteur, "libre")
    assert deuxieme["cout"] == versions["libre"]["cout"]
    assert deuxieme["contenu"].equals(versions["libre"]["contenu"])


@pytest.mark.parametrize("mode", MODES)
def test_temps_sous_le_budget(versions, mode):
    assert versions[mode]["total"] <= 90


@pytest.mark.parametrize("mode", MODES)
def test_non_regression(versions, mode):
    ref = json.loads((Path(__file__).parent / "reference_resultats.json").read_text(encoding="utf-8"))["versions"][mode]
    c = versions[mode]["contenu"]
    assert versions[mode]["cout"] == pytest.approx(ref["cout"], abs=0.01)
    assert c["camion_id"].nunique() == ref["camions"]
    assert c[~c["envoi_exceptionnel"]]["camion_id"].nunique() == ref["livraisons"]


@pytest.mark.parametrize("mode", MODES)
def test_comparaison_versions_csv_a_jour(versions, mode):
    comp = pd.read_csv(DONNEES / "comparaison_versions.csv").set_index("version")
    assert comp.loc[mode, "cout"] == pytest.approx(versions[mode]["cout"], abs=0.01)
    assert int(comp.loc[mode, "camions"]) == versions[mode]["contenu"]["camion_id"].nunique()


# ---------------------------------------------------------------- 4. lissage
def test_le_lissage_ne_cree_aucun_pic(moteur, versions):
    charge = moteur["charge_par_jour_semaine"]
    avant, apres = charge(versions["libre"]["etape1"]), charge(versions["libre"]["choix"])
    for usine in avant:
        assert max(apres[usine].values()) <= max(avant[usine].values())
        # le lissage peut choisir un profil a une livraison de plus ou de moins (cout dans les 2 %), pas davantage
        assert abs(sum(apres[usine].values()) - sum(avant[usine].values())) <= 0.05 * sum(avant[usine].values())


def test_le_lissage_reste_dans_la_tolerance(versions):
    avant, apres = versions["libre"]["etape1"], versions["libre"]["choix"]
    assert all(apres[k]["cout"] <= avant[k]["cout"] * 1.02 + 1e-6 for k in apres)


# ---------------------------------------------------------------- 5. autres fonctions du moteur
def test_cout_exceptionnels(moteur):
    par_nom = {p["libelle"]: i for i, p in enumerate(moteur["PROFILS"])}
    c74 = moteur["COUPLES"][("SUP_00074", "PLT_003")]
    cout, nb = moteur["cout_exceptionnels"](c74, moteur["DATES_PROFIL"][par_nom["1 / semaine : lundi"]])
    assert nb == 1 and cout == pytest.approx(moteur["prix_exceptionnel"](c74["ligne"]))
    # dernier jour du profil a 8 jours du besoin (15/12) : impossible
    assert moteur["cout_exceptionnels"](c74, moteur["DATES_PROFIL"][par_nom["1 semaine sur 4 (semaine 1) : lundi"]]) is None
    assert moteur["cout_exceptionnels"](couple_fictif([("2026-11-09", 500)]), moteur["DATES_PROFIL"][par_nom["1 / semaine : lundi"]]) == (0.0, 0)


def test_construire_contenu_sur_couples_tires_au_hasard(moteur):
    par_nom = {p["libelle"]: i for i, p in enumerate(moteur["PROFILS"])}
    idx5 = par_nom["5 / semaine : lundi, mardi, mercredi, jeudi, vendredi"]
    rng = np.random.default_rng(7); cles = list(moteur["COUPLES"])
    vus = 0
    for i in rng.choice(len(cles), 40, replace=False):
        cle = cles[i]; cp = moteur["COUPLES"][cle]; res = moteur["evaluer_dp"](cp, idx5)
        if res is None:
            continue
        vus += 1
        cont = moteur["construire_contenu"]({cle: res})
        assert len(cont) == len(cp["besoins"]) + len(cp["exc_dates"])
        assert cont["poids"].sum() == pytest.approx(cp["poids"].sum() + cp["exc_poids"].sum(), abs=0.01)
        assert cont["avance_jours"].between(0, AVANCE_MAX).all()
        prix = sum(moteur["grille"].loc[cp["ligne"], ">4000" if g["envoi_exceptionnel"].iloc[0] else moteur["tranche_poids"](g["poids"].sum())]
                   for _, g in cont.groupby("camion_id"))
        assert prix == pytest.approx(res["cout"], abs=0.01)
    assert vus > 20


def _force_brute_inter(moteur, couple, ip):
    dates = moteur["DATES_PROFIL"][ip]; K = moteur["objectif_semaines"](ip)[0]; sem = moteur["SEM_PROFIL"][ip]
    ce = moteur["cout_exceptionnels"](couple, dates)
    if ce is None:
        return None
    dj = dates.astype("datetime64[D]").astype(int); bj = couple["besoins"].astype("datetime64[D]").astype(int)
    meilleur = None
    for masque in range(1, 2 ** len(dj)):
        retenu = np.array([masque >> k & 1 == 1 for k in range(len(dj))])
        rj = dj[retenu]; pos = np.searchsorted(rj, bj, side="right") - 1
        if (pos < 0).any() or (bj - rj[pos] > AVANCE_MAX).any():
            continue
        w = np.bincount(pos, weights=couple["poids"], minlength=len(rj)); v = np.bincount(pos, weights=couple["volume"], minlength=len(rj))
        if (w > CAP_POIDS + 1e-6).any() or (v > CAP_VOLUME + 1e-6).any():
            continue
        if (np.bincount(sem, weights=(~retenu).astype(float), minlength=int(sem.max()) + 1) == 0).sum() < K:
            continue
        cout = sum(moteur["prix_camion"](couple["ligne"], x) for x in w if x > 1e-9)
        meilleur = cout if meilleur is None else min(meilleur, cout)
    return None if meilleur is None else meilleur + ce[0]


def test_dp_intermediaire_egale_force_brute(moteur):
    rng = np.random.default_rng(11)
    petits = [i for i, d in enumerate(moteur["DATES_PROFIL"]) if 3 <= len(d) <= 9]
    for _ in range(60):
        n = int(rng.integers(2, 8)); ip = int(rng.choice(petits))
        base = moteur["DATES_PROFIL"][ip]
        base = base[base >= np.datetime64("2026-11-09")]          # les besoins commencent le 09/11 (la semaine d'avance n'en a aucun, H22)
        if len(base) == 0:
            continue
        dates = rng.choice(base, size=n) + rng.integers(0, 7, size=n).astype("timedelta64[D]")
        poids = rng.choice([30, 200, 800, 2500, 6000, 9000], size=n) * rng.uniform(0.8, 1.2, size=n)
        c = couple_fictif(list(zip(dates.astype(str), poids)), ligne=str(rng.choice(list(moteur["grille"].index))))
        r = moteur["evaluer_dp_inter"](c, ip); fb = _force_brute_inter(moteur, c, ip)
        assert (r is None) == (fb is None)
        if r is not None:
            assert r["cout"] == pytest.approx(fb, abs=1e-6)


def test_lissage_tolerance_zero_ne_coute_rien(moteur):
    cand = moteur["evaluer_tous"](moteur["idx_tous"], un_camion=True, mode="libre")
    best = {k: min(v, key=lambda x: x["cout"]) for k, v in cand.items() if v}
    choix, cout = moteur["lissage"](cand, best, 0.0)
    assert cout == pytest.approx(sum(b["cout"] for b in best.values()), abs=1e-6)
    assert set(choix) == set(best)
