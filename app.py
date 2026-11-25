"""Dashboard Streamlit : consolidation des livraisons.

Lancer (depuis la racine du projet, environnement Python active) :

    streamlit run app.py          # ou ./lancer_app.sh

On depose les fichiers d'entree (planning, distances, grille tarifaire), on choisit la version du moteur, et on obtient :
  - les trois sorties du projet (profil par couple, camions, savings par couple), en CSV et en Excel ;
  - le detail d'un couple : calendrier avant / apres, impact du lissage, contenu de chaque camion ;
  - les gains (avant / apres, par usine, lissage, couples) et les controles.
Trois pages : Sorties, Details des sorties, Gains (st.navigation).
"""
import hashlib
import os
import io

import pandas as pd
import streamlit as st

from dashboard import explorateur as xp
from dashboard import lecture
from dashboard import page_details, page_gains, page_sorties
from dashboard import sorties_client as sc
from dashboard import style
from src import config, preparation
from src.pipeline import executer

TITRE = "Planification améliorée des livraisons"
SOUS_TITRE = "Le bon rythme de livraison pour chaque fournisseur, au meilleur coût."
VERSIONS_COURTES = {"strict": "Stricte · recommandée", "intermediaire": "Intermédiaire", "libre": "Libre", "toutes": "Comparer les trois"}
VERSIONS_NOMS = xp.VERSIONS_NOMS
VERSIONS_EXPLICATIONS = {
    "strict": "Le rythme annoncé à chaque fournisseur est tenu **toutes les semaines** : un profil est un engagement.",
    "intermediaire": "Au moins **4 semaines** du profil sont respectées ; le reste, le moteur choisit au moins cher.",
    "libre": "Le profil est un maximum : le moteur choisit **les jours au moins chers**. Version de comparaison.",
    "toutes": "Calcule les trois versions pour **les comparer** : plus de souplesse coûte moins cher, mais le rythme est moins tenu.",
}
@st.cache_resource(show_spinner=False)
def calculer(planning_octets, distances_octets, grille_octets, versions):
    """Lance tout le flux sur les fichiers donnes (en octets, pour que le cache reconnaisse un meme fichier)."""
    planning = lecture.lire_tableau(planning_octets, config.COLONNES_PLANNING, "le planning")
    distances = lecture.lire_tableau(distances_octets, config.COLONNES_DISTANCES, "le fichier des distances")
    grille = preparation.charger_grille_pdf(io.BytesIO(grille_octets))
    ex = executer(planning, distances, grille, versions=versions, version_retenue=versions[0])
    ex.planning_brut, ex.distances_brutes = planning, distances          # pour lister tous les couples du fichier (sortie 1)
    return ex


# Les trois fichiers sont obligatoires. Seuls les tests automatiques (sans navigateur, ils ne peuvent pas deposer de fichier)
# utilisent ceux du client, en posant cette variable d'environnement.
FICHIERS_CLIENT_POUR_TESTS = os.environ.get("CONSOLIDATION_FICHIERS_CLIENT") == "1"


def octets(televerse, chemin_defaut):
    """Les octets du fichier televerse, ou ceux du fichier du client si rien n'a ete televerse."""
    return televerse.getvalue() if televerse is not None else chemin_defaut.read_bytes()


# --------------------------------------------------------------------------------- page
st.set_page_config(page_title="Planification des livraisons", page_icon="🚚", layout="wide")
style.appliquer_style()
style.appliquer_style_calendrier()
style._css_haut()
style.appliquer_style_sobre()

class Depot:
    """Un fichier depose, garde dans la session (nom et contenu)."""
    def __init__(self, name, contenu):
        self.name, self._contenu = name, contenu

    def getvalue(self):
        return self._contenu


def _retire(cle):
    """Appele quand l'utilisateur change le depot lui-meme : s'il l'a vide (la croix), on oublie le fichier."""
    if st.session_state.get(f"tv_{cle}") is None:
        st.session_state.pop(f"depot_{cle}", None)


def deposer(colonne, libelle, cle, types):
    """Un depot de fichier dont le contenu est garde dans la session des qu'il est depose.

    Sur la page « Details des sorties », le bouton de depot est cache : Streamlit le recree alors vide. Le fichier ne doit pas
    etre perdu pour autant : on lit celui de la session, qui n'est efface que si l'utilisateur le retire (la croix)."""
    tv = colonne.file_uploader(libelle, type=types, key=f"tv_{cle}", on_change=_retire, args=(cle,))
    if tv is not None:
        st.session_state[f"depot_{cle}"] = Depot(tv.name, tv.getvalue())
    return st.session_state.get(f"depot_{cle}")


def panneau_fichiers():
    """Les trois depots, la version et le bouton de calcul (cles fixes : rien ne se perd entre l'accueil et les pages)."""
    c1, c2, c3 = st.columns(3)
    planning = deposer(c1, "Planning (Excel ou CSV)", "planning", ["xlsx", "csv"])
    distances = deposer(c2, "Distances (Excel ou CSV)", "distances", ["xlsx", "csv"])
    grille = deposer(c3, "Grille tarifaire (PDF)", "grille", ["pdf"])
    c4, c5 = st.columns([4, 1], vertical_alignment="bottom")
    version = c4.radio("Version", list(VERSIONS_COURTES), format_func=VERSIONS_COURTES.get, horizontal=True, key="choix_version",
                       help="  \n".join(f"**{VERSIONS_COURTES[k]}** : {v}" for k, v in VERSIONS_EXPLICATIONS.items()))
    manquants = [] if FICHIERS_CLIENT_POUR_TESTS else [nom for nom, tv in (("planning", planning), ("distances", distances), ("grille", grille)) if tv is None]
    lancer = c5.button("Lancer le calcul", type="primary", width="stretch", disabled=bool(manquants))
    if manquants:
        st.caption("À déposer : " + ", ".join(manquants) + ".")
    elif any(d is not None for d in (planning, distances, grille)):
        st.caption("Fichiers utilisés : " + ", ".join(d.name for d in (planning, distances, grille) if d is not None) + ".")
    return planning, distances, grille, version, lancer, manquants


calcul = st.session_state.get("calcul_demande", False)
if calcul:                                           # les trois pages ; la page demandee est connue avant de dessiner le haut
    xp.PAGES.update({
        "sorties": st.Page(page_sorties.page, title="Sorties", icon=":material/table_view:", url_path="sorties", default=True),
        "details": st.Page(page_details.page, title="Détails des sorties", icon=":material/calendar_month:", url_path="details"),
        "gains": st.Page(page_gains.page, title="Gains", icon=":material/trending_up:", url_path="gains"),
    })
    navigation = st.navigation(list(xp.PAGES.values()), position="top")
    page_epuree = navigation.url_path == "details"   # « Détails des sorties » : seulement le bouton Accueil en haut
    sans_filtres = navigation.url_path in ("details", "gains")   # pas de semaine ni de filtres sur ces pages
if calcul:                                           # apres le calcul : une ligne compacte, les fichiers dans un menu
    c_logo, c_fichiers, c_retour = st.columns([4, 1.3, 1], vertical_alignment="center")
    # sur la page epuree, les depots restent en place (pour garder les fichiers deposes) mais caches
    with (st.container(key="cache_fichiers") if page_epuree else c_fichiers.popover("Fichiers et version", width="stretch")):
        planning_tv, distances_tv, grille_tv, choix, lancer, manquants = panneau_fichiers()
    if c_retour.button("← Accueil", width="stretch", key="retour_accueil"):
        st.session_state["calcul_demande"] = False
        st.rerun()
else:                                                # accueil : le bandeau, puis les fichiers juste en dessous
    style.hero(TITRE, SOUS_TITRE)
    with st.container(border=True):
        planning_tv, distances_tv, grille_tv, choix, lancer, manquants = panneau_fichiers()

if manquants and st.session_state.get("calcul_demande"):      # un fichier a ete retire : retour a l'accueil
    st.session_state["calcul_demande"] = False
    st.rerun()
if lancer:
    st.session_state["calcul_demande"] = True
    st.rerun()                      # pour afficher le bouton « Accueil » et replier le panneau des fichiers

# ---------------------------------------------------------------- accueil (avant le calcul)
if not st.session_state.get("calcul_demande"):
    style.etapes([("Déposez", "le planning, les distances et la grille"), ("Choisissez", "la version du moteur"), ("Lancez", "le calcul")])
    st.stop()

# ---------------------------------------------------------------- calcul
versions = config.VERSIONS[::-1] if choix == "toutes" else (choix,)       # stricte d'abord
try:
    with st.spinner("Préparation du planning et calcul des livraisons..."):
        fichiers = (octets(planning_tv, config.CHEMIN_PLANNING), octets(distances_tv, config.CHEMIN_DISTANCES), octets(grille_tv, config.CHEMIN_GRILLE))
        ex = calculer(*fichiers, versions)
except ValueError as e:                              # fichier a corriger, ou solution refusee par les controles
    style.hero("Le calcul s'est arrêté", "Un des fichiers doit être corrigé avant de continuer.")
    st.error(f"{e}")
    st.stop()
except Exception as e:                               # fichier illisible, PDF inattendu...
    style.hero("Impossible de lire les fichiers", "Vérifiez le format des fichiers déposés (voir « Format attendu des fichiers »).")
    st.error(f"{type(e).__name__} : {e}")
    st.stop()

# ---------------------------------------------------------------- barre laterale apres le calcul : version affichee, semaine, filtres
cle_cache = hashlib.sha1(b"".join(fichiers) + ",".join(versions).encode()).hexdigest()
plantes = sorted({c[1] for c in sc.couples_fichier(ex)})
fournisseurs_fichier = sorted({c[0] for c in sc.couples_fichier(ex)})
for cle, valides in (("f_usine", plantes), ("f_fournisseur", fournisseurs_fichier)):      # un autre fichier peut avoir d'autres usines
    st.session_state[cle] = [x for x in st.session_state.get(cle, []) if x in valides]
with (st.container(key="cache_filtres") if sans_filtres else st.container(border=True)):
    colonnes = st.columns(4 if len(versions) > 1 else 3)
    detail = versions[0]
    if len(versions) > 1:
        detail = colonnes[-4].selectbox("Version affichée", versions, format_func=lambda v: VERSIONS_NOMS[v], key="version_detail")
    lundis = [None] + sc.lundis(ex)                                        # None : toutes les semaines
    semaine = colonnes[-3].selectbox("Semaine", lundis, index=0, key="semaine",          # par defaut : toutes les semaines
                                     format_func=lambda d: "Toutes les semaines" if d is None else f"Semaine du {d:%d/%m}")
    usines = colonnes[-2].multiselect("Usines", plantes, key="f_usine", placeholder="Toutes")
    fournisseurs = colonnes[-1].multiselect("Fournisseurs", fournisseurs_fichier, key="f_fournisseur", placeholder="Tous")

nom_planning = planning_tv.name if planning_tv else "planning du client"
if sans_filtres:                                      # pas de filtre visible : tous les couples, tout l'horizon
    semaine, usines, fournisseurs = None, [], []
st.session_state["ctx"] = xp.construire_contexte(ex, detail, versions, nom_planning, semaine, usines, fournisseurs, cle_cache)

# ---------------------------------------------------------------- la page demandee
navigation.run()
st.markdown('<div class="pied">Projet ESIGELEC</div>', unsafe_allow_html=True)
