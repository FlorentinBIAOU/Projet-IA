"""Tests de dashboard/lecture.py : les fichiers deposes sous des formes courantes donnent le meme resultat."""
import io

import pandas as pd
import pytest

from dashboard.lecture import lire_tableau
from src import config, preparation
from src.pipeline import executer

PLANNING = pd.read_csv(config.CHEMIN_PLANNING, encoding="utf-8-sig")
DISTANCES = pd.read_csv(config.CHEMIN_DISTANCES)


def _cout(planning, distances):
    ex = executer(planning, distances, preparation.charger_grille_pdf(config.CHEMIN_GRILLE))
    return round(ex.resultats["strict"].cout, 2)


def _excel(feuilles):
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as w:
        for nom, (df, decalage) in feuilles.items():
            if decalage:                                                     # un titre au-dessus du tableau
                pd.DataFrame([["Planning de livraison - export"]]).to_excel(w, sheet_name=nom, index=False, header=False)
            df.to_excel(w, sheet_name=nom, index=False, startrow=decalage)
    return tampon.getvalue()


def test_csv_du_client_meme_resultat():
    p = lire_tableau(config.CHEMIN_PLANNING.read_bytes(), config.COLONNES_PLANNING)
    d = lire_tableau(config.CHEMIN_DISTANCES.read_bytes(), config.COLONNES_DISTANCES)
    assert len(p) == len(PLANNING) and _cout(p, d) == 82110.82


def test_excel_avec_titre_et_plusieurs_feuilles_meme_resultat():
    contenu = _excel({"Notes": (pd.DataFrame({"a": [1]}), 0), "Planning": (PLANNING, 2)})
    p = lire_tableau(contenu, config.COLONNES_PLANNING)
    d = lire_tableau(_excel({"Feuil1": (DISTANCES, 0)}), config.COLONNES_DISTANCES)
    assert len(p) == len(PLANNING) and _cout(p, d) == 82110.82


def test_csv_point_virgule_virgule_decimale_et_majuscules():
    contenu = PLANNING.rename(columns=str.upper).to_csv(sep=";", decimal=",", index=False).encode("latin-1", errors="replace")
    p = lire_tableau(contenu, config.COLONNES_PLANNING)
    assert list(p.columns[:3]) == ["date", "supplier_id", "material"]
    assert p["weight"].sum() == pytest.approx(PLANNING["weight"].sum())


def test_colonne_manquante_message_clair():
    contenu = PLANNING.drop(columns="weight").to_csv(index=False).encode()
    with pytest.raises(ValueError, match="colonnes introuvables : weight"):
        lire_tableau(contenu, config.COLONNES_PLANNING, "le planning")


def test_ancien_format_xls_refuse_avec_un_message():
    with pytest.raises(ValueError, match=r"\.xlsx"):
        lire_tableau(b"\xd0\xcf\x11\xe0" + b"\x00" * 100, config.COLONNES_PLANNING, "le planning")


def test_colonne_distance_en_km_reconnue():
    contenu = DISTANCES.rename(columns={"distance": "Distance (km)"}).to_csv(index=False).encode()
    d = lire_tableau(contenu, config.COLONNES_DISTANCES)
    assert d["distance"].sum() == pytest.approx(DISTANCES["distance"].sum())


def test_planning_depose_a_la_place_des_distances():
    with pytest.raises(ValueError, match="ressemble au planning"):
        lire_tableau(config.CHEMIN_PLANNING.read_bytes(), config.COLONNES_DISTANCES, "le fichier des distances")
