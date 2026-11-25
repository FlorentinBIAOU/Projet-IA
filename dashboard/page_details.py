"""Page « Détails des sorties » : un couple, son profil, et le calendrier avant / après (le coeur de l'interface)."""
import streamlit as st

from dashboard import explorateur as xp
from dashboard import sorties_client as sc
from dashboard import style

CLASSES_STATUT = {sc.STATUT_OPT: "", sc.STATUT_PART: "partiel", sc.STATUT_NON: "non", sc.STATUT_VIDE: "vide"}


def _retenir():
    st.session_state["couple_sel"] = st.session_state["liste_couples"]


def page():
    ctx = xp.contexte()
    options = list(ctx.couples)
    sel = st.session_state.get("couple_sel")
    if sel is None or sel not in sc.couples_fichier(ctx.ex):
        meilleurs = ctx.opt.sort_values("economie_eur", ascending=False)                    # par defaut : le couple qui rapporte le plus
        sel = next(((a, b) for a, b in zip(meilleurs["supplier_id"], meilleurs["plant"])), options[0] if options else None)
    if sel is None:
        st.info("Aucun couple ne correspond aux filtres.")
        return
    if sel not in options:
        options = [sel] + options                       # le couple choisi reste affiche meme si un filtre l'ecarte
    if st.session_state.get("liste_couples") != sel:
        st.session_state["liste_couples"] = sel
    st.selectbox("Couple fournisseur × usine", options, format_func=xp.nom_couple, key="liste_couples", on_change=_retenir, placeholder="Rechercher un couple…")
    sel = st.session_state["liste_couples"]
    st.session_state["couple_sel"] = sel
    c = sc.couple(ctx.ex, ctx.version, sel)
    st.markdown(f'<div class="entete-couple"><span class="nom">{xp.e(xp.nom_couple(sel))}</span>{xp.pastilles_jours(c["jours_profil"])}'
                f'<span class="puce-statut {CLASSES_STATUT[c["statut"]]}">{xp.e(c["statut"])}</span><span class="prof">{xp.e(c["profil"])}</span></div>', unsafe_allow_html=True)
    style.kpis_compacts([
        ("Camions optimisés", xp.nombre(c["camions_optimises"]), "", ""),
        ("Envois hors optimisation", xp.nombre(c["envois_non_optimises"]), "", "gris"),
        ("Livraisons aujourd'hui", xp.nombre(c["livraisons_aujourdhui"]), "", "gris"),
        ("Coût avant → après", f"{xp.nombre(c['cout_avant'])} → {xp.eur(c['cout_apres'])}",
         f"<b>−{xp.pct((c['cout_avant'] - c['cout_apres']) / c['cout_avant'] * 100, 0)}</b>" if c["cout_avant"] > 0 else "rien à optimiser", "vert"),
    ])
    xp.calendrier_complet(ctx, sel)
