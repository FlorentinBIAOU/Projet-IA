"""Tests de dashboard/sorties_client.py : sorties 1 a 3, calendrier d'un couple, lissage, controles.

    pytest tests/test_sorties_client.py -v
"""
import pandas as pd
import pytest

from dashboard import sorties_client as sc
from src import config, preparation
from src.pipeline import executer

TRANCHES = config.TRANCHES_KG
COUPLE_SLIDES = [("SUP_00085", "PLT_004"), ("SUP_00144", "PLT_001"), ("SUP_00059", "PLT_003"), ("SUP_00080", "PLT_004"), ("SUP_00149", "PLT_004")]


def _executer(planning, distances, version="strict"):
    grille = preparation.charger_grille_pdf(config.CHEMIN_GRILLE)
    ex = executer(planning, distances, grille, versions=(version,))
    ex.planning_brut, ex.distances_brutes = planning, distances            # comme le fait app.calculer
    return ex


@pytest.fixture(scope="module")
def client():
    planning = pd.read_csv(config.CHEMIN_PLANNING, encoding="utf-8-sig")
    return _executer(planning, pd.read_csv(config.CHEMIN_DISTANCES))


def _petit_planning(en_plus=()):
    """Deux couples sur deux semaines, fabriques a la main."""
    lignes = [("2026-11-09", "SUP_A", "MAT_1", "PLT_001", 100, 100.0, 1.0), ("2026-11-10", "SUP_A", "MAT_1", "PLT_001", 100, 200.0, 1.0),
              ("2026-11-16", "SUP_A", "MAT_2", "PLT_001", 50, 300.0, 1.0),
              ("2026-11-09", "SUP_B", "MAT_3", "PLT_002", 10, 400.0, 2.0), ("2026-11-12", "SUP_B", "MAT_3", "PLT_002", 10, 500.0, 2.0),
              ("2026-11-17", "SUP_B", "MAT_4", "PLT_002", 5, 50.0, 0.5)] + list(en_plus)
    planning = pd.DataFrame(lignes, columns=["date", "supplier_id", "material", "plant", "schedule_quantity", "weight", "volume"])
    planning["unloading_point"] = "ULP_0001"
    planning["transmission_date"], planning["version_date"] = "2026-11-04", "2026-11-08"
    distances = pd.DataFrame({"supplier_id": ["SUP_A", "SUP_B"], "distance": [40.0, 120.0]})        # lignes de grille 50 et 125 km
    return planning, distances


def _prix(ex, ligne, poids):
    """Le prix lu a la main dans la grille : colonne = premiere tranche de poids au-dessus du poids."""
    colonne = next(str(t) for t in TRANCHES if poids <= t)
    return float(ex.moteur.grille.loc[str(ligne), colonne])


# ---------------------------------------------------------------------------------------------- fichier du client (non-regression)
def test_resultats_du_client_inchanges(client):
    assert round(client.resultats["strict"].cout, 2) == 82110.82
    resume, _ = sc.camions(client, "strict")
    assert (resume["type"] != sc.TYPE_NON).sum() == 652                                      # 651 camions + 1 envoi exceptionnel


def test_sortie1_contient_tous_les_couples_du_fichier(client):
    s1 = sc.sortie1(client, "strict")
    assert len(s1) == 185 and s1[["fournisseur", "usine"]].drop_duplicates().shape[0] == 185
    assert set(s1["statut"]) == {sc.STATUT_OPT, sc.STATUT_PART, sc.STATUT_NON, sc.STATUT_VIDE}
    assert (s1["statut"] == sc.STATUT_VIDE).sum() == 5                                       # couples sans aucune ligne exploitable


def test_sortie2_138_lignes_non_optimisees_et_camions(client):
    s2, mat = sc.sortie2(client, "strict")
    assert (s2["type"] == sc.TYPE_NON).sum() == 138 and s2.loc[s2["type"] == sc.TYPE_NON, "lignes"].sum() == 138
    assert set(mat["camion_id"]) == set(s2["camion_id"])                                      # chaque camion a ses materials
    assert s2["jour"].isin(sc.JOURS).all()


def test_sortie3_semaine_du_16_11_pour_les_5_couples_des_slides(client):
    s3 = sc.sortie3(client, "strict", "2026-11-16")
    cinq = s3[[(f, u) in COUPLE_SLIDES for f, u in zip(s3["fournisseur"], s3["usine"])]]
    assert len(cinq) == 5 and round(cinq["cout_actuel_semaine"].sum()) == 3994                # slide 12 : 3 994 EUR par semaine
    assert (cinq["cout_optimise_semaine"] < cinq["cout_actuel_semaine"]).all()


def test_slide_sortie2_le_camion_du_lundi_16_11(client):
    """Slide 11 : le camion de SUP_00085 x PLT_004 du lundi 16/11 remplace 5 livraisons, 36 lignes, 11 660 kg."""
    cal = sc.calendrier_couple(client, "strict", ("SUP_00085", "PLT_004"))
    camion = next(t for t in cal["camions"].values() if t["date"] == pd.Timestamp("2026-11-16"))
    assert camion["nb_lignes"] == 36 and round(camion["poids"]) == 11660 and len(camion["besoins"]) == 5


def test_les_sommes_de_la_sortie3_sont_les_couts_globaux(client):
    s3 = sc.sortie3(client, "strict")
    assert s3["cout_actuel_horizon"].sum() == pytest.approx(client.baselines["baseline_h20"], abs=0.5)
    assert s3["cout_optimise_horizon"].sum() == pytest.approx(client.resultats["strict"].cout, abs=0.5)


def test_tous_les_controles_passent(client):
    controles = sc.verifier(client, "strict")
    assert len(controles) >= 12 and all(c["ok"] for c in controles), [c["nom"] for c in controles if not c["ok"]]


def test_calendrier_du_couple_SUP_00107_PLT_001(client):
    cle = ("SUP_00107", "PLT_001")
    prof = client.moteur.PROFILS[client.resultats["strict"].choix[cle]["idx"]]
    cal = sc.calendrier_couple(client, "strict", cle, "apres")
    besoins = [b for s in cal["semaines"] for j in s["jours"] for b in j["besoins"]]
    assert besoins and all(b["camion"] in cal["camions"] for b in besoins)                    # chaque besoin a un camion
    assert all(0 <= (b["date"] - b["parti_le"]).days <= config.AVANCE_MAX for b in besoins)    # avance de 0 a 7 jours
    assert all(t["date"].weekday() in prof["jours"] for t in cal["camions"].values() if t["type"] == sc.TYPE_OPT)
    p = client.planning_propre
    assert sum(b["nb_lignes"] for b in besoins) == ((p["supplier_id"] == cle[0]) & (p["plant"] == cle[1])).sum()


def test_avant_et_apres_lissage_ne_different_que_pour_les_couples_deplaces(client):
    deplaces = set(sc.couples_deplaces(client, "strict"))
    assert deplaces                                                                           # le lissage deplace des profils
    assert sc.phrase_deplacement(client, "strict", ("SUP_00107", "PLT_001")).startswith("profil déplacé")
    for cle in list(client.moteur.COUPLES)[:60]:
        dates = lambda etat: sorted((t["date"], round(t["poids"], 3)) for t in sc.calendrier_couple(client, "strict", cle, etat)["camions"].values())
        if cle not in deplaces:
            assert dates("avant") == dates("apres"), cle
            assert sc.phrase_deplacement(client, "strict", cle) == ""


def test_la_repartition_par_jour_compte_les_trois_etats(client):
    rep = sc.repartition_jours(client, "strict")
    assert set(rep["etat"]) == {"aujourdhui", "avant", "apres"} and set(rep["jour"]) <= set(range(5))
    assert rep[rep["etat"] == "aujourdhui"]["n"].sum() > rep[rep["etat"] == "apres"]["n"].sum()    # moins de livraisons apres


# ---------------------------------------------------------------------------------------------- petit planning fait a la main
def test_petit_planning_sorties_et_controles_egales_au_calcul_a_la_main():
    ex = _executer(*_petit_planning())
    a_la_main = {("SUP_A", "PLT_001"): _prix(ex, 50, 100) + _prix(ex, 50, 200) + _prix(ex, 50, 300),      # une livraison par jour de besoin
                 ("SUP_B", "PLT_002"): _prix(ex, 125, 400) + _prix(ex, 125, 500) + _prix(ex, 125, 50)}
    s3 = sc.sortie3(ex, "strict").set_index(["fournisseur", "usine"])
    for cle, attendu in a_la_main.items():
        assert s3.loc[cle, "cout_actuel_horizon"] == pytest.approx(attendu, abs=0.01)
    s1 = sc.sortie1(ex, "strict", "2026-11-09")
    assert len(s1) == 2 and set(s1["statut"]) == {sc.STATUT_OPT} and s1["livraisons_sem_actuelles"].tolist() == [2, 2]
    s2, mat = sc.sortie2(ex, "strict")
    assert s2["lignes"].sum() == 6 and s2["poids"].sum() == pytest.approx(1550.0) and s2["livraisons_remplacees"].sum() == 6
    for cle, g in s2.groupby(["fournisseur", "usine"]):                                       # le prix d'un camion = la grille, lu a la main
        ligne = 50 if cle[0] == "SUP_A" else 125
        assert g["prix"].sum() == pytest.approx(sum(_prix(ex, ligne, p) for p in g["poids"]), abs=0.01)
        assert s3.loc[cle, "cout_optimise_horizon"] == pytest.approx(g["prix"].sum(), abs=0.01)
        assert g["prix"].sum() <= a_la_main[cle] + 0.01                                            # on ne paie jamais plus qu'aujourd'hui
    assert all(c["ok"] for c in sc.verifier(ex, "strict"))


def test_planning_modifie_les_sorties_changent():
    base = _executer(*_petit_planning())
    plus = _executer(*_petit_planning(en_plus=[("2026-11-10", "SUP_A", "MAT_9", "PLT_001", 20, 150.0, 1.0)]))      # le 10/11 passe de 200 a 350 kg
    assert sc.sortie2(plus, "strict")[0]["lignes"].sum() == 7 and sc.sortie2(plus, "strict")[0]["poids"].sum() == pytest.approx(1700.0)
    attendu = _prix(plus, 50, 100) + _prix(plus, 50, 350) + _prix(plus, 50, 300)
    s3 = sc.sortie3(plus, "strict").set_index(["fournisseur", "usine"])
    assert s3.loc[("SUP_A", "PLT_001"), "cout_actuel_horizon"] == pytest.approx(attendu, abs=0.01)
    assert s3.loc[("SUP_A", "PLT_001"), "cout_actuel_horizon"] > sc.sortie3(base, "strict").set_index(["fournisseur", "usine"]).loc[("SUP_A", "PLT_001"), "cout_actuel_horizon"]
    assert all(c["ok"] for c in sc.verifier(plus, "strict"))


def test_un_defaut_est_detecte_par_les_controles():
    ex = _executer(*_petit_planning())
    contenu = ex.resultats["strict"].contenu
    contenu.loc[contenu.index[0], "avance_jours"] = 99
    ex.resultats["strict"].contenu = contenu.iloc[1:]                                         # une ligne oubliee
    controles = {c["nom"]: c for c in sc.verifier(ex, "strict")}
    assert not controles["Chaque ligne du planning est dans un camion (une seule fois)"]["ok"]
    assert controles["Chaque ligne du planning est dans un camion (une seule fois)"]["nb"] == 1
