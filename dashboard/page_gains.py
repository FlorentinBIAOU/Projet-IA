"""Page « Gains » : avant / apres, par usine, lissage, couples, et pourquoi regrouper paie."""
import numpy as np
import pandas as pd
import streamlit as st

from dashboard import explorateur as xp
from dashboard import graphiques as gr
from dashboard import sorties_client as sc
from dashboard import style
from src import tarifs

JOURS_COURTS = [j[:3] for j in sc.JOURS]


def graphique(chart):
    st.altair_chart(chart, theme=None, width="stretch")


def long_avant_apres(etiquettes, avant, apres, colonne="etiquette"):
    return pd.DataFrame([{colonne: k, "serie": s, "valeur": float(v)} for k, a, b in zip(etiquettes, avant, apres) for s, v in (("Avant", a), ("Après", b))])


def _camions_apres(ctx):
    """Les camions optimises (normaux et exceptionnels) apres lissage, filtres : prix, remplissage, semaine de depart."""
    resume, _ = sc.camions(ctx.ex, ctx.version, "apres")
    r = ctx.garde(resume[resume["type"] != sc.TYPE_NON])
    return r.assign(lundi=r["date_livraison"].map(sc.lundi_de))


def page():
    ctx = xp.contexte()
    xp.kpis_haut(ctx)
    ex, v = ctx.ex, ctx.version
    if ex.comparaison is not None:
        cartes = []
        for _, r in ex.comparaison.iterrows():
            cartes.append((xp.VERSIONS_NOMS[r["version"]], "Recommandée" if r["version"] == "strict" else "", xp.eur(r["cout"]),
                           [f"Économie : <b>{xp.pct(r['economie %'])}</b>", f"Camions : <b>{int(r['camions'])}</b>",
                            f"Rythme tenu : <b>{xp.pct(r['part semaines respectees %'], 0)}</b> des semaines"]))
        style.cartes_versions(cartes)
    t1, t2, t3, t4, t5 = st.tabs(["Avant / après", "Par usine", "Lissage", "Couples", "Pourquoi regrouper paie"])
    cam = _camions_apres(ctx)
    envois = ctx.envois
    rempl_apres = cam[cam["type"] == sc.TYPE_OPT]["remplissage_poids_%"]
    rempl_avant = envois["remplissage_poids_%"]

    # ------------------------------------------------------------------ avant / apres
    with t1:
        act = sc.cout_actuel_jours(ex)
        act = ctx.garde(act)
        liv_avant, liv_apres = len(act), len(cam[["supplier_id", "plant", "date_livraison"]].drop_duplicates())
        c1, c2 = st.columns(2)
        with c1, style.carte_graphique("Coût du transport"):
            graphique(gr.comparaison_horizontale(["Avant", "Après"], [ctx.avant, ctx.apres], [gr.AVANT, gr.APRES], ",.0f", hauteur=130))
        with c2, style.carte_graphique("Camions"):
            graphique(gr.comparaison_horizontale(["Avant", "Après"], [ctx.camions_avant, ctx.camions_apres], [gr.AVANT, gr.APRES], ",.0f", hauteur=130))
        st.dataframe(pd.DataFrame({
            "Indicateur": ["Coût", "Camions", "Livraisons", "Remplissage moyen (poids)"],
            "Avant": [xp.eur(ctx.avant), xp.nombre(ctx.camions_avant), xp.nombre(liv_avant), xp.pct(rempl_avant.mean())],
            "Après": [xp.eur(ctx.apres), xp.nombre(ctx.camions_apres), xp.nombre(liv_apres), xp.pct(rempl_apres.mean())]}), hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        bornes = [0, 1, 2, 5, 10, 20, 30, 50, 75, 100.01]
        libelles = ["< 1 %", "1-2", "2-5", "5-10", "10-20", "20-30", "30-50", "50-75", "75-100"]
        a = pd.cut(rempl_avant, bornes, labels=libelles, right=False).value_counts().reindex(libelles)
        b = pd.cut(rempl_apres, bornes, labels=libelles, right=False).value_counts().reindex(libelles)
        with c1, style.carte_graphique("Remplissage des camions"):
            graphique(gr.barres_groupees(long_avant_apres(libelles, a.values, b.values, "tranche"), "tranche", "valeur", ordre=libelles, titre_y="camions", hauteur=260))
        cout_avant = (envois["cout"] / envois["nb_camions"]).values
        with c2, style.carte_graphique("Coût d'un camion"):
            graphique(gr.histogramme_cout(pd.concat([pd.DataFrame({"cout": cout_avant, "serie": "Avant"}),
                                                     pd.DataFrame({"cout": cam["prix"].values, "serie": "Après"})]), hauteur=260))
        sem_avant = envois.groupby("semaine")["nb_camions"].sum()
        sem_apres = cam.groupby("lundi").size()
        semaines = sorted(set(sem_avant.index) | set(sem_apres.index))
        etiq = [sc.jj_mm(s) for s in semaines]
        with style.carte_graphique("Camions par semaine"):
            graphique(gr.barres_groupees(long_avant_apres(etiq, [sem_avant.get(s, 0) for s in semaines], [sem_apres.get(s, 0) for s in semaines], "semaine"),
                                         "semaine", "valeur", ordre=etiq, titre_y="camions", titre_x="semaine du", hauteur=260))

    # ------------------------------------------------------------------ par usine
    with t2:
        par_usine = ctx.opt.groupby("plant")[["cout_actuel", "cout_optimise"]].sum().rename(columns={"cout_actuel": "avant", "cout_optimise": "après"})
        par_usine["économie"] = par_usine["avant"] - par_usine["après"]
        par_usine["économie %"] = par_usine["économie"] / par_usine["avant"] * 100
        c1, c2 = st.columns(2)
        with c1, style.carte_graphique("Coût du transport par usine"):
            graphique(gr.barres_groupees(long_avant_apres(list(par_usine.index), par_usine["avant"].values, par_usine["après"].values, "usine"),
                                         "usine", "valeur", ordre=list(par_usine.index), titre_y="coût (€)", hauteur=260))
        with c2:
            tab = par_usine.reset_index().rename(columns={"plant": "Usine", "avant": "Avant", "après": "Après", "économie": "Économie"})
            for col in ("Avant", "Après", "Économie"):
                tab[col] = tab[col].map(xp.eur)
            st.dataframe(tab, hide_index=True, width="stretch", column_config={"économie %": st.column_config.ProgressColumn("Économie %", min_value=0, max_value=100, format="%.0f %%")})
        usines = sorted(cam["plant"].unique())
        if usines:
            usine = st.selectbox("Calendrier de l'usine", usines, key="usine_calendrier")
            c = cam[cam["plant"] == usine]
            lundis = sorted(c["lundi"].unique())
            jour = c["date_livraison"].dt.weekday
            grille = c.assign(j=jour).groupby(["lundi", "j"]).size().unstack(fill_value=0).reindex(index=lundis, columns=range(5), fill_value=0)
            etiq_l = [sc.jj_mm(d) for d in lundis]
            df_cal = pd.DataFrame([{"semaine": etiq_l[i], "jour": JOURS_COURTS[j], "n": int(grille.values[i, j])} for i in range(len(lundis)) for j in range(5)])
            with style.carte_graphique(f"{usine} · camions par jour"):
                graphique(gr.calendrier(df_cal, JOURS_COURTS, etiq_l, hauteur=max(220, 46 * len(lundis))))

    # ------------------------------------------------------------------ lissage
    with t3:
        rep = sc.repartition_jours(ex, v)
        if ctx.usines:
            rep = rep[rep["plant"].isin(ctx.usines)]
        usines_rep = sorted(rep["plant"].unique())
        choix = st.segmented_control("Périmètre", ["Toutes les usines"] + usines_rep, default="Toutes les usines", key="lissage_usine", label_visibility="collapsed") or "Toutes les usines"
        d = rep if choix == "Toutes les usines" else rep[rep["plant"] == choix]
        tot = d.groupby(["etat", "jour"])["n"].sum().reset_index()
        noms = {"aujourdhui": gr.ETATS_LISSAGE[0], "avant": gr.ETATS_LISSAGE[1], "apres": gr.ETATS_LISSAGE[2]}
        lignes = []
        for etat in noms:
            t = tot[tot["etat"] == etat].set_index("jour")["n"].reindex(range(5), fill_value=0)
            lignes += [{"jour": JOURS_COURTS[j], "etat": noms[etat], "part": float(t[j] / max(t.sum(), 1) * 100)} for j in range(5)]
        deplaces = sc.couples_deplaces(ex, v)
        deplaces = [c for c in deplaces if (not ctx.usines or c[1] in ctx.usines) and (not ctx.fournisseurs or c[0] in ctx.fournisseurs)]
        with style.carte_graphique("Part des livraisons par jour de la semaine"):
            graphique(gr.barres_trois_etats(pd.DataFrame(lignes), "jour", "part", ordre=JOURS_COURTS, titre_y="% des livraisons"))
        if deplaces:
            with st.expander(f"Les {len(deplaces)} couples déplacés"):
                st.dataframe(pd.DataFrame([{"Couple": xp.nom_couple(c), "Changement": sc.phrase_deplacement(ex, v, c)} for c in deplaces]), hide_index=True, width="stretch", height=300)

    # ------------------------------------------------------------------ couples
    with t4:
        r = ctx.opt.merge(ctx.potentiel[["supplier_id", "plant", "gain_eur"]], on=["supplier_id", "plant"], how="left")
        r["couple"] = r["supplier_id"] + " × " + r["plant"]
        c1, c2 = st.columns(2)
        with c1, style.carte_graphique("Réalisé contre potentiel"):
            graphique(gr.realise_contre_potentiel(r.rename(columns={"gain_eur": "potentiel", "economie_eur": "realise"})[["couple", "potentiel", "realise"]]))
        top = ctx.opt.sort_values("economie_eur", ascending=False).head(10)
        with c2, style.carte_graphique("Les 10 couples les plus rentables"):
            graphique(gr.top_couples(pd.DataFrame({"couple": top["supplier_id"] + " × " + top["plant"], "economie": top["economie_eur"]})))
        choisi = st.selectbox("Ouvrir un de ces couples", [(a, b) for a, b in zip(top["supplier_id"], top["plant"])], format_func=xp.nom_couple, key="top_couple", index=None,
                              placeholder="Choisir un couple…")
        xp.bouton_ouvrir(choisi, "ouvrir_top")

    # ------------------------------------------------------------------ pourquoi regrouper paie
    with t5:
        grille = ctx.moteur.grille
        distances = ctx.opt["distance"].dropna()
        lignes_grille = [float(g) for g in grille.index if str(g).replace(".", "").isdigit()]
        ligne = str(next(g for g in grille.index if float(g) == min(lignes_grille, key=lambda x: abs(x - distances.median())))) if len(distances) and lignes_grille else str(grille.index[0])
        poids = np.linspace(10, ctx.moteur.CAP_POIDS, 300)
        prix = [tarifs.prix_camion(grille, ligne, p) for p in poids]
        df = pd.DataFrame({"ligne": f"{ligne} km", "poids": poids, "prix": prix, "prix_kg": [x / p for x, p in zip(prix, poids)]})
        with style.carte_graphique("Le prix au kilo selon le poids du camion"):
            graphique(gr.courbes_prix(df, "prix_kg", "prix au kilo (€/kg)", echelle_log=True))
        with st.expander("La grille complète (prix finaux, marge et diesel inclus)"):
            st.dataframe(grille.round(2), width="stretch")
