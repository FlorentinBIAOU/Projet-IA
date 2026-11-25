"""Page « Gains » : avant / apres, par usine, lissage, couples."""
import pandas as pd
import streamlit as st

from dashboard import explorateur as xp
from dashboard import graphiques as gr
from dashboard import sorties_client as sc
from dashboard import style

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
    ex, v = ctx.ex, ctx.version
    if ex.comparaison is not None:
        cartes = []
        for _, r in ex.comparaison.iterrows():
            cartes.append((xp.VERSIONS_NOMS[r["version"]], "Recommandée" if r["version"] == "strict" else "", xp.eur(r["cout"]),
                           [f"Économie : <b>{xp.pct(r['economie %'])}</b>", f"Camions : <b>{int(r['camions'])}</b>",
                            f"Rythme tenu : <b>{xp.pct(r['part semaines respectees %'], 0)}</b> des semaines"]))
        style.cartes_versions(cartes)
    t1, t2, t3, t4 = st.tabs(["Avant / après", "Par usine", "Lissage", "Couples"])
    cam = _camions_apres(ctx)
    envois = ctx.envois
    rempl_apres = cam[cam["type"] == sc.TYPE_OPT]["remplissage_poids_%"]
    rempl_avant = envois["remplissage_poids_%"]
    resume, _ = sc.camions(ex, v, "apres")
    non = ctx.garde(resume[resume["type"] == sc.TYPE_NON])                # livres comme aujourd'hui : memes camions et meme cout avant et apres
    non = non.assign(lundi=non["date_livraison"].map(sc.lundi_de))

    # ------------------------------------------------------------------ avant / apres
    with t1:
        act = sc.cout_actuel_jours(ex)
        act = ctx.garde(act)
        liv_avant, liv_apres = len(act), len(cam[["supplier_id", "plant", "date_livraison"]].drop_duplicates())
        n_non, cout_non = len(non), float(non["prix"].sum())
        cout_avant_t, cout_apres_t = ctx.avant + cout_non, ctx.apres + cout_non
        cam_avant_t, cam_apres_t = ctx.camions_avant + n_non, ctx.camions_apres + n_non
        part = lambda n, total: xp.pct(n / total * 100) if total else "—"
        c1, c2 = st.columns(2)
        with c1, style.carte_graphique("Coût du transport total"):
            graphique(gr.comparaison_horizontale(["Avant", "Après"], [cout_avant_t, cout_apres_t], [gr.AVANT, gr.APRES], ",.0f", hauteur=130))
        with c2, style.carte_graphique("Camions au total"):
            graphique(gr.comparaison_horizontale(["Avant", "Après"], [cam_avant_t, cam_apres_t], [gr.AVANT, gr.APRES], ",.0f", hauteur=130))
        gain_cout, gain_cam = cout_avant_t - cout_apres_t, cam_avant_t - cam_apres_t
        style.tableau_avant_apres([                                    # (libelle, avant, apres, ecart, niveau) ; niveau : total, detail, simple
            ("Coût total", xp.eur(cout_avant_t), xp.eur(cout_apres_t), f"−{xp.eur(gain_cout)}", "total"),
            ("dont périmètre optimisé", xp.eur(ctx.avant), xp.eur(ctx.apres), f"−{xp.pct((ctx.avant - ctx.apres) / ctx.avant * 100)}", "detail"),
            ("dont hors optimisation (données manquantes)", xp.eur(cout_non), xp.eur(cout_non), "inchangé", "detail"),
            ("Camions au total", xp.nombre(cam_avant_t), xp.nombre(cam_apres_t), f"−{xp.nombre(gain_cam)}", "total"),
            ("dont périmètre optimisé", xp.nombre(ctx.camions_avant), xp.nombre(ctx.camions_apres), f"−{xp.nombre(ctx.camions_avant - ctx.camions_apres)}", "detail"),
            ("dont hors optimisation (données manquantes)", xp.nombre(n_non), xp.nombre(n_non), "inchangé", "detail"),
            ("Pourcentage des camions non optimisés", "—", part(n_non, cam_apres_t), "", "simple"),
            ("Livraisons", xp.nombre(liv_avant + n_non), xp.nombre(liv_apres + n_non), f"−{xp.nombre(liv_avant - liv_apres)}", "simple"),
            ("Remplissage moyen des camions optimisés (poids)", xp.pct(rempl_avant.mean()), xp.pct(rempl_apres.mean()), "", "simple"),
        ])
        c1, c2 = st.columns(2)
        bornes = [0, 1, 2, 5, 10, 20, 30, 50, 75, 100.01]
        libelles = ["< 1 %", "1-2", "2-5", "5-10", "10-20", "20-30", "30-50", "50-75", "75-100"]
        a = pd.cut(rempl_avant, bornes, labels=libelles, right=False).value_counts().reindex(libelles)
        b = pd.cut(rempl_apres, bornes, labels=libelles, right=False).value_counts().reindex(libelles)
        with c1, style.carte_graphique("Remplissage des camions optimisés"):
            graphique(gr.barres_groupees(long_avant_apres(libelles, a.values, b.values, "tranche"), "tranche", "valeur", ordre=libelles, titre_y="camions", hauteur=260))
        cout_avant = (envois["cout"] / envois["nb_camions"]).values
        with c2, style.carte_graphique("Coût d'un camion optimisé"):
            graphique(gr.histogramme_cout(pd.concat([pd.DataFrame({"cout": cout_avant, "serie": "Avant"}),
                                                     pd.DataFrame({"cout": cam["prix"].values, "serie": "Après"})]), hauteur=260))
        sem_non = non.groupby("lundi").size()                           # les non optimises comptent avant et apres
        sem_avant = envois.groupby("semaine")["nb_camions"].sum().add(sem_non, fill_value=0)
        sem_apres = cam.groupby("lundi").size().add(sem_non, fill_value=0)
        semaines = sorted(set(sem_avant.index) | set(sem_apres.index))
        etiq = [sc.jj_mm(s) for s in semaines]
        with style.carte_graphique("Camions par semaine (total)"):
            graphique(gr.barres_groupees(long_avant_apres(etiq, [sem_avant.get(s, 0) for s in semaines], [sem_apres.get(s, 0) for s in semaines], "semaine"),
                                         "semaine", "valeur", ordre=etiq, titre_y="camions", titre_x="semaine du", hauteur=260))

    # ------------------------------------------------------------------ par usine
    with t2:
        par_usine = ctx.opt.groupby("plant")[["cout_actuel", "cout_optimise"]].sum().rename(columns={"cout_actuel": "avant", "cout_optimise": "après"})
        cout_non = non.groupby("plant")["prix"].sum()
        par_usine = par_usine.reindex(par_usine.index.union(cout_non.index)).fillna({"avant": 0, "après": 0})
        par_usine["non optimisés"] = cout_non.reindex(par_usine.index).fillna(0)
        par_usine["avant"] += par_usine["non optimisés"]
        par_usine["après"] += par_usine["non optimisés"]
        par_usine["économie"] = par_usine["avant"] - par_usine["après"]
        par_usine["économie %"] = par_usine["économie"] / par_usine["avant"] * 100
        c1, c2 = st.columns(2)
        with c1, style.carte_graphique("Coût total du transport par usine"):
            graphique(gr.barres_groupees(long_avant_apres(list(par_usine.index), par_usine["avant"].values, par_usine["après"].values, "usine"),
                                         "usine", "valeur", ordre=list(par_usine.index), titre_y="coût (€)", hauteur=260))
        with c2:
            tab = par_usine.reset_index().rename(columns={"index": "Usine", "plant": "Usine", "avant": "Avant", "après": "Après",
                                                          "non optimisés": "dont hors optimisation", "économie": "Économie"})
            tab = tab[["Usine", "Avant", "Après", "dont hors optimisation", "Économie", "économie %"]]
            for col in ("Avant", "Après", "dont hors optimisation", "Économie"):
                tab[col] = tab[col].map(xp.eur)
            st.dataframe(tab, hide_index=True, width="stretch", column_config={"économie %": st.column_config.ProgressColumn("Économie %", min_value=0, max_value=100, format="%.0f %%")})
        tous = pd.concat([cam[["plant", "date_livraison", "lundi"]], non[["plant", "date_livraison", "lundi"]]])    # optimises et non optimises
        usines = sorted(tous["plant"].unique())
        if usines:
            usine = st.selectbox("Calendrier de l'usine", usines, key="usine_calendrier")
            c = tous[tous["plant"] == usine]
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
        deplaces = sc.couples_deplaces(ex, v)
        deplaces = [c for c in deplaces if choix == "Toutes les usines" or c[1] == choix]          # suit l'usine choisie
        lignes = []
        for etat, nom in zip(sc.ETATS, gr.ETATS_LISSAGE):
            t = tot[tot["etat"] == etat].set_index("jour")["n"].reindex(range(5), fill_value=0)
            lignes += [{"jour": JOURS_COURTS[j], "etat": nom, "part": float(t[j] / max(t.sum(), 1) * 100)} for j in range(5)]
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
