"""Page « Sorties » : les trois sorties demandees par le client (slides « Livrables attendus »), telechargeables, chaque couple cliquable."""
import io

import pandas as pd
import streamlit as st

from dashboard import explorateur as xp
from dashboard import sorties_client as sc
from dashboard import style

CONFIG_S1 = {
    "fournisseur": st.column_config.TextColumn("Fournisseur"), "usine": st.column_config.TextColumn("Usine"),
    "distance_km": st.column_config.NumberColumn("Distance (km)", format="%.0f"), "statut": st.column_config.TextColumn("Statut", width="medium"),
    "livraisons_sem_actuelles": st.column_config.NumberColumn("Livraisons / sem. actuelles (semaine)", format="%d"),
    "livraisons_sem_moyenne": st.column_config.NumberColumn("Livraisons / sem. actuelles (moyenne)", format="%.2f"),
    "frequence_cible": st.column_config.TextColumn("Fréquence cible"), "jours_autorises": st.column_config.TextColumn("Jours autorisés", width="medium"),
    "profil": None, "jours_livres_semaine": st.column_config.TextColumn("Jours livrés (semaine)", width="medium"),
    "camions_semaine": st.column_config.NumberColumn("Camions (semaine)", format="%d"),
    "remplissage_poids_%": st.column_config.ProgressColumn("Remplissage poids", min_value=0, max_value=100, format="%.1f %%"),
    "lignes_non_optimisees": st.column_config.NumberColumn("Lignes non optimisées", format="%d"),
    "dates_non_optimisees": st.column_config.TextColumn("Dates non optimisées", width="medium"),
}
CONFIG_S2 = {
    "camion_id": st.column_config.TextColumn("Camion"), "type": st.column_config.TextColumn("Type", width="medium"),
    "fournisseur": st.column_config.TextColumn("Fournisseur"), "usine": st.column_config.TextColumn("Usine"),
    "date_livraison": st.column_config.TextColumn("Date"), "jour": st.column_config.TextColumn("Jour"),
    "lignes": st.column_config.NumberColumn("Lignes", format="%d"), "materials": st.column_config.NumberColumn("Materials", format="%d"),
    "quantite": st.column_config.NumberColumn("Quantité", format="%.0f"), "poids": st.column_config.NumberColumn("Poids (kg)", format="%.0f"),
    "volume": st.column_config.NumberColumn("Volume (m³)", format="%.1f"),
    "remplissage_%": st.column_config.ProgressColumn("Remplissage", min_value=0, max_value=100, format="%.0f %%"),
    "livraisons_remplacees": st.column_config.NumberColumn("Livraisons remplacées", format="%d"),
    "jours_besoin": st.column_config.TextColumn("Jours de besoin regroupés", width="large"), "prix": st.column_config.NumberColumn("Prix", format="%.0f €"),
}
CONFIG_MAT = {
    "camion_id": st.column_config.TextColumn("Camion"), "material": st.column_config.TextColumn("Material"), "quai": st.column_config.TextColumn("Quai"),
    "besoins_regroupes": st.column_config.TextColumn("Besoins regroupés (jours)", width="large"),
    "quantite": st.column_config.NumberColumn("Quantité", format="%.0f"), "poids": st.column_config.NumberColumn("Poids (kg)", format="%.0f"),
    "volume": st.column_config.NumberColumn("Volume (m³)", format="%.2f"),
}
CONFIG_S3 = {
    "fournisseur": st.column_config.TextColumn("Fournisseur"), "usine": st.column_config.TextColumn("Usine"),
    "cout_actuel_semaine": st.column_config.NumberColumn("Coût actuel (semaine)", format="%.0f €"),
    "cout_optimise_semaine": st.column_config.NumberColumn("Optimisé (semaine)", format="%.0f €"),
    "economie_semaine": st.column_config.NumberColumn("Économie (semaine)", format="%.0f €"),
    "economie_semaine_%": st.column_config.ProgressColumn("Économie % (semaine)", min_value=0, max_value=100, format="%.0f %%"),
    "cout_actuel_horizon": st.column_config.NumberColumn("Coût actuel (horizon)", format="%.0f €"),
    "cout_optimise_horizon": st.column_config.NumberColumn("Optimisé (horizon)", format="%.0f €"),
    "economie_horizon": st.column_config.NumberColumn("Économie (horizon)", format="%.0f €"),
    "economie_horizon_%": st.column_config.ProgressColumn("Économie % (horizon)", min_value=0, max_value=100, format="%.0f %%"),
    "cout_non_optimise": st.column_config.NumberColumn("Lignes non optimisées (inchangé)", format="%.0f €"),
}


def csv(df):
    return df.to_csv(index=False).encode("utf-8")


@st.cache_data(show_spinner=False, max_entries=8)
def excel(_ex, cle_cache, version, lundi):
    """Les trois sorties dans un classeur Excel : une feuille par sortie (la sortie 2 a deux feuilles)."""
    s2, mat = sc.sortie2(_ex, version)
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as w:
        sc.sortie1(_ex, version, lundi).to_excel(w, sheet_name="Sortie 1 - Profils", index=False)
        s2.to_excel(w, sheet_name="Sortie 2 - Camions", index=False)
        mat.to_excel(w, sheet_name="Sortie 2 - Materials", index=False)
        sc.sortie3(_ex, version, lundi).to_excel(w, sheet_name="Sortie 3 - Savings", index=False)
    return tampon.getvalue()


def page():
    ctx = xp.contexte()
    xp.kpis_haut(ctx)
    ex, v = ctx.ex, ctx.version
    s1 = ctx.garde(sc.sortie1(ex, v, ctx.lundi), "fournisseur", "usine")
    s2, mat = sc.sortie2(ex, v)
    s2 = ctx.garde(s2, "fournisseur", "usine")
    s3 = ctx.garde(sc.sortie3(ex, v, ctx.lundi), "fournisseur", "usine")
    haut, bouton = st.columns([3, 1.3])
    with haut:
        style.section("Les trois sorties du projet", f"Semaine du {ctx.lundi:%d/%m}")
    with bouton:
        st.write("")
        st.download_button("Tout télécharger (.xlsx)", excel(ex, ctx.cle_cache, v, ctx.lundi), file_name="sorties_consolidation.xlsx", type="primary", width="stretch",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    t1, t2, t3 = st.tabs(["Sortie 1 · Profil par couple", "Sortie 2 · Camions", "Sortie 3 · Savings par couple"])
    with t1:
        ligne = xp.tableau_cliquable(s1, "s1", CONFIG_S1)
        c1, c2 = st.columns([1, 3])
        with c1:
            st.download_button("Télécharger en CSV", csv(s1), file_name="sortie1_profils.csv", mime="text/csv", key="dl1")
        with c2:
            xp.bouton_ouvrir((ligne["fournisseur"], ligne["usine"]) if ligne is not None else None, "ouvrir1")
    with t2:
        ligne = xp.tableau_cliquable(s2, "s2", CONFIG_S2)
        c1, c2, c3 = st.columns([1, 1, 3])
        with c1:
            st.download_button("Camions en CSV", csv(s2), file_name="sortie2_camions.csv", mime="text/csv", key="dl2")
        with c2:
            st.download_button("Materials en CSV", csv(mat[mat["camion_id"].isin(s2["camion_id"])]), file_name="sortie2_materials.csv", mime="text/csv", key="dl2b")
        with c3:
            xp.bouton_ouvrir((ligne["fournisseur"], ligne["usine"]) if ligne is not None else None, "ouvrir2")
        if ligne is not None:
            style.section(f"Materials du camion {ligne['camion_id']}")
            st.dataframe(mat[mat["camion_id"] == ligne["camion_id"]].drop(columns="camion_id"), hide_index=True, width="stretch", column_config=CONFIG_MAT)
    with t3:
        a, o = s3["cout_actuel_semaine"].sum(), s3["cout_optimise_semaine"].sum()
        ligne = xp.tableau_cliquable(s3, "s3", CONFIG_S3)
        c1, c2 = st.columns([1, 3])
        with c1:
            st.download_button("Télécharger en CSV", csv(s3), file_name="sortie3_savings.csv", mime="text/csv", key="dl3")
        with c2:
            xp.bouton_ouvrir((ligne["fournisseur"], ligne["usine"]) if ligne is not None else None, "ouvrir3")
