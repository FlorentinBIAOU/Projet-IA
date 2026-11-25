"""Affichage partage par les pages : formats, contexte (resultat + filtres), indicateurs du haut, calendrier d'un couple, panneau d'un camion.

Le calcul est dans `sorties_client.py` (fonctions pures) ; ici, on ne fait que mettre en forme avec Streamlit.
"""
import html
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st

from dashboard import sorties_client as sc
from dashboard import style
from src import sorties, tarifs

PAGES = {}                      # nom -> st.Page, rempli par app.py (pour ouvrir un couple depuis un tableau)
VERSIONS_NOMS = {"strict": "Stricte", "intermediaire": "Intermédiaire", "libre": "Libre"}
JOURS_LETTRES = ["L", "M", "M", "J", "V"]
CLASSES_TYPE = {sc.TYPE_OPT: "opt", sc.TYPE_EXC: "exc", sc.TYPE_NON: "non", sc.TYPE_ACT: "act"}


# ----------------------------------------------------------------------------------------------- formats
def eur(x, dec=0):
    """Montant au format 82 111 €."""
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",") + " €"


def nombre(x):
    return f"{round(float(x)):,}".replace(",", "\u00a0")


def pct(x, dec=1):
    return f"{x:.{dec}f}".replace(".", ",") + " %"


def kg(x):
    return f"{x:,.0f}".replace(",", " ") + " kg"


def e(texte):
    return html.escape(str(texte))


def nom_couple(cle):
    return f"{cle[0]} × {cle[1]}"


# ----------------------------------------------------------------------------------------------- contexte
def construire_contexte(ex, version, versions, nom_planning, lundi, usines, fournisseurs, cle_cache=""):
    """Tout ce que lisent les pages : le resultat de la version affichee, la semaine et les filtres, avec les tableaux deja filtres."""
    moteur = ex.moteur
    resultat = ex.resultats[version]

    def garde(df, col_s="supplier_id", col_p="plant"):
        if usines:
            df = df[df[col_p].isin(usines)]
        if fournisseurs:
            df = df[df[col_s].isin(fournisseurs)]
        return df

    profils = sorties.profils_couples(moteur, resultat)
    couples = [c for c in sc.couples_fichier(ex) if (not usines or c[1] in usines) and (not fournisseurs or c[0] in fournisseurs)]
    opt = garde(profils[profils["cout_optimise"].notna()])
    contenu = garde(resultat.contenu)
    envois = garde(tarifs.envois_actuels(ex.planning_propre, moteur.grille))
    potentiel = garde(tarifs.potentiel_couples(tarifs.envois_actuels(ex.planning_propre, moteur.grille), moteur.grille))
    ctx = SimpleNamespace(ex=ex, moteur=moteur, version=version, versions=versions, resultat=resultat, nom_planning=nom_planning, lundi=pd.Timestamp(lundi) if lundi is not None else None,
                          usines=list(usines), fournisseurs=list(fournisseurs), garde=garde, profils=profils, opt=opt, contenu=contenu, envois=envois,
                          potentiel=potentiel, couples=couples, cle_cache=cle_cache)
    ctx.avant, ctx.apres = float(opt["cout_actuel"].sum()), float(opt["cout_optimise"].sum())
    ctx.camions_avant, ctx.camions_apres = int(envois["nb_camions"].sum()), int(contenu["camion_id"].nunique())
    ctx.couples_couverts = len(opt)
    # Indicateurs du haut : la semaine choisie (un camion compte la semaine ou il part), ou tout l'horizon
    ctx.kpi_avant, ctx.kpi_apres, ctx.kpi_camions_avant, ctx.kpi_camions_apres = ctx.avant, ctx.apres, ctx.camions_avant, ctx.camions_apres
    if ctx.lundi is not None:
        act = garde(sc.cout_actuel_jours(ex))
        act = act[act["date"].map(sc.lundi_de) == ctx.lundi]
        cam, _ = sc.camions(ex, version, "apres")
        cam = garde(cam[cam["type"] != sc.TYPE_NON])
        cam = cam[cam["date_livraison"].map(sc.lundi_de) == ctx.lundi]
        ctx.kpi_avant, ctx.kpi_apres = float(act["cout"].sum()), float(cam["prix"].sum())
        ctx.kpi_camions_avant, ctx.kpi_camions_apres = int(act["camions"].sum()), len(cam)
    return ctx


def contexte():
    return st.session_state["ctx"]


def kpis_haut(ctx):
    """La ligne d'indicateurs du haut de chaque page : version, semaine et filtres du moment."""
    gain = (ctx.kpi_avant - ctx.kpi_apres) / ctx.kpi_avant * 100 if ctx.kpi_avant else 0.0
    periode = f"semaine du {ctx.lundi:%d/%m}" if ctx.lundi is not None else "toutes les semaines"
    style.kpis_compacts([
        (f"Coût · {periode}", f"{nombre(ctx.kpi_avant)} → {eur(ctx.kpi_apres)}", f"<b>−{pct(gain)}</b>", "vert"),
        (f"Camions · {periode}", f"{nombre(ctx.kpi_camions_avant)} → {nombre(ctx.kpi_camions_apres)}",
         f"−{nombre(ctx.kpi_camions_avant - ctx.kpi_camions_apres)}", ""),
        ("Couples couverts", f"{ctx.couples_couverts} / {len(ctx.couples)}", "", "gris"),
    ])


def ouvrir_couple(cle):
    """Memorise le couple et ouvre la page « Détails des sorties »."""
    st.session_state["couple_sel"] = tuple(cle)
    st.switch_page(PAGES["details"])


def tableau_cliquable(df, key, config, hauteur=380):
    """Un tableau dont on peut cliquer une ligne : renvoie la ligne cliquee (une Series), ou None."""
    ev = st.dataframe(df, hide_index=True, width="stretch", column_config=config, height=hauteur, on_select="rerun", selection_mode="single-row", key=key)
    lignes = ev.selection.rows if ev is not None else []
    return df.iloc[lignes[0]] if lignes else None


def bouton_ouvrir(cle, key):
    if cle is not None and st.button(f"Voir le détail de {nom_couple(cle)} →", key=key, type="primary"):
        ouvrir_couple(cle)


# ----------------------------------------------------------------------------------------------- calendrier d'un couple
def pastilles_jours(jours_profil):
    return '<span class="pastilles-jours">' + "".join(f'<b class="{"on" if i in jours_profil else ""}">{JOURS_LETTRES[i]}</b>' for i in range(5)) + "</span>"


def m3(x):
    return f"{x:,.1f}".replace(",", "\u00a0").replace(".", ",") + "\u00a0m³"


def tonnes(x):
    """Poids court pour le calendrier : 2,7 t (ou 850 kg sous la tonne)."""
    return kg(x) if x < 1000 else f"{x / 1000:,.1f}".replace(",", "\u00a0").replace(".", ",") + "\u00a0t"


def _carte_camion(t, sel):
    """Un camion sur une ligne : poids · volume · prix (la couleur du trait donne le type)."""
    cls = CLASSES_TYPE[t["type"]]
    poids = tonnes(t["poids"]) if pd.notna(t["poids"]) else "poids ?"
    volume = m3(t["volume"]) if pd.notna(t["volume"]) else "volume ?"
    return f'<div class="cam {cls}">{poids} · {volume} · <b>{eur(t["prix"])}</b></div>'


def calendrier_html(cal, aujourdhui=False):
    """Le calendrier semaine x jour d'un couple : fond teinte = jour du profil ; une carte par camion."""
    h = '<div class="cal"><div></div>' + "".join(f'<div class="ent">{j[:3]}</div>' for j in sc.JOURS)
    for s in cal["semaines"]:
        h += f'<div class="sem">{jj_mm(s["lundi"])}</div>'
        for j in s["jours"]:
            teinte = bool(j["camions"]) if aujourdhui else j["profil"]          # aujourd'hui : pas de profil, on teinte les jours livres
            classes = "j" + (" prof" if teinte else "") + (" ferme" if j["ferme"] else "")
            contenu = "".join(_carte_camion(t, False) for t in j["camions"])
            h += f'<div class="{classes}"><div class="d"><span>{j["date"].day}</span>{"<i>fermé</i>" if j["ferme"] else ""}</div>{contenu}</div>'
    return h + "</div>"


def jj_mm(d):
    return sc.jj_mm(d)


def legende_html(aujourdhui=False):
    if aujourdhui:
        items = [("#8895A7", "livraison actuelle"), ("#D9822B", "hors optimisation"), ("#BBD7EE", "jour livré")]
    else:
        items = [("#0072B2", "camion optimisé"), ("#C0392B", "exceptionnel"), ("#D9822B", "hors optimisation"), ("#BBD7EE", "jour du profil")]
    return '<div class="legende">' + "".join(f'<span style="--c:{c}">{t}</span>' for c, t in items) + "</div>"


def calendrier_complet(ctx, cle):
    """Le coeur de la page « Détails des sorties » : le choix de la vue, puis le calendrier."""
    c1, c2 = st.columns([3, 2])
    with c1:
        vue = st.segmented_control("Vue du calendrier", list(sc.ETATS), default="apres", format_func=sc.ETATS.get, key="vue_calendrier", label_visibility="collapsed")
    vue = vue or "apres"
    cal = sc.calendrier_couple(ctx.ex, ctx.version, cle, vue)
    phrase = sc.phrase_deplacement(ctx.ex, ctx.version, cle)
    with c2:
        if phrase and vue != "aujourdhui":
            st.caption(f"Lissage : {phrase}.")
    st.html(legende_html(vue == "aujourdhui") + calendrier_html(cal, vue == "aujourdhui"))
