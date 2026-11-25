"""Page « Contrôles » : les verifications calculees sur le resultat du fichier depose."""
import pandas as pd
import streamlit as st

from dashboard import explorateur as xp
from dashboard import sorties_client as sc
from dashboard import style


def page():
    ctx = xp.contexte()
    xp.kpis_haut(ctx)
    ex, v = ctx.ex, ctx.version
    style.section("Contrôles du résultat", "")
    for c in ctx.controles:
        icone = "✅" if c["ok"] else "❌"
        ligne = f"{icone} **{c['nom']}**" + ("" if c["ok"] else f" — {c['nb']} cas en défaut")
        if c["ok"]:
            st.markdown(ligne)
        else:
            with st.expander(ligne, expanded=True):
                st.dataframe(c["cas"], hide_index=True, width="stretch", height=min(300, 40 + 35 * len(c["cas"])))
    with st.expander("Contrôles du moteur"):
        st.dataframe(pd.DataFrame([{"Contrôle": n, "Résultat": "✅ OK" if ok else "❌ ÉCHEC"} for n, ok in ctx.resultat.controles]), hide_index=True, width="stretch", height="content")
        st.markdown("**Contrôles indépendants** (recalculés sans utiliser ceux du moteur)")
        st.dataframe(pd.DataFrame([{"Contrôle": n, "Résultat": "✅ OK" if ok else "❌ ÉCHEC", "Détail": d} for n, ok, d in ex.controles_independants[v]]),
                     hide_index=True, width="stretch", height="content")
    n = ex.inconnues.assign(date=pd.to_datetime(ex.inconnues["date"]).dt.strftime("%d/%m/%Y")).rename(columns={
        "supplier_id": "Fournisseur", "plant": "Usine", "date": "Date", "raison": "Raison", "ligne_grille": "Ligne de grille (km)", "nb_camions": "Camions", "cout": "Coût estimé (€)"})
    with st.expander(f"Lignes non optimisées ({len(n)}) et leur raison"):
        st.dataframe(ctx.garde(n.rename(columns={"Fournisseur": "supplier_id", "Usine": "plant"})).rename(columns={"supplier_id": "Fournisseur", "plant": "Usine"}),
                     hide_index=True, width="stretch", height=320,
                     column_config={"Coût estimé (€)": st.column_config.NumberColumn(format="%.0f €"), "Ligne de grille (km)": st.column_config.NumberColumn(format="%.0f")})
    with st.expander("Journal de préparation du planning"):
        st.dataframe(ex.journal.rename(columns={"etape": "Étape", "lignes_avant": "Lignes avant", "lignes_apres": "Lignes après",
                                                "retirees_ou_marquees": "Retirées ou marquées", "regle": "Règle"}), hide_index=True, width="stretch", height="content")
