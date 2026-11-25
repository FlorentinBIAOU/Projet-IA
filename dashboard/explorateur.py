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
TEINTES = ["#7B61C9", "#009E73", "#CC79A7", "#56B4E9", "#8C6D31", "#9B9B1F"]
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
    controles = sc.verifier(ex, version)
    non = [c for c in controles if not c["ok"]]
    non += [{"nom": n} for n, ok, _ in ex.controles_independants[version] if not ok]
    ctx = SimpleNamespace(ex=ex, moteur=moteur, version=version, versions=versions, resultat=resultat, nom_planning=nom_planning, lundi=pd.Timestamp(lundi),
                          usines=list(usines), fournisseurs=list(fournisseurs), garde=garde, profils=profils, opt=opt, contenu=contenu, envois=envois,
                          potentiel=potentiel, couples=couples, controles=controles, nb_non=len(non), cle_cache=cle_cache)
    ctx.avant, ctx.apres = float(opt["cout_actuel"].sum()), float(opt["cout_optimise"].sum())
    ctx.camions_avant, ctx.camions_apres = int(envois["nb_camions"].sum()), int(contenu["camion_id"].nunique())
    ctx.couples_couverts = len(opt)
    return ctx


def contexte():
    return st.session_state["ctx"]


def kpis_haut(ctx):
    """La ligne de 4 indicateurs du haut de chaque page, calculee sur la version, la semaine et les filtres du moment."""
    gain = (ctx.avant - ctx.apres) / ctx.avant * 100 if ctx.avant else 0.0
    controles = ("Contrôles", "OK" if ctx.nb_non == 0 else f"{ctx.nb_non} NON", "" if ctx.nb_non == 0 else "voir Contrôles",
                 "vert" if ctx.nb_non == 0 else "rouge")
    style.kpis_compacts([
        ("Coût du transport", f"{nombre(ctx.avant)} → {eur(ctx.apres)}", f"<b>−{pct(gain)}</b>", "vert"),
        ("Camions", f"{nombre(ctx.camions_avant)} → {nombre(ctx.camions_apres)}", f"−{nombre(ctx.camions_avant - ctx.camions_apres)}", ""),
        ("Couples couverts", f"{ctx.couples_couverts} / {len(ctx.couples)}", "", "gris"),
        controles,
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


def _carte_camion(t, sel):
    cls = CLASSES_TYPE[t["type"]]
    pt = f'<span class="pt" style="--pt:{TEINTES[t["teinte"]]}"></span>'
    nom = "Aujourd'hui" if t["type"] == sc.TYPE_ACT else t["id"]
    suffixe = f" ×{t['nb_camions']}" if t.get("nb_camions", 1) > 1 else ""
    if pd.notna(t["poids"]):
        poids = kg(t["poids"]) if t["poids"] < 1000 else f"{t['poids'] / 1000:,.1f}".replace(",", "\u00a0").replace(".", ",") + "\u00a0t"
        rempl = min(float(t["remplissage_poids"]), 100) if pd.notna(t["remplissage_poids"]) else 0
        jauge = f'<div class="jauge"><i style="width:{rempl:.0f}%"></i></div>'
    else:
        poids, jauge = "poids ?", '<div class="jauge"></div>'
    besoins = (f'<div class="b">besoins du {e(sc.liste_dates(t["besoins"]))}</div>' if t["type"] in (sc.TYPE_OPT, sc.TYPE_EXC)
               else ('<div class="b">non optimisé</div>' if t["type"] == sc.TYPE_NON else ""))
    typ = "<span>exceptionnel</span>" if t["type"] == sc.TYPE_EXC else ""
    return (f'<div class="cam {cls}{" sel" if sel else ""}"><div class="t"><span>{pt if t["type"] != sc.TYPE_ACT else ""}{e(nom)}{e(suffixe)}</span>{typ}</div>'
            f'<div>{poids}</div>{jauge}<div class="prix">{eur(t["prix"])}</div>{besoins}</div>')


def calendrier_html(cal, selection=None):
    """Le calendrier semaine x jour d'un couple : fond teinte = jour du profil ; camions en cartes ; besoins en lignes courtes."""
    h = '<div class="cal"><div></div>' + "".join(f'<div class="ent">{j[:3]}</div>' for j in sc.JOURS)
    for s in cal["semaines"]:
        lun = s["lundi"]
        h += f'<div class="sem">{jj_mm(lun)}<small>semaine</small></div>'
        for j in s["jours"]:
            classes = "j" + (" prof" if j["profil"] else "") + (" ferme" if j["ferme"] else "")
            contenu = "".join(_carte_camion(t, t["id"] == selection) for t in j["camions"])
            for b in j["besoins"]:
                t = cal["camions"][b["camion"]]
                pt = f'<span class="pt" style="--pt:{TEINTES[t["teinte"]]}"></span>' if t["type"] != sc.TYPE_ACT else '<span class="pt"></span>'
                depart = "le jour même" if b["parti_le"] == b["date"] else f"parti le {jj_mm(b['parti_le'])}"
                cible = "livré" if t["type"] == sc.TYPE_ACT else e(b["camion"])
                contenu += (f'<div class="bes{" sel" if b["camion"] == selection else ""}">{pt}{b["nb_lignes"]} ligne{"s" if b["nb_lignes"] > 1 else ""} '
                            f'→ {cible} <small>({depart})</small></div>')
            h += f'<div class="{classes}"><div class="d"><span>{j["date"]:%d/%m}</span>{"<i>profil</i>" if j["profil"] else ""}{"<i>fermé</i>" if j["ferme"] else ""}</div>{contenu}</div>'
    return h + "</div>"


def jj_mm(d):
    return sc.jj_mm(d)


def legende_html():
    items = [("#0072B2", "camion optimisé"), ("#C0392B", "envoi exceptionnel"), ("#D9822B", "non optimisé (livré comme aujourd'hui)"),
             ("#8895A7", "livraison actuelle"), ("#BBD7EE", "jour du profil")]
    return '<div class="legende">' + "".join(f'<span style="--c:{c}">{t}</span>' for c, t in items) + "</div>"


def jauge(pourcentage, couleur="#0072B2"):
    return f'<div class="jauge grande" style="--typ:{couleur}"><i style="width:{min(max(pourcentage, 0), 100):.0f}%"></i></div>'


def panneau_camion(ctx, cle, cal, camion_id, etat):
    """Le panneau d'un camion : besoins regroupes, materials, jauges poids et volume, prix, livraisons d'aujourd'hui remplacees."""
    t = cal["camions"][camion_id]
    m = ctx.moteur
    with st.container(border=True):
        nom = "Livraison actuelle" if t["type"] == sc.TYPE_ACT else f"Camion {t['id']}"
        st.markdown(f'<div class="panneau-titre">{e(nom)} · {t["jour"]} {t["date"]:%d/%m/%Y}</div>'
                    f'<div class="panneau-sous">{e(t["type"])} · {e(nom_couple(cle))}</div>', unsafe_allow_html=True)
        if t["type"] == sc.TYPE_ACT:
            lignes = sc.lignes_jour_actuel(ctx.ex, cle, t["date"])
            det = pd.DataFrame({"material": lignes["material"], "quai": lignes["unloading_point"], "quantité": lignes["schedule_quantity"],
                                "poids (kg)": lignes["weight"], "volume (m³)": lignes["volume"], "date du besoin": lignes["date"].dt.strftime("%d/%m/%Y"), "avance (j)": 0})
        else:
            det = sc.lignes_camion(ctx.ex, ctx.version, camion_id, etat)
            det = pd.DataFrame({"material": det["material"], "quai": det["unloading_point"], "quantité": det["quantite"], "poids (kg)": det["poids"],
                                "volume (m³)": det["volume"], "date du besoin": pd.to_datetime(det["date_besoin"]).dt.strftime("%d/%m/%Y"), "avance (j)": det["avance_jours"]})
        poids = t["poids"]
        chiffres = [("Prix", eur(t["prix"], 2)), ("Lignes", nombre(t["nb_lignes"])), ("Poids", kg(poids) if pd.notna(poids) else "inconnu"),
                    ("Remplace", f"{len(t['besoins'])} livraison(s)")]
        st.markdown('<div class="ligne-chiffres">' + "".join(f"<div>{a}<b>{e(b)}</b></div>" for a, b in chiffres) + "</div>", unsafe_allow_html=True)
        if pd.notna(poids) and t["type"] != sc.TYPE_NON:
            c1, c2 = st.columns(2)
            with c1:
                st.caption(f"Poids {pct(t['remplissage_poids'])}")
                st.markdown(jauge(t["remplissage_poids"]), unsafe_allow_html=True)
            with c2:
                st.caption(f"Volume {pct(t['remplissage_volume'])}")
                st.markdown(jauge(t["remplissage_volume"], "#009E73"), unsafe_allow_html=True)
        st.dataframe(det, hide_index=True, width="stretch", height=min(320, 38 + 35 * len(det)),
                     column_config={"quantité": st.column_config.NumberColumn(format="%.0f"), "poids (kg)": st.column_config.NumberColumn(format="%.1f"),
                                    "volume (m³)": st.column_config.NumberColumn(format="%.3f"), "avance (j)": st.column_config.NumberColumn(format="%d")})


def calendrier_complet(ctx, cle):
    """Le coeur de la page « Détails des sorties » : vue, calendrier, clic sur un camion."""
    c1, c2 = st.columns([3, 2])
    with c1:
        vue = st.segmented_control("Vue du calendrier", list(sc.ETATS), default="apres", format_func=sc.ETATS.get, key="vue_calendrier", label_visibility="collapsed")
    vue = vue or "apres"
    cal = sc.calendrier_couple(ctx.ex, ctx.version, cle, vue)
    phrase = sc.phrase_deplacement(ctx.ex, ctx.version, cle)
    with c2:
        if phrase and vue != "aujourdhui":
            st.caption(f"Lissage : {phrase}.")
    selection = None
    ordre = sorted(cal["camions"], key=lambda i: (cal["camions"][i]["date"], i))
    if ordre and vue != "aujourdhui":                                   # aujourd'hui : une livraison par jour de besoin, deja lisible dans le calendrier
        etiquette = lambda i: f"{i} · {cal['camions'][i]['date']:%d/%m}"
        selection = st.pills("Ouvrir un camion", ordre, selection_mode="single", format_func=etiquette, key=f"camion_{cle[0]}_{cle[1]}_{ctx.version}_{vue}")
    if selection:
        panneau_camion(ctx, cle, cal, selection, vue)
    st.html(legende_html() + calendrier_html(cal, selection))
