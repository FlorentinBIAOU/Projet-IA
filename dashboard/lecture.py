"""Lecture tolerante des tableaux deposes (planning, distances) : Excel (.xlsx) ou CSV.

Un fichier prepare a la main n'a pas toujours la forme ideale : un titre au-dessus du tableau, plusieurs feuilles,
des noms de colonnes en majuscules ou avec des espaces, des nombres a virgule ecrits comme du texte, un CSV a point-virgule
ou enregistre en Latin-1. On retrouve le tableau tout seul ; s'il manque des colonnes, le message dit lesquelles.
"""
import io

import pandas as pd

COLONNES_NUMERIQUES = ["schedule_quantity", "weight", "volume", "distance"]
LIGNES_EXPLOREES = 30                      # le tableau commence dans les 30 premieres lignes d'une feuille


# Autres noms courants d'une colonne (en francais, avec l'unite...) -> nom attendu
SYNONYMES = {"distance_(km)": "distance", "distance_km": "distance", "km": "distance", "distance(km)": "distance",
             "fournisseur": "supplier_id", "supplier": "supplier_id", "id_fournisseur": "supplier_id"}
# Colonnes qui trahissent un planning (pour reconnaitre un planning depose a la place des distances)
SIGNATURE_PLANNING = {"material", "plant", "schedule_quantity"}


def _normaliser(nom):
    n = str(nom).strip().lower().replace(" ", "_")
    return SYNONYMES.get(n, n)


def _depuis_brut(brut, attendues):
    """Cherche la ligne d'en-tete (celle qui contient toutes les colonnes attendues) ; renvoie le tableau ou None."""
    for i in range(min(LIGNES_EXPLOREES, len(brut))):
        entete = [_normaliser(x) for x in brut.iloc[i]]
        if set(attendues) <= set(entete):
            tableau = brut.iloc[i + 1:].copy()
            tableau.columns = entete
            tableau = tableau.loc[:, [c for c in tableau.columns if c not in ("", "nan")]]
            return tableau.dropna(how="all").reset_index(drop=True)
    return None


def _nombres(tableau):
    """Nombres ecrits comme du texte (« 12,5 ») -> nombres. Une valeur vraiment non numerique reste telle quelle (le controle la signalera)."""
    for col in COLONNES_NUMERIQUES:
        if col in tableau.columns and tableau[col].dtype == object:
            converti = pd.to_numeric(tableau[col].astype(str).str.replace(" ", "").str.replace(" ", "").str.replace(",", "."), errors="coerce")
            garde = tableau[col].isna() | converti.notna()
            tableau[col] = converti.where(garde, tableau[col])
            if garde.all():
                tableau[col] = converti.astype(float)
    return tableau


def lire_tableau(contenu, attendues, nom="le fichier"):
    """Lit un tableau depose (octets) qui doit contenir les colonnes `attendues`. Leve ValueError avec un message clair sinon."""
    attendues = [_normaliser(c) for c in attendues]
    if contenu[:2] == b"PK":                                       # un .xlsx est une archive zip
        feuilles = pd.read_excel(io.BytesIO(contenu), sheet_name=None, header=None, dtype=object)
        for brut in feuilles.values():
            tableau = _depuis_brut(brut, attendues)
            if tableau is not None:
                return _nombres(tableau)
        trouvees = sorted({_normaliser(x) for brut in feuilles.values() for x in brut.head(LIGNES_EXPLOREES).values.ravel() if pd.notna(x)})
    elif contenu[:4] == b"\xd0\xcf\x11\xe0":                     # ancien format .xls
        raise ValueError(f"{nom} est au format Excel 97-2003 (.xls) : enregistrez-le au format .xlsx ou CSV.")
    else:
        texte = None
        for encodage in ("utf-8-sig", "latin-1"):
            try:
                texte = contenu.decode(encodage)
                break
            except UnicodeDecodeError:
                continue
        trouvees = []
        for sep in (",", ";", "\t"):
            try:
                brut = pd.read_csv(io.StringIO(texte), sep=sep, header=None, dtype=str, keep_default_na=False, engine="python")
            except pd.errors.ParserError:                              # mauvais separateur : on essaie le suivant
                continue
            brut = brut.replace("", None)
            tableau = _depuis_brut(brut, attendues)
            if tableau is not None:
                return _nombres(tableau)
            vues = sorted({_normaliser(x) for x in brut.head(LIGNES_EXPLOREES).values.ravel() if x is not None})
            if len(set(vues) & set(attendues)) > len(set(trouvees) & set(attendues)):     # on garde l'essai le plus proche, pour le message
                trouvees = vues
    manquantes = [c for c in attendues if c not in trouvees]
    if "distance" in attendues and SIGNATURE_PLANNING <= set(trouvees):
        raise ValueError(f"{nom[:1].upper() + nom[1:]} ressemble au planning (colonnes material, plant…) : vérifiez que chaque fichier est déposé "
                         "dans la bonne case. Le fichier des distances n'a que deux colonnes : supplier_id, distance.")
    raise ValueError(f"Dans {nom}, colonnes introuvables : {', '.join(manquantes)}. Colonnes attendues : {', '.join(attendues)}.")
