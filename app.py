"""Dashboard Streamlit : consolidation des livraisons.

Lancer (depuis la racine du projet, environnement Python active) :

    streamlit run app.py          # ou ./lancer_app.sh

On depose les fichiers d'entree (planning, distances, grille tarifaire), on choisit la version du moteur, et on obtient :
  - une synthese claire pour le client : economies, camions, messages a retenir ;
  - les deux sorties demandees par le projet : le profil de livraison de chaque couple fournisseur x usine (sortie 1) et
    le materiel regroupe dans chaque camion (sortie 2), en CSV ;
  - l'analyse des gains : avant / apres, distributions, economies par usine et par couple, realise contre potentiel,
    calendrier d'une usine, courbes de prix.
"""
import io
import zipfile

import numpy as np
import pandas as pd
import streamlit as st

from dashboard import graphiques as gr
from dashboard import style
from src import config, preparation, sorties, tarifs
from src.pipeline import executer

JOURS_COURTS = ["lun", "mar", "mer", "jeu", "ven"]
VERSIONS_COURTES = {"strict": "Stricte · recommandée", "intermediaire": "Intermédiaire", "libre": "Libre", "toutes": "Comparer les trois"}
VERSIONS_NOMS = {"strict": "Stricte", "intermediaire": "Intermédiaire", "libre": "Libre"}
VERSIONS_EXPLICATIONS = {
    "strict": "Le rythme annoncé à chaque fournisseur est tenu **toutes les semaines** : un profil est un engagement.",
    "intermediaire": "Au moins **4 semaines** du profil sont respectées ; le reste, le moteur choisit au moins cher.",
    "libre": "Le profil est un maximum : le moteur choisit **les jours au moins chers**. Version de comparaison.",
    "toutes": "Calcule les trois versions pour **les comparer** : plus de souplesse coûte moins cher, mais le rythme est moins tenu.",
}
FORMATS = """
**Planning de livraisons** (CSV) : une ligne par besoin, avec les colonnes
`date, supplier_id, material, plant, unloading_point, schedule_quantity, weight, volume, transmission_date, version_date`.

**Distances** (CSV) : `supplier_id, distance` (en km).

**Grille tarifaire** (PDF du transporteur) : le tableau des coûts par tranche de distance et de poids.

Sans fichier déposé, l'application utilise ceux du client.
"""

CONFIG_PROFILS = {
    "supplier_id": st.column_config.TextColumn("Fournisseur"), "plant": st.column_config.TextColumn("Usine"),
    "distance": st.column_config.NumberColumn("Distance (km)", format="%.0f"),
    "envois_sem_actuels": st.column_config.NumberColumn("Livraisons/sem. avant", format="%.2f"),
    "profil": st.column_config.TextColumn("Profil retenu", width="large"), "periode": None, "jours": st.column_config.TextColumn("Jours"),
    "livraisons_reelles": st.column_config.NumberColumn("Livraisons", format="%d"), "camions": st.column_config.NumberColumn("Camions", format="%d"),
    "envois_exceptionnels": st.column_config.NumberColumn("Exceptionnels", format="%d"),
    "remplissage_moyen_%": st.column_config.ProgressColumn("Remplissage moyen", min_value=0, max_value=100, format="%.1f %%"),
    "cout_actuel": st.column_config.NumberColumn("Coût actuel", format="%.0f €"),
    "cout_optimise": st.column_config.NumberColumn("Coût optimisé", format="%.0f €"),
    "economie_eur": st.column_config.NumberColumn("Économie", format="%.0f €"),
    "economie_%": st.column_config.ProgressColumn("Économie %", min_value=0, max_value=100, format="%.0f %%"),
}
CONFIG_CAMIONS = {
    "camion_id": st.column_config.TextColumn("Camion"), "supplier_id": st.column_config.TextColumn("Fournisseur"),
    "plant": st.column_config.TextColumn("Usine"), "date_livraison": st.column_config.TextColumn("Livraison"),
    "material": st.column_config.TextColumn("Matériau"), "unloading_point": st.column_config.TextColumn("Point de déchargement"),
    "date_besoin": st.column_config.TextColumn("Besoin"), "avance_jours": st.column_config.NumberColumn("Avance (j)", format="%d"),
    "quantite": st.column_config.NumberColumn("Quantité", format="%.0f"), "poids": st.column_config.NumberColumn("Poids (kg)", format="%.1f"),
    "volume": st.column_config.NumberColumn("Volume (m³)", format="%.3f"), "envoi_exceptionnel": st.column_config.CheckboxColumn("Exceptionnel"),
}


def eur(x, dec=0):
    """Montant au format 82 111 €."""
    return f"{x:,.{dec}f}".replace(",", "\u00a0") + "\u00a0€"      # espaces insecables : un montant ne se coupe pas en fin de ligne


def nombre(x):
    """Entier a la francaise : 1 604."""
    return f"{int(x):,}".replace(",", "\u00a0")


def pct(x, dec=1):
    """Pourcentage au format 42,7 %."""
    return f"{x:.{dec}f}".replace(".", ",") + "\u00a0%"


@st.cache_resource(show_spinner=False)
def calculer(planning_octets, distances_octets, grille_octets, versions):
    """Lance tout le flux sur les fichiers donnes (en octets, pour que le cache reconnaisse un meme fichier)."""
    planning = pd.read_csv(io.BytesIO(planning_octets), encoding="utf-8-sig")
    distances = pd.read_csv(io.BytesIO(distances_octets))
    grille = preparation.charger_grille_pdf(io.BytesIO(grille_octets))
    return executer(planning, distances, grille, versions=versions, version_retenue=versions[0])


def octets(televerse, chemin_defaut):
    """Les octets du fichier televerse, ou ceux du fichier du client si rien n'a ete televerse."""
    return televerse.getvalue() if televerse is not None else chemin_defaut.read_bytes()


def csv_octets(tableau):
    return tableau.to_csv(index=False).encode("utf-8")


def archive(tables):
    """Tous les fichiers de sortie dans une archive zip."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for nom, tableau in tables.items():
            z.writestr(f"{nom}.csv", csv_octets(tableau))
    return tampon.getvalue()


def graphique(chart):
    st.altair_chart(chart, theme=None, width="stretch")


def long_avant_apres(etiquettes, avant, apres, colonne="etiquette"):
    """Un tableau au format long (une ligne par etiquette et par serie) pour les barres groupees Avant / Apres."""
    return pd.DataFrame([{colonne: e, "serie": s, "valeur": float(v)} for e, a, b in zip(etiquettes, avant, apres) for s, v in (("Avant", a), ("Après", b))])


# --------------------------------------------------------------------------------- page
st.set_page_config(page_title="Consolidation des livraisons", page_icon="🚚", layout="wide")
style.appliquer_style()

with st.sidebar:
    st.markdown('<div class="logo">Consolidation<span>.</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="etape-titre">1 · Déposer les fichiers</div>', unsafe_allow_html=True)
    planning_tv = st.file_uploader("Planning de livraisons (CSV)", type="csv")
    distances_tv = st.file_uploader("Distances fournisseur → usine (CSV)", type="csv")
    grille_tv = st.file_uploader("Grille tarifaire du transporteur (PDF)", type="pdf")
    with st.expander("Format attendu des fichiers"):
        st.markdown(FORMATS)
    utilises = [nom for nom, tv in (("planning", planning_tv), ("distances", distances_tv), ("grille", grille_tv)) if tv is not None]
    st.caption("Fichiers déposés : " + (", ".join(utilises) if utilises else "aucun") + ". Les autres sont ceux du client.")
    st.markdown('<div class="etape-titre">2 · Choisir la version</div>', unsafe_allow_html=True)
    choix = st.radio("Version", list(VERSIONS_COURTES), format_func=VERSIONS_COURTES.get, label_visibility="collapsed")
    st.caption(VERSIONS_EXPLICATIONS[choix])
    lancer = st.button("Lancer le calcul", type="primary", width="stretch")

if lancer:
    st.session_state["calcul_demande"] = True

# ---------------------------------------------------------------- accueil (avant le calcul)
if not st.session_state.get("calcul_demande"):
    style.hero("Moins de camions. Les mêmes livraisons. Aucun retard.",
               "Cet outil regroupe les livraisons des fournisseurs vers les usines pour réduire le coût de transport, "
               "en respectant les règles du client : jamais de retard, 7 jours d'avance au plus, 24 500 kg par camion.",
               pastilles=["Planning de livraisons", "Moteur d'optimisation exact", "Contrôles automatiques"], sur_titre="Consolidation du planning de livraison")
    style.section("Comment ça marche")
    style.etapes([("Déposez vos fichiers", "Le planning de livraisons, les distances et la grille tarifaire. Sans fichier, nous utilisons ceux du client."),
                  ("Choisissez la version", "Stricte (le rythme annoncé est tenu), intermédiaire, libre, ou comparez les trois."),
                  ("Obtenez les résultats", "Les économies, les deux fichiers de sortie du projet et les analyses, en quelques secondes.")])
    style.section("Ce que vous obtiendrez")
    style.cartes_simples([("Sortie 1 · Les profils", "Pour chaque couple fournisseur × usine, le profil de livraison à appliquer : quels jours livrer."),
                          ("Sortie 2 · Les camions", "Le matériel regroupé dans chaque camion, avec sa date de livraison et son avance."),
                          ("L'analyse des gains", "Coût avant/après, remplissage des camions, économies par usine et par couple, réalisé contre potentiel.")])
    st.markdown('<div class="pied">Cliquez sur « Lancer le calcul » dans la colonne de gauche pour commencer.</div>', unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------------------- calcul
versions = config.VERSIONS[::-1] if choix == "toutes" else (choix,)       # stricte d'abord
try:
    with st.spinner("Préparation du planning et calcul des livraisons..."):
        ex = calculer(octets(planning_tv, config.CHEMIN_PLANNING), octets(distances_tv, config.CHEMIN_DISTANCES),
                      octets(grille_tv, config.CHEMIN_GRILLE), versions)
except ValueError as e:                              # fichier a corriger, ou solution refusee par les controles
    style.hero("Le calcul s'est arrêté", "Un des fichiers doit être corrigé avant de continuer.", sur_titre="Consolidation du planning de livraison")
    st.error(f"{e}")
    st.stop()
except Exception as e:                               # fichier illisible, PDF inattendu...
    style.hero("Impossible de lire les fichiers", "Vérifiez le format des fichiers déposés (voir « Format attendu des fichiers »).",
               sur_titre="Consolidation du planning de livraison")
    st.error(f"{type(e).__name__} : {e}")
    st.stop()

zone_bandeau = st.container()                  # le bandeau s'ecrit apres le choix de la version affichee, mais reste en haut de page
zone_choix = st.container()
detail = versions[0]
if len(versions) > 1:
    with zone_choix:
        detail = st.selectbox("Version affichée dans les onglets ci-dessous", versions, format_func=lambda v: VERSIONS_NOMS[v], key="version_detail")
resultat, moteur = ex.resultats[detail], ex.moteur
profils = sorties.profils_couples(moteur, resultat)                                       # sortie 1
contenu = resultat.contenu                                                                # sortie 2
resume = sorties.resume_economies(resultat, ex.baselines, float(ex.inconnues["cout"].sum()))
res = resume.set_index("indicateur")["valeur"]
envois = tarifs.envois_actuels(ex.planning_propre, moteur.grille)
potentiel = tarifs.potentiel_couples(envois, moteur.grille)
nb_semaines = ex.planning_propre["semaine"].nunique()
cout_inconnues = float(ex.inconnues["cout"].sum())

avant, apres = float(res["Cout avant - baseline H20 (perimetre)"]), float(res["Cout apres (perimetre)"])
camions_avant, camions_apres = int(res["Camions avant"]), int(res["Camions apres"])
gain, gain_pct = avant - apres, (avant - apres) / avant * 100
sem = moteur.semaines_par_couple(resultat.choix, contenu)
rythme = sum(a for a, b in sem.values()) / max(sum(b for a, b in sem.values()), 1) * 100
normaux = contenu[~contenu["envoi_exceptionnel"]]
poids_camion = normaux.groupby("camion_id")["poids"].sum()
rempl_apres = poids_camion / config.CAP_POIDS * 100
rempl_avant = envois["remplissage_poids_%"]

nom_planning = planning_tv.name if planning_tv else "planning du client"
pastilles = [f"Version {VERSIONS_NOMS[detail].lower()}", nom_planning.capitalize(), f"{len(moteur.COUPLES)} couples fournisseur × usine", f"{nombre(len(ex.planning_propre))} lignes de besoin"]
with zone_bandeau:
    style.hero("Résultats de la consolidation", f"Avec la version {VERSIONS_NOMS[detail].lower()}, le coût de transport baisse de {pct(gain_pct)} sans aucun retard de livraison.",
               pastilles=pastilles, sur_titre="Consolidation du planning de livraison")
style.kpis([
    ("Économie", f"−{pct(gain_pct)}", f"<b>{eur(gain)}</b> économisés sur le périmètre optimisé", "vert"),
    ("Coût du transport", eur(apres), f"au lieu de {eur(avant)}", ""),
    ("Camions", nombre(camions_apres), f"au lieu de {nombre(camions_avant)} ({pct((camions_avant - camions_apres) / camions_avant * 100, 0)} en moins)", ""),
    ("Rythme annoncé tenu", pct(rythme, 0), "des semaines de chaque profil de livraison", "gris"),
])

onglets = st.tabs(["Synthèse", "Sorties du projet", "Analyse des gains", "Économies et potentiel", "Usines et calendrier", "Courbes de prix", "Contrôles et données"])

# ---------------------------------------------------------------- 0. synthese
with onglets[0]:
    style.section("En un coup d'œil", "La situation actuelle (chaque besoin livré le jour même) contre la solution du moteur.")
    c1, c2 = st.columns(2)
    with c1, style.carte_graphique("Coût du transport", "sur le périmètre optimisé"):
        graphique(gr.comparaison_horizontale(["Situation actuelle", "Solution"], [avant, apres], [gr.AVANT, gr.APRES], ",.0f"))
    with c2, style.carte_graphique("Nombre de camions", "pour livrer exactement la même matière"):
        graphique(gr.comparaison_horizontale(["Situation actuelle", "Solution"], [camions_avant, camions_apres], [gr.AVANT, gr.APRES], ",.0f"))
    dates_liv = pd.to_datetime(contenu["date_livraison"])
    sem_apres = contenu.assign(s=dates_liv - pd.to_timedelta(dates_liv.dt.weekday, unit="D")).groupby("s")["camion_id"].nunique()
    sem_avant = envois.groupby("semaine")["nb_camions"].sum()
    semaines = sorted(set(sem_apres.index) | set(sem_avant.index))
    etiq_sem = [s.strftime("%d/%m") for s in semaines]
    with style.carte_graphique("Camions par semaine", "chaque semaine est repérée par son lundi"):
        graphique(gr.barres_groupees(long_avant_apres(etiq_sem, [sem_avant.get(s, 0) for s in semaines], [sem_apres.get(s, 0) for s in semaines], "semaine"),
                                     "semaine", "valeur", ordre=etiq_sem, titre_y="camions", titre_x="semaine du"))

    opt = profils[profils["cout_optimise"].notna()].copy()
    tri = opt["economie_eur"].sort_values(ascending=False)
    n20 = int(np.ceil(len(tri) * 0.2))
    part20 = tri.head(n20).sum() / tri.sum() * 100
    style.section("Ce qu'il faut retenir")
    style.encadre("Les messages clés", [
        f"On économise <b>{eur(gain)}</b> (<b>{pct(gain_pct)}</b>) sur le périmètre optimisé, <b>sans jamais livrer en retard</b> et en respectant la capacité des camions.",
        f"Il faut <b>{nombre(camions_apres)} camions</b> au lieu de {nombre(camions_avant)} : <b>{nombre(camions_avant - camions_apres)} camions en moins</b> pour livrer la même matière.",
        f"L'économie est concentrée : <b>{n20} couples sur {len(tri)}</b> (20 %) apportent <b>{pct(part20, 0)}</b> du gain. Ce sont les couples qui livrent souvent et loin.",
        f"Le rythme annoncé à chaque fournisseur est tenu <b>{pct(rythme, 0)}</b> des semaines" + (" : c'est un engagement ferme." if rythme > 99.9 else "."),
    ], ton="retenir")
    st.write("")
    style.encadre("Points d'attention", [
        f"<b>{len(ex.inconnues)} lignes</b> n'ont pas de poids, de volume ou de distance : elles ne sont pas optimisées. Leur coût, estimé au pire cas "
        f"(<b>{eur(cout_inconnues)}</b>), est identique avant et après. Compléter ces données ouvrirait une économie supplémentaire.",
        f"Le remplissage médian d'un camion reste bas (<b>{pct(rempl_apres.median())}</b>) car un camion ne porte qu'un seul fournisseur : "
        "le gain vient du <b>nombre de camions en moins</b>, pas de camions pleins partout.",
    ], ton="attention")
    if ex.comparaison is not None:
        style.section("Le choix de la version", "Plus on laisse de souplesse au moteur, moins ça coûte, mais moins le rythme annoncé aux fournisseurs est tenu. Le choix revient au client.")
        cartes = []
        for _, r in ex.comparaison.iterrows():
            cartes.append((VERSIONS_NOMS[r["version"]], "Recommandée" if r["version"] == "strict" else "", eur(r["cout"]),
                           [f"Économie : <b>{pct(r['economie %'])}</b>", f"Camions : <b>{int(r['camions'])}</b>",
                            f"Rythme tenu : <b>{pct(r['part semaines respectees %'], 0)}</b> des semaines"]))
        style.cartes_versions(cartes)

# ---------------------------------------------------------------- 1. les sorties demandees par le projet
with onglets[1]:
    style.section("Sortie 1 · Le profil de livraison à appliquer à chaque couple",
                  "Pour chaque couple fournisseur × usine : le profil choisi (jours de livraison), le nombre de livraisons, le remplissage moyen, "
                  "le coût actuel, le coût optimisé et l'économie.")
    st.download_button("Télécharger la sortie 1 (profils_couples.csv)", csv_octets(profils), file_name="profils_couples.csv", mime="text/csv", type="primary")
    st.dataframe(profils, hide_index=True, width="stretch", column_config=CONFIG_PROFILS, height=380)
    style.section("Sortie 2 · Le matériel regroupé dans chaque camion",
                  "Une ligne par ligne de besoin : le camion qui la porte, sa date de livraison, sa date de besoin (donc son avance), la quantité, le poids et le volume.")
    st.download_button("Télécharger la sortie 2 (contenu_camions.csv)", csv_octets(contenu), file_name="contenu_camions.csv", mime="text/csv", type="primary")
    contenu_affiche = contenu.assign(date_livraison=pd.to_datetime(contenu["date_livraison"]).dt.strftime("%d/%m/%Y"),
                                     date_besoin=pd.to_datetime(contenu["date_besoin"]).dt.strftime("%d/%m/%Y"))       # lisible a l'ecran ; le CSV garde les dates d'origine
    st.dataframe(contenu_affiche, hide_index=True, width="stretch", column_config=CONFIG_CAMIONS, height=380)
    style.section("Résumé des économies")
    tableau_resume = res.rename("valeur").reset_index()
    tableau_resume.columns = ["Indicateur", "Valeur"]
    tableau_resume["Valeur"] = tableau_resume["Valeur"].astype(str)          # la colonne melange un texte (la version) et des nombres
    st.dataframe(tableau_resume, hide_index=True, width="stretch")
    fichiers = {"profils_couples": profils, "contenu_camions": contenu, "resume_economies": resume,
                "planning_propre": ex.planning_propre, "journal_pipeline": ex.journal, "lignes_inconnues": ex.inconnues}
    if ex.comparaison is not None:
        fichiers["comparaison_versions"] = ex.comparaison
    st.download_button("Tout télécharger (archive .zip)", archive(fichiers), file_name="resultats_consolidation.zip", mime="application/zip")

# ---------------------------------------------------------------- 2. analyse des gains : avant / apres
with onglets[2]:
    premiere_ligne = normaux.groupby("camion_id")[["supplier_id", "plant"]].first()          # le couple de chaque camion
    cout_camion_apres = pd.Series([tarifs.prix_camion(moteur.grille, moteur.COUPLES[tuple(premiere_ligne.loc[c])]["ligne"], poids_camion[c])
                                   for c in poids_camion.index], index=poids_camion.index)
    cout_camion_avant = envois["cout"] / envois["nb_camions"]
    style.section("Avant et après", "Les indicateurs de la situation actuelle comparés à ceux de la solution.")
    st.dataframe(pd.DataFrame({
        "Indicateur": ["Coût du périmètre", "Camions", "Coût moyen par camion", "Remplissage moyen (poids)", "Remplissage médian (poids)"],
        "Avant": [eur(avant), nombre(camions_avant), eur(avant / camions_avant, 1).replace(".", ","), pct(rempl_avant.mean()), pct(rempl_avant.median(), 2)],
        "Après": [eur(apres), nombre(camions_apres), eur(apres / camions_apres, 1).replace(".", ","), pct(rempl_apres.mean()), pct(rempl_apres.median(), 2)],
    }), hide_index=True, width="stretch")
    if ex.comparaison is not None:
        style.section("Les trois versions")
        noms = ["Situation actuelle"] + [VERSIONS_NOMS[v] for v in ex.comparaison["version"]]
        with style.carte_graphique("Coût du transport selon la version", "la situation actuelle en gris, les versions du moteur en bleu"):
            graphique(gr.comparaison_horizontale(noms, [avant] + list(ex.comparaison["cout"]), [gr.AVANT] + [gr.APRES] * len(ex.comparaison), ",.0f", hauteur=200))
        st.dataframe(ex.comparaison, hide_index=True, width="stretch")

    style.section("Les nouvelles distributions", "Chaque graphique compare la situation actuelle (gris) à la solution (bleu).")
    c1, c2 = st.columns(2)
    bornes = [0, 1, 2, 5, 10, 20, 30, 50, 75, 100.01]
    libelles = ["< 1 %", "1-2", "2-5", "5-10", "10-20", "20-30", "30-50", "50-75", "75-100"]
    a = pd.cut(rempl_avant, bornes, labels=libelles, right=False).value_counts().reindex(libelles)
    b = pd.cut(rempl_apres, bornes, labels=libelles, right=False).value_counts().reindex(libelles)
    with c1, style.carte_graphique("Taux de remplissage des camions", "poids chargé / 24 500 kg, en % de la capacité"):
        graphique(gr.barres_groupees(long_avant_apres(libelles, a.values, b.values, "tranche"), "tranche", "valeur", ordre=libelles,
                                     titre_y="camions", titre_x="remplissage du camion"))
    with c2, style.carte_graphique("Coût d'un camion", "un camion plus rempli coûte un peu plus cher, mais on en envoie bien moins"):
        graphique(gr.histogramme_cout(pd.concat([pd.DataFrame({"cout": cout_camion_avant.values, "serie": "Avant"}),
                                                 pd.DataFrame({"cout": cout_camion_apres.values, "serie": "Après"})])))
    c3, c4 = st.columns(2)
    jour_avant = envois.assign(j=envois["date"].dt.weekday).groupby("j")["nb_camions"].sum().reindex(range(5), fill_value=0)
    jour_apres = contenu.assign(j=dates_liv.dt.weekday).groupby("j")["camion_id"].nunique().reindex(range(5), fill_value=0)
    with c3, style.carte_graphique("Camions par jour de la semaine", "la charge est répartie sur les cinq jours"):
        graphique(gr.barres_groupees(long_avant_apres(JOURS_COURTS, jour_avant.values, jour_apres.values, "jour"), "jour", "valeur", ordre=JOURS_COURTS, titre_y="camions"))
    with c4, style.carte_graphique("Camions par semaine"):
        graphique(gr.barres_groupees(long_avant_apres(etiq_sem, [sem_avant.get(s, 0) for s in semaines], [sem_apres.get(s, 0) for s in semaines], "semaine"),
                                     "semaine", "valeur", ordre=etiq_sem, titre_y="camions", titre_x="semaine du"))
    st.caption(f"Remplissage médian d'un camion : {pct(rempl_avant.median(), 2)} avant, {pct(rempl_apres.median(), 2)} après.")

# ---------------------------------------------------------------- 3. economies, realise contre potentiel
with onglets[3]:
    style.section("Économies réalisées contre potentiel",
                  "Le <b>potentiel</b> est l'estimation de départ, volontairement simple : un seul envoi par couple et par semaine, le lundi. "
                  "Le <b>réalisé</b> est l'économie de la solution du moteur, avec toutes les règles du client.")
    r = opt.merge(potentiel[["supplier_id", "plant", "gain_eur"]], on=["supplier_id", "plant"], how="left")
    r["couple"] = r["supplier_id"] + " × " + r["plant"]
    style.kpis([("Potentiel estimé au départ", eur(float(r["gain_eur"].sum())), "un envoi par couple et par semaine", "gris"),
                ("Réalisé (solution du moteur)", eur(float(r["economie_eur"].sum())), "avec les règles du client", "vert"),
                ("Couples au-dessus du potentiel", f"{int((r['economie_eur'] > r['gain_eur'] + 0.01).sum())} / {len(r)}", "l'estimation de départ était volontairement simple", ""),
                ("Couples sans économie", f"{int((tri <= 0.01).sum())}", "rien à regrouper : ils livrent déjà peu", "gris")])
    c1, c2 = st.columns(2)
    with c1, style.carte_graphique("Chaque point est un couple", "au-dessus de la ligne pointillée : le réalisé dépasse le potentiel"):
        graphique(gr.realise_contre_potentiel(r.rename(columns={"gain_eur": "potentiel", "economie_eur": "realise"})[["couple", "potentiel", "realise"]]))
    cum = tri.cumsum() / tri.sum() * 100
    with c2, style.carte_graphique("Où se concentre l'économie", "% des économies cumulées, des couples les plus rentables aux moins rentables"):
        graphique(gr.concentration(pd.DataFrame({"rang": np.arange(1, len(cum) + 1), "pourcentage": cum.values})))
    top = opt.sort_values("economie_eur", ascending=False).head(10)
    with style.carte_graphique("Les 10 couples les plus rentables"):
        graphique(gr.top_couples(pd.DataFrame({"couple": top["supplier_id"] + " × " + top["plant"], "economie": top["economie_eur"]})))

# ---------------------------------------------------------------- 4. usines et calendrier
with onglets[4]:
    par_usine = opt.groupby("plant")[["cout_actuel", "cout_optimise"]].sum().rename(columns={"cout_actuel": "avant", "cout_optimise": "après"})
    par_usine["économie"] = par_usine["avant"] - par_usine["après"]
    par_usine["économie %"] = par_usine["économie"] / par_usine["avant"] * 100
    style.section("Économie par usine")
    c1, c2 = st.columns([1, 1])
    with c1, style.carte_graphique("Coût du transport par usine"):
        graphique(gr.barres_groupees(long_avant_apres(list(par_usine.index), par_usine["avant"].values, par_usine["après"].values, "usine"),
                                     "usine", "valeur", ordre=list(par_usine.index), titre_y="coût (€)"))
    with c2:
        tab_usine = par_usine.reset_index().rename(columns={"plant": "Usine", "avant": "Avant", "après": "Après", "économie": "Économie"})
        for col in ("Avant", "Après", "Économie"):
            tab_usine[col] = tab_usine[col].map(eur)                                      # montants a la francaise : 38 667 €
        st.dataframe(tab_usine, hide_index=True, width="stretch",
                     column_config={"économie %": st.column_config.ProgressColumn("Économie %", min_value=0, max_value=100, format="%.0f %%")})
    style.section("Calendrier des livraisons d'une usine", "Chaque case est un jour : plus elle est foncée, plus il y a de camions ce jour-là.")
    usine = st.selectbox("Usine", sorted(contenu["plant"].unique()))
    c = contenu[contenu["plant"] == usine].copy()
    c["date"] = pd.to_datetime(c["date_livraison"])
    c["lundi"] = c["date"] - pd.to_timedelta(c["date"].dt.weekday, unit="D")
    lundis = sorted(c["lundi"].unique())
    cal = c.groupby(["lundi", c["date"].dt.weekday])["camion_id"].nunique().unstack(fill_value=0).reindex(index=lundis, columns=range(5), fill_value=0)
    etiq_lundis = [pd.Timestamp(d).strftime("%d/%m") for d in lundis]
    df_cal = pd.DataFrame([{"semaine": etiq_lundis[i], "jour": JOURS_COURTS[j], "n": int(cal.values[i, j])} for i in range(len(lundis)) for j in range(5)])
    with style.carte_graphique(f"{usine} · camions par jour", f"{int(cal.values.sum())} camions au total, lignes = semaines (repérées par leur lundi)"):
        graphique(gr.calendrier(df_cal, JOURS_COURTS, etiq_lundis, hauteur=max(220, 46 * len(lundis))))
    style.section("Fréquence de livraison par couple", "Combien de fois par semaine chaque couple est livré, en moyenne, avant et après.")
    apres_freq = opt["livraisons_reelles"] / nb_semaines
    bornes_f = np.arange(0, max(opt["envois_sem_actuels"].max(), apres_freq.max()) + 1.0, 1.0)
    etiq_f = [f"{int(x)}-{int(x) + 1}" for x in bornes_f[:-1]]
    fa = pd.cut(opt["envois_sem_actuels"], bornes_f, labels=etiq_f, right=False).value_counts().reindex(etiq_f)
    fb = pd.cut(apres_freq, bornes_f, labels=etiq_f, right=False).value_counts().reindex(etiq_f)
    with style.carte_graphique("Livraisons par semaine et par couple", "nombre de couples dans chaque tranche"):
        graphique(gr.barres_groupees(long_avant_apres(etiq_f, fa.values, fb.values, "tranche"), "tranche", "valeur", ordre=etiq_f, titre_y="couples", titre_x="livraisons par semaine"))

# ---------------------------------------------------------------- 5. courbes de prix
with onglets[5]:
    grille = moteur.grille
    style.section("Le prix d'un camion", "Le prix se lit dans la grille du transporteur : une ligne par tranche de distance, une colonne par tranche de poids. "
                  "Le prix monte avec le poids, mais bien moins vite : le <b>prix au kilo s'effondre</b>. C'est ce qui rend le regroupement rentable.")
    defaut = [lg for lg in ("50", "150", "300") if lg in grille.index] or list(grille.index[:3])
    lignes = st.multiselect("Distances à comparer (km)", list(grille.index), default=defaut)
    if lignes:
        poids = np.linspace(10, config.CAP_POIDS, 400)
        df_prix = pd.DataFrame([{"ligne": f"{lg} km", "poids": float(p), "prix": tarifs.prix_camion(grille, lg, p), "prix_kg": tarifs.prix_camion(grille, lg, p) / p}
                                for lg in lignes for p in poids])
        c1, c2 = st.columns(2)
        with c1, style.carte_graphique("Prix d'un camion selon son poids", "des paliers : le prix change à chaque tranche de poids"):
            graphique(gr.courbes_prix(df_prix, "prix", "prix d'un camion (€)", escalier=True))
        with c2, style.carte_graphique("Prix au kilo selon le poids", "échelle logarithmique : plus le camion est chargé, moins le kilo coûte"):
            graphique(gr.courbes_prix(df_prix, "prix_kg", "prix au kilo (€/kg)", echelle_log=True))
    with st.expander("La grille complète (prix finaux, marge et diesel inclus)"):
        st.dataframe(grille.round(2), width="stretch")

# ---------------------------------------------------------------- 6. controles et donnees
with onglets[6]:
    style.section("Contrôles", f"Le moteur refuse de publier une solution qui viole une règle. Contrôles passés pour la version <b>{VERSIONS_NOMS[detail].lower()}</b> : "
                  f"{sum(ok for _, ok in resultat.controles)} sur {len(resultat.controles)} pour le moteur, "
                  f"{sum(ok for _, ok, _ in ex.controles_independants[detail])} sur {len(ex.controles_independants[detail])} pour les contrôles indépendants.")
    resultat_col = {"Résultat": st.column_config.TextColumn("Résultat", width="small")}
    st.markdown("**Contrôles du moteur**")
    st.dataframe(pd.DataFrame([{"Contrôle": n, "Résultat": "✅ OK" if ok else "❌ ÉCHEC"} for n, ok in resultat.controles]),
                 hide_index=True, width="stretch", height="content", column_config=resultat_col)
    st.markdown("**Contrôles indépendants** : recalculés à partir du planning et de la grille, sans utiliser ceux du moteur")
    st.dataframe(pd.DataFrame([{"Contrôle": n, "Résultat": "✅ OK" if ok else "❌ ÉCHEC"} for n, ok, d in ex.controles_independants[detail]]),
                 hide_index=True, width="stretch", height="content", column_config=resultat_col)
    style.section("Qualité des données", "Ce que la préparation a retiré ou marqué dans le planning déposé.")
    journal = ex.journal.rename(columns={"etape": "Étape", "lignes_avant": "Lignes avant", "lignes_apres": "Lignes après",
                                         "retirees_ou_marquees": "Retirées ou marquées", "regle": "Règle"})
    st.dataframe(journal, hide_index=True, width="stretch", height="content")
    style.section("Lignes à information manquante (non optimisées)", "Pas de poids, de volume ou de distance : chaque ligne est estimée au pire cas, un camion plein.")
    inconnues = ex.inconnues.assign(date=pd.to_datetime(ex.inconnues["date"]).dt.strftime("%d/%m/%Y")).rename(columns={
        "supplier_id": "Fournisseur", "plant": "Usine", "date": "Date", "raison": "Raison", "ligne_grille": "Ligne de grille (km)",
        "nb_camions": "Camions", "cout": "Coût estimé (€)"})
    st.dataframe(inconnues, hide_index=True, width="stretch", height=360,
                 column_config={"Coût estimé (€)": st.column_config.NumberColumn(format="%.0f €"),
                                "Ligne de grille (km)": st.column_config.NumberColumn(format="%.0f")})

st.markdown('<div class="pied">Projet ESIGELEC · Consolidation du planning de livraison</div>', unsafe_allow_html=True)
