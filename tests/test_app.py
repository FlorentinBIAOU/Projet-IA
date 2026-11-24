"""Tests du dashboard Streamlit (app.py), executes sans navigateur avec le banc d'essai de Streamlit.

    pytest tests -v
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
ONGLETS = ["Synthèse", "Sorties du projet", "Analyse des gains", "Économies et potentiel", "Usines et calendrier", "Courbes de prix",
           "Contrôles et données"]


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
    assert "Moins de camions" in texte and "Comment ça marche" in texte      # l'accueil explique, rien n'est calcule
    assert len(at.tabs) == 0 and "82 111" not in texte


def test_calcul_version_stricte_par_defaut():
    at = _lancer()
    assert not at.exception and not at.error
    texte = _texte(at)
    assert "82 111 €" in texte and "143 321 €" in texte                     # coût après et avant
    assert "−42,7 %" in texte and "652" in texte                            # économie et camions
    assert [t.label for t in at.tabs] == ONGLETS


@pytest.mark.parametrize("version, cout", [("intermediaire", "79 096 €"), ("libre", "74 908 €")])
def test_les_autres_versions(version, cout):
    at = _lancer(version)
    assert not at.exception and not at.error
    assert cout in _texte(at)


def test_comparaison_des_trois_versions_et_choix_du_detail():
    at = _lancer("toutes")
    assert not at.exception and not at.error
    texte = _texte(at)
    assert "Le choix de la version" in texte and "82 111 €" in texte and "79 096 €" in texte and "74 908 €" in texte    # les trois cartes
    at.selectbox[0].set_value("libre").run()
    assert not at.exception
    assert "−47,7 %" in _texte(at)                                          # le détail suit la version choisie


def test_les_deux_sorties_du_projet_sont_telechargeables():
    """Sortie 1 (profils), sortie 2 (contenu des camions) et l'archive complete : trois boutons de telechargement."""
    at = _lancer()
    assert not at.exception
    libelles = [b.proto.label for b in at.get("download_button")]
    assert libelles == ["Télécharger la sortie 1 (profils_couples.csv)", "Télécharger la sortie 2 (contenu_camions.csv)",
                        "Tout télécharger (archive .zip)"]
