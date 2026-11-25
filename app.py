"""Dashboard Streamlit : consolidation des livraisons.

Lancer (depuis la racine du projet, environnement Python active) :

    streamlit run app.py          # ou ./lancer_app.sh

On depose les fichiers d'entree (planning, distances, grille tarifaire), on choisit la version du moteur, et on obtient :
  - les trois sorties du projet (profil par couple, camions, savings par couple), en CSV et en Excel ;
  - le detail d'un couple : calendrier avant / apres, impact du lissage, contenu de chaque camion ;
  - les gains (avant / apres, par usine, lissage, couples) et les controles.
Quatre pages : Sorties, Details des sorties, Gains, Controles (st.navigation).
"""
import hashlib
import io

import pandas as pd
import streamlit as st

from dashboard import explorateur as xp
from dashboard import page_controles, page_details, page_gains, page_sorties
from dashboard import sorties_client as sc
from dashboard import style
from src import config, preparation
from src.pipeline import executer

VERSIONS_COURTES = {"strict": "Stricte · recommandée", "intermediaire": "Intermédiaire", "libre": "Libre", "toutes": "Comparer les trois"}
VERSIONS_NOMS = xp.VERSIONS_NOMS
VERSIONS_EXPLICATIONS = {
    "strict": "Le rythme annoncé à chaque fournisseur est tenu **toutes les semaines** : un profil est un engagement.",
    "intermediaire": "Au moins **4 semaines** du profil sont respectées ; le reste, le moteur choisit au moins cher.",
    "libre": "Le profil est un maximum : le moteur choisit **les jours au moins chers**. Version de comparaison.",
    "toutes": "Calcule les trois versions pour **les comparer** : plus de souplesse coûte moins cher, mais le rythme est moins tenu.",
}
FORMATS_COURT = "Colonnes du planning : date, supplier_id, material, plant, unloading_point, schedule_quantity, weight, volume."
FORMATS = """
**Planning de livraisons** (CSV) : une ligne par besoin, avec les colonnes
`date, supplier_id, material, plant, unloading_point, schedule_quantity, weight, volume, transmission_date, version_date`.

**Distances** (CSV) : `supplier_id, distance` (en km).

**Grille tarifaire** (PDF du transporteur) : le tableau des coûts par tranche de distance et de poids.

Sans fichier déposé, l'application utilise ceux du client.
"""


@st.cache_resource(show_spinner=False)
def calculer(planning_octets, distances_octets, grille_octets, versions):
    """Lance tout le flux sur les fichiers donnes (en octets, pour que le cache reconnaisse un meme fichier)."""
    planning = pd.read_csv(io.BytesIO(planning_octets), encoding="utf-8-sig")
    distances = pd.read_csv(io.BytesIO(distances_octets))
    grille = preparation.charger_grille_pdf(io.BytesIO(grille_octets))
    ex = executer(planning, distances, grille, versions=versions, version_retenue=versions[0])
    ex.planning_brut, ex.distances_brutes = planning, distances          # pour lister tous les couples du fichier (sortie 1)
    return ex


def octets(televerse, chemin_defaut):
    """Les octets du fichier televerse, ou ceux du fichier du client si rien n'a ete televerse."""
    return televerse.getvalue() if televerse is not None else chemin_defaut.read_bytes()


# --------------------------------------------------------------------------------- page
st.set_page_config(page_title="Consolidation des livraisons", page_icon="🚚", layout="wide")
style.appliquer_style()
style.appliquer_style_calendrier()
style._css_haut()

calcul = st.session_state.get("calcul_demande", False)
c_logo, c_retour = st.columns([5, 1], vertical_alignment="center")
c_logo.markdown('<div class="logo-haut">Consolidation<span>.</span></div>', unsafe_allow_html=True)
if calcul and c_retour.button("← Accueil", width="stretch", key="retour_accueil"):
    st.session_state["calcul_demande"] = False
    st.rerun()
with st.expander("Fichiers et version", expanded=not calcul):
    c1, c2, c3 = st.columns(3)
    planning_tv = c1.file_uploader("Planning (CSV)", type="csv")
    distances_tv = c2.file_uploader("Distances (CSV)", type="csv")
    grille_tv = c3.file_uploader("Grille tarifaire (PDF)", type="pdf")
    c4, c5 = st.columns([4, 1], vertical_alignment="bottom")
    choix = c4.radio("Version", list(VERSIONS_COURTES), format_func=VERSIONS_COURTES.get, horizontal=True,
                     help="  \n".join(f"**{VERSIONS_COURTES[k]}** : {v}" for k, v in VERSIONS_EXPLICATIONS.items()))
    lancer = c5.button("Lancer le calcul", type="primary", width="stretch")

if lancer:
    st.session_state["calcul_demande"] = True
    st.rerun()                      # pour afficher le bouton « Accueil » et replier le panneau des fichiers

# ---------------------------------------------------------------- accueil (avant le calcul)
if not st.session_state.get("calcul_demande"):
    style.hero("Moins de camions. Aucun retard.", "Regroupez les livraisons des fournisseurs vers les usines.",
               pastilles=["Planning", "Moteur exact", "Contrôles automatiques"], sur_titre="Consolidation du planning de livraison")
    style.etapes([("1 · Déposez", "les fichiers, ou gardez ceux du client"), ("2 · Choisissez", "la version du moteur"), ("3 · Lancez", "le calcul")])
    st.stop()

# ---------------------------------------------------------------- calcul
versions = config.VERSIONS[::-1] if choix == "toutes" else (choix,)       # stricte d'abord
try:
    with st.spinner("Préparation du planning et calcul des livraisons..."):
        fichiers = (octets(planning_tv, config.CHEMIN_PLANNING), octets(distances_tv, config.CHEMIN_DISTANCES), octets(grille_tv, config.CHEMIN_GRILLE))
        ex = calculer(*fichiers, versions)
except ValueError as e:                              # fichier a corriger, ou solution refusee par les controles
    style.hero("Le calcul s'est arrêté", "Un des fichiers doit être corrigé avant de continuer.", sur_titre="Consolidation du planning de livraison")
    st.error(f"{e}")
    st.stop()
except Exception as e:                               # fichier illisible, PDF inattendu...
    style.hero("Impossible de lire les fichiers", "Vérifiez le format des fichiers déposés (voir « Format attendu des fichiers »).",
               sur_titre="Consolidation du planning de livraison")
    st.error(f"{type(e).__name__} : {e}")
    st.stop()

# ---------------------------------------------------------------- barre laterale apres le calcul : version affichee, semaine, filtres
cle_cache = hashlib.sha1(b"".join(fichiers) + ",".join(versions).encode()).hexdigest()
plantes = sorted({c[1] for c in sc.couples_fichier(ex)})
fournisseurs_fichier = sorted({c[0] for c in sc.couples_fichier(ex)})
for cle, valides in (("f_usine", plantes), ("f_fournisseur", fournisseurs_fichier)):      # un autre fichier peut avoir d'autres usines
    st.session_state[cle] = [x for x in st.session_state.get(cle, []) if x in valides]
with st.container(border=True):
    colonnes = st.columns(4 if len(versions) > 1 else 3)
    detail = versions[0]
    if len(versions) > 1:
        detail = colonnes[-4].selectbox("Version affichée", versions, format_func=lambda v: VERSIONS_NOMS[v], key="version_detail")
    lundis = sc.lundis(ex)
    semaine = colonnes[-3].selectbox("Semaine", lundis, index=sc.semaine_par_defaut(ex), format_func=lambda d: f"Semaine du {d:%d/%m}", key="semaine")
    usines = colonnes[-2].multiselect("Usines", plantes, key="f_usine", placeholder="Toutes")
    fournisseurs = colonnes[-1].multiselect("Fournisseurs", fournisseurs_fichier, key="f_fournisseur", placeholder="Tous")

nom_planning = planning_tv.name if planning_tv else "planning du client"
st.session_state["ctx"] = xp.construire_contexte(ex, detail, versions, nom_planning, semaine, usines, fournisseurs, cle_cache)

# ---------------------------------------------------------------- les quatre pages
xp.PAGES.update({
    "sorties": st.Page(page_sorties.page, title="Sorties", icon=":material/table_view:", url_path="sorties", default=True),
    "details": st.Page(page_details.page, title="Détails des sorties", icon=":material/calendar_month:", url_path="details"),
    "gains": st.Page(page_gains.page, title="Gains", icon=":material/trending_down:", url_path="gains"),
    "controles": st.Page(page_controles.page, title="Contrôles", icon=":material/fact_check:", url_path="controles"),
})
navigation = st.navigation(list(xp.PAGES.values()), position="top")
navigation.run()
st.markdown('<div class="pied">Projet ESIGELEC · Consolidation du planning de livraison</div>', unsafe_allow_html=True)
