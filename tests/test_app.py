"""Tests du dashboard Streamlit (app.py), executes sans navigateur avec le banc d'essai de Streamlit.

    pytest tests -v
"""
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
os.environ["CONSOLIDATION_FICHIERS_CLIENT"] = "1"        # le banc d'essai ne sait pas deposer de fichier : il utilise ceux du client
ONGLETS_SORTIES = ["Sortie 1 · Profil par couple", "Sortie 2 · Camions", "Sortie 3 · Savings par couple"]


def _lancer(version=None):
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    if version is not None:
        at.radio[0].set_value(version)
    at.button[0].click().run()
    return at


def _texte(at):
    """Tout le texte affiche par la page (cartes, bandeau, messages), espaces insecables ramenes a des espaces."""
    return " ".join(m.value for m in at.markdown).replace(" ", " ")


def test_page_d_accueil_sans_calcul():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    texte = _texte(at)
    assert "Planification améliorée" in texte and "Déposez" in texte      # l'accueil explique, rien n'est calcule
    assert len(at.tabs) == 0 and "82 111" not in texte


def test_calcul_version_stricte_par_defaut():
    at = _lancer()
    assert not at.exception and not at.error
    texte = _texte(at)
    assert "toutes les semaines" in texte and "143 321 → 82 111 €" in texte and "171 / 185" in texte    # par défaut : tout l'horizon
    assert [t.label for t in at.tabs] == ONGLETS_SORTIES


@pytest.mark.parametrize("version, cout", [("intermediaire", "79 096 €"), ("libre", "74 908 €")])
def test_les_autres_versions(version, cout):
    at = _lancer(version)
    at.selectbox[0].select_index(0).run()                                   # toutes les semaines : le coût de tout l'horizon
    assert not at.exception and not at.error
    assert cout in _texte(at)


def test_comparaison_des_trois_versions_et_choix_du_detail():
    at = _lancer("toutes")
    assert not at.exception and not at.error
    texte = _texte(at)
    assert "Version affichée" in [s.label for s in at.selectbox]
    at.selectbox[0].set_value("libre").run()
    at.selectbox[1].select_index(0).run()                                   # toutes les semaines
    assert not at.exception
    assert "−47,7 %" in _texte(at)                                          # le détail suit la version choisie


def test_les_sorties_sont_telechargeables():
    """Tout en CSV (archive), puis CSV de la sortie 1, de la sortie 2 (camions et materials) et de la sortie 3."""
    at = _lancer()
    assert not at.exception
    libelles = [b.proto.label for b in at.get("download_button")]
    assert libelles[0] == "Tout télécharger (CSV)"
    assert libelles.count("Télécharger en CSV") == 2 and "Camions en CSV" in libelles and "Materials en CSV" in libelles


def test_la_barre_laterale_garde_la_semaine_et_les_filtres_apres_le_calcul():
    at = _lancer()
    assert [s.label for s in at.selectbox] == ["Semaine"]
    assert at.selectbox[0].value is None                                    # par défaut : toutes les semaines
    at.selectbox[0].select_index(2).run()                                   # la semaine du 16/11
    assert "semaine du 16/11" in _texte(at)
    assert [m.label for m in at.multiselect] == ["Usines", "Fournisseurs"]
    at.selectbox[0].select_index(0).run()                                  # toutes les semaines
    texte = _texte(at)
    assert not at.exception and "toutes les semaines" in texte
    assert "143 321 → 82 111 €" in texte and "−42,7 %" in texte and "1 604 → 652" in texte      # tout l'horizon
    at.multiselect[0].set_value(["PLT_001"]).run()
    assert not at.exception and "−" in _texte(at)                            # les indicateurs suivent le filtre


# ---------------------------------------------------------------------------------------------- pages (avec le résultat déjà calculé)
@pytest.fixture(scope="module")
def contexte():
    import pandas as pd
    from dashboard import explorateur as xp
    from src import config, preparation
    from src.pipeline import executer
    planning, distances = pd.read_csv(config.CHEMIN_PLANNING, encoding="utf-8-sig"), pd.read_csv(config.CHEMIN_DISTANCES)
    ex = executer(planning, distances, preparation.charger_grille_pdf(config.CHEMIN_GRILLE), versions=("strict",))
    ex.planning_brut, ex.distances_brutes = planning, distances
    return xp.construire_contexte(ex, "strict", ("strict",), "test", "2026-11-16", [], [])


def _page(nom, contexte, **etat):
    def script():
        import streamlit as st
        from dashboard import page_details, page_gains, page_sorties
        from dashboard import style
        style.appliquer_style()
        {"sorties": page_sorties, "details": page_details, "gains": page_gains}[st.session_state["page_testee"]].page()
    at = AppTest.from_function(script, default_timeout=180)
    at.session_state["ctx"], at.session_state["page_testee"] = contexte, nom
    for cle, valeur in etat.items():
        at.session_state[cle] = valeur
    return at.run()


def test_page_details_affiche_le_couple_choisi_et_son_calendrier(contexte):
    at = _page("details", contexte, couple_sel=("SUP_00107", "PLT_001"))
    assert not at.exception
    texte = _texte(at)
    assert "SUP_00107 × PLT_001" in texte and "Camions optimisés" in texte and "Coût avant → après" in texte
    assert 'class="pastilles-jours"' in texte and "profil déplacé" not in texte.replace("Lissage", "")


def test_page_details_garde_le_couple_choisi_apres_un_changement_de_filtre(contexte):
    at = _page("details", contexte, couple_sel=("SUP_00085", "PLT_004"))
    assert at.selectbox[0].value == ("SUP_00085", "PLT_004")
    assert at.session_state["couple_sel"] == ("SUP_00085", "PLT_004")


def test_page_gains_a_ses_quatre_onglets(contexte):
    at = _page("gains", contexte)
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Avant / après", "Par usine", "Lissage", "Couples"]


def test_sans_fichier_depose_le_calcul_est_impossible(monkeypatch):
    monkeypatch.delenv("CONSOLIDATION_FICHIERS_CLIENT")
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert at.button[0].label == "Lancer le calcul" and at.button[0].disabled
    assert "À déposer : planning, distances, grille." in [c.value for c in at.caption]
