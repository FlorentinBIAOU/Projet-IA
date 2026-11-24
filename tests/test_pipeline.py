"""Tests du flux complet (milestone 5) : planning brut -> main.py -> fichiers de resultats.

    pytest tests -v
"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main as programme  # noqa: E402
from src import config, preparation  # noqa: E402
from src.pipeline import executer  # noqa: E402

PUBLIE = config.DONNEES / "processed"
REFERENCE = json.loads((Path(__file__).parent / "reference_resultats.json").read_text(encoding="utf-8"))["versions"]


@pytest.fixture(scope="module")
def brut():
    return (preparation.charger_planning(config.CHEMIN_PLANNING), preparation.charger_distances(config.CHEMIN_DISTANCES),
            preparation.charger_grille_pdf(config.CHEMIN_GRILLE))


@pytest.fixture(scope="module")
def execution(brut, tmp_path_factory):
    dossier = tmp_path_factory.mktemp("resultats")
    return executer(*brut, versions=config.VERSIONS, version_retenue="strict", dossier_sortie=dossier)


# ---------------------------------------------------------------- les memes resultats que les notebooks
@pytest.mark.parametrize("fichier", ["profils_couples", "contenu_camions", "planning_propre", "journal_pipeline"])
def test_fichiers_identiques_a_ceux_des_notebooks(execution, fichier):
    """Le decoupage en modules ne change aucun resultat : fichiers identiques octet pour octet."""
    assert execution.fichiers[fichier].read_bytes() == (PUBLIE / f"{fichier}.csv").read_bytes()


def test_resume_et_lignes_inconnues_identiques_aux_chiffres_publies(execution):
    resume = pd.read_csv(execution.fichiers["resume_economies"]).set_index("indicateur")["valeur"]
    publie = pd.read_csv(PUBLIE / "resume_economies.csv").set_index("indicateur")["valeur"]
    for ligne in publie.index:
        if ligne == "Version du moteur (MODE_PROFIL)":
            assert resume[ligne] == publie[ligne]
        else:   # un centime d'ecart au plus : les lignes inconnues sont recalculees (le notebook en avait ecrit le total en dur)
            assert float(resume[ligne]) == pytest.approx(float(publie[ligne]), abs=0.011)
    inc, pub = pd.read_csv(execution.fichiers["lignes_inconnues"]), pd.read_csv(PUBLIE / "lignes_inconnues.csv")
    assert inc.drop(columns="cout").equals(pub.drop(columns="cout"))
    assert inc["cout"].tolist() == pytest.approx(pub["cout"].tolist(), abs=1e-9)


@pytest.mark.parametrize("mode", config.VERSIONS)
def test_resultats_conformes_a_la_reference(execution, mode):
    r = execution.resultats[mode]; c = r.contenu
    assert r.cout == pytest.approx(REFERENCE[mode]["cout"], abs=0.01)
    assert c["camion_id"].nunique() == REFERENCE[mode]["camions"]
    assert c[~c["envoi_exceptionnel"]]["camion_id"].nunique() == REFERENCE[mode]["livraisons"]


def test_comparaison_des_versions(execution):
    comp = execution.comparaison.set_index("version")
    assert comp.loc["libre", "cout"] <= comp.loc["intermediaire", "cout"] <= comp.loc["strict", "cout"]
    assert comp.loc["strict", "part semaines respectees %"] == 100.0


def test_controles_independants_passent(execution):
    for mode, liste in execution.controles_independants.items():
        assert all(ok for _, ok, _ in liste), (mode, [n for n, ok, _ in liste if not ok])


# ---------------------------------------------------------------- la ligne de commande
def test_main_cree_les_fichiers(tmp_path, capsys):
    code = programme.main(["--silencieux", "--sortie", str(tmp_path)])
    sortie = capsys.readouterr().out
    assert code == 0
    for fichier in ("profils_couples", "contenu_camions", "resume_economies"):
        assert (tmp_path / f"{fichier}.csv").exists()
    assert "Economie" in sortie and "42.7" in sortie


def test_main_fichier_introuvable(tmp_path, capsys):
    assert programme.main([str(tmp_path / "n_existe_pas.csv"), "--silencieux", "--sortie", str(tmp_path)]) == 1
    assert "introuvable" in capsys.readouterr().err.lower()


def test_main_colonne_manquante(tmp_path, capsys):
    mauvais = tmp_path / "planning.csv"
    planning = preparation.charger_planning(config.CHEMIN_PLANNING).drop(columns=["weight"])
    planning.to_csv(mauvais, index=False)
    assert programme.main([str(mauvais), "--silencieux", "--sortie", str(tmp_path / "out")]) == 1
    assert "weight" in capsys.readouterr().err


def test_main_doublons_refuses(tmp_path, capsys):
    planning = preparation.charger_planning(config.CHEMIN_PLANNING)
    pd.concat([planning, planning.head(3)]).to_csv(tmp_path / "planning.csv", index=False)
    assert programme.main([str(tmp_path / "planning.csv"), "--silencieux", "--sortie", str(tmp_path / "out")]) == 1
    assert "doublons" in capsys.readouterr().err


# ---------------------------------------------------------------- un autre planning, que nous ne connaissons pas
def test_planning_reduit_de_20_pour_cent(brut):
    planning, distances, grille = brut
    reduit = planning.drop(planning.sample(frac=0.2, random_state=1).index)
    ex = executer(reduit, distances, grille)          # les controles internes et independants s'appliquent
    assert ex.resultats["strict"].cout > 0
    assert ex.contenu_camions["camion_id"].nunique() > 0


def test_fournisseur_au_dela_de_650_km(brut):
    """La derniere ligne de la grille ('>650') ne doit pas faire planter le flux."""
    planning, distances, grille = brut
    lointain = distances.copy()
    actifs = planning.loc[planning["schedule_quantity"] > 0, "supplier_id"].unique()
    lointain.loc[lointain["supplier_id"] == actifs[0], "distance"] = 700.0
    ex = executer(planning, lointain, grille)
    assert (ex.planning_propre["ligne_grille"] == ">650").any()
    assert ex.resultats["strict"].cout > 0


# ---------------------------------------------------------------- le premier jour de livraison est un reglage
def test_sans_livraison_avant_le_premier_besoin_on_retrouve_les_resultats_d_avant():
    """PREMIER_JOUR_LIVRAISON = 09/11 : aucun jour de livraison avant le premier besoin (resultats du milestone 3 avant la semaine d'avance)."""
    from src.moteur import Moteur
    planning = pd.read_csv(PUBLIE / "planning_propre.csv", parse_dates=["date", "semaine"])
    grille = pd.read_csv(PUBLIE / "grille_prix.csv", index_col=0)
    moteur = Moteur(planning, grille, {"PREMIER_JOUR_LIVRAISON": "2026-11-09"})
    assert moteur.jours_ouvres[0] == pd.Timestamp("2026-11-09") and len(moteur.jours_ouvres) == 30
    attendu = {"libre": (74908.28, 567), "intermediaire": (80754.80, 635), "strict": (83394.55, 659)}
    for mode, (cout, camions) in attendu.items():
        r = moteur.lancer(mode=mode)
        assert r.cout == pytest.approx(cout, abs=0.01) and r.contenu["camion_id"].nunique() == camions


def test_le_premier_jour_de_livraison_est_sept_jours_avant_le_premier_besoin_par_defaut():
    from src.moteur import Moteur
    planning = pd.read_csv(PUBLIE / "planning_propre.csv", parse_dates=["date", "semaine"])
    grille = pd.read_csv(PUBLIE / "grille_prix.csv", index_col=0)
    moteur = Moteur(planning, grille)
    assert moteur.d0 == planning.loc[planning["statut"] == "optimise", "date"].min() - pd.Timedelta(7, unit="D")
    assert moteur.d0 == pd.Timestamp("2026-11-02") and len(moteur.jours_ouvres) == 35


# ---------------------------------------------------------------- le potentiel du milestone 2
def test_potentiel_des_couples_identique_au_jalon_2():
    """Le potentiel (un seul envoi par couple et par semaine) retrouve celui publie par le milestone 2."""
    from src import tarifs
    planning = pd.read_csv(PUBLIE / "planning_propre.csv", parse_dates=["date", "semaine"])
    grille = pd.read_csv(PUBLIE / "grille_prix.csv", index_col=0)
    grille.columns = grille.columns.astype(str); grille.index = grille.index.astype(str)
    pot = tarifs.potentiel_couples(tarifs.envois_actuels(planning, grille), grille)
    ref = pd.read_csv(PUBLIE / "potentiel_couples.csv")
    m = pot.merge(ref, on=["supplier_id", "plant"], suffixes=("", "_ref"))
    assert len(m) == len(ref) == len(pot)
    assert m["gain_eur"].tolist() == pytest.approx(m["gain_eur_ref"].tolist(), abs=1e-6)
    assert pot["gain_eur"].sum() == pytest.approx(ref["gain_eur"].sum(), abs=1e-6)
