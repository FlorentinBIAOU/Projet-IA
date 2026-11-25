"""Style du dashboard : feuille de style, bandeau d'accueil, cartes de chiffres cles, encadres.

Palette : bleu marine (texte et bandeau), bleu (la solution), gris (la situation actuelle), vert (les economies).
"""
import html

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root { --navy:#0B2545; --bleu:#0072B2; --vert:#1E8E5A; --orange:#D9822B; --gris:#5B6B7F; --fond:#F4F6FA; --bord:#E3E8EF; }
html, body, .stApp, .stMarkdown, p, li, label, h1, h2, h3, h4, h5, button, input, textarea, [data-baseweb="tab"] p,
div[data-testid="stMarkdownContainer"], div[data-testid="stCaptionContainer"], div[data-testid="stWidgetLabel"] {
  font-family: Inter, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
/* les icones de Streamlit sont une police a part : on ne la remplace pas */
span[data-testid="stIconMaterial"], .material-symbols-rounded { font-family: "Material Symbols Rounded" !important; }
.stApp { background: var(--fond); }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1280px; }

/* ---- meme police partout dans nos composants (Streamlit impose la sienne aux titres) */
.hero, .hero *, .kpi, .kpi *, .carte, .carte *, .section, .aide, .titre-graphique, .sous-graphique, .pied, .logo, .etape-titre {
  font-family: Inter, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important; }

/* ---- bandeau d'accueil */
.hero { position: relative; overflow: hidden; color: #fff; border-radius: 20px; padding: 34px 42px 30px; margin-bottom: 22px;
  background: linear-gradient(120deg, #0B2545 0%, #134074 52%, #0072B2 100%); box-shadow: 0 10px 30px rgba(11,37,69,.22); }
.hero::after { content: ""; position: absolute; right: -60px; top: -80px; width: 340px; height: 340px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,.16) 0%, rgba(255,255,255,0) 70%); }
.hero .sur-titre { font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; color: rgba(255,255,255,.7); font-weight: 600; margin-bottom: 8px; }
.hero h1 { margin: 0 0 8px 0; padding: 0; font-size: 2.3rem; font-weight: 800; letter-spacing: -.02em; color: #fff; line-height: 1.15; }
.hero p { margin: 0; max-width: 780px; font-size: 1.05rem; color: rgba(255,255,255,.85); line-height: 1.55; }
.hero .pastilles { margin-top: 16px; }
.hero .pastilles span { display: inline-block; margin: 0 8px 8px 0; padding: 5px 13px; border-radius: 99px; font-size: .82rem; font-weight: 500;
  background: rgba(255,255,255,.13); border: 1px solid rgba(255,255,255,.25); }

/* ---- chiffres cles */
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 4px 0 22px; }
.kpi { background: #fff; border: 1px solid var(--bord); border-top: 4px solid var(--accent, #0072B2); border-radius: 16px; padding: 18px 22px 16px;
  box-shadow: 0 1px 2px rgba(11,37,69,.04), 0 8px 22px rgba(11,37,69,.06); }
.kpi .lib { font-size: .74rem; text-transform: uppercase; letter-spacing: .08em; color: var(--gris); font-weight: 600; }
.kpi .val { font-size: 2.05rem; font-weight: 800; color: var(--navy); line-height: 1.12; margin: 8px 0 6px; letter-spacing: -.02em; }
.kpi .det { font-size: .88rem; color: var(--gris); line-height: 1.4; }
.kpi.vert { --accent: #1E8E5A; } .kpi.vert .val { color: #1E8E5A; }
.kpi.gris { --accent: #9AA5B1; }
@media (max-width: 1000px) { .kpis { grid-template-columns: repeat(2, 1fr); } }

/* ---- cartes et encadres */
.carte { background: #fff; border: 1px solid var(--bord); border-radius: 16px; padding: 22px 26px;
  box-shadow: 0 1px 2px rgba(11,37,69,.04), 0 8px 22px rgba(11,37,69,.05); }
.carte h3 { margin: 0 0 10px; padding: 0; font-size: 1.08rem; font-weight: 700; color: var(--navy); }
.carte ul { margin: 6px 0 0 20px; padding: 0; color: #2B3A4D; line-height: 1.75; }
.carte li { margin-bottom: 4px; }
.carte.retenir { border-left: 5px solid var(--vert); }
.carte.attention { border-left: 5px solid var(--orange); }
.grille3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 8px; }
@media (max-width: 1000px) { .grille3 { grid-template-columns: 1fr; } }
.etape .num { width: 36px; height: 36px; border-radius: 50%; background: var(--bleu); color: #fff; font-weight: 700; display: flex;
  align-items: center; justify-content: center; margin-bottom: 12px; }
.etape p { margin: 0; color: var(--gris); line-height: 1.6; }
.version .nom { font-weight: 700; color: var(--navy); font-size: 1.05rem; }
.version .badge { display: inline-block; margin-left: 8px; padding: 2px 10px; border-radius: 99px; font-size: .72rem; font-weight: 700;
  background: #E5F4EC; color: #1E8E5A; vertical-align: middle; }
.version .chiffre { font-size: 1.6rem; font-weight: 800; color: var(--navy); margin: 8px 0 2px; }
.version .ligne { color: var(--gris); font-size: .9rem; line-height: 1.6; }

/* ---- titres de section */
.section { margin: 28px 0 2px; font-size: 1.35rem; font-weight: 700; color: var(--navy); letter-spacing: -.01em; }
.aide { margin: 0 0 14px; color: var(--gris); font-size: .95rem; line-height: 1.55; max-width: 900px; }
.titre-graphique { font-weight: 700; color: var(--navy); font-size: 1rem; margin-bottom: 2px; }
.sous-graphique { color: var(--gris); font-size: .85rem; margin-bottom: 8px; }

/* ---- conteneurs bordes (graphiques) */
div[data-testid="stVerticalBlockBorderWrapper"] { background: #fff; border-radius: 16px; border-color: var(--bord);
  box-shadow: 0 1px 2px rgba(11,37,69,.04), 0 8px 22px rgba(11,37,69,.05); }

/* ---- onglets, boutons, colonne de gauche */
button[data-baseweb="tab"] { font-size: .98rem; font-weight: 600; padding: 12px 18px; }
div[data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--bord); }
section[data-testid="stSidebar"] { border-right: 1px solid var(--bord); background: #fff; }
section[data-testid="stSidebar"] .etape-titre { font-weight: 700; color: var(--navy); font-size: .8rem; text-transform: uppercase;
  letter-spacing: .09em; margin: 10px 0 8px; }
section[data-testid="stSidebar"] .logo { font-size: 1.15rem; font-weight: 800; color: var(--navy); letter-spacing: -.01em; margin-bottom: 4px; }
section[data-testid="stSidebar"] .logo span { color: var(--bleu); }
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] { background: linear-gradient(90deg, #0072B2, #1B8AD3); border: none; color: #fff;
  font-weight: 700; padding: .72rem 1rem; border-radius: 12px; box-shadow: 0 8px 18px rgba(0,114,178,.28); }
.stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover { filter: brightness(1.06); }
.stDownloadButton button { border-radius: 12px; font-weight: 600; }
div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid var(--bord); }
.pied { color: #8895A7; font-size: .8rem; margin-top: 36px; text-align: center; }
</style>
"""


def appliquer_style():
    """Injecte la feuille de style une fois par page."""
    st.markdown(CSS, unsafe_allow_html=True)


def hero(titre, sous_titre, pastilles=(), sur_titre=""):
    """Le bandeau d'en-tete."""
    p = "".join(f"<span>{html.escape(x)}</span>" for x in pastilles)
    surtitre = f'<div class="sur-titre">{html.escape(sur_titre)}</div>' if sur_titre else ""
    st.markdown(f'<div class="hero">{surtitre}<h1>{html.escape(titre)}</h1><p>{html.escape(sous_titre)}</p>'
                f'<div class="pastilles">{p}</div></div>', unsafe_allow_html=True)


def kpis(cartes):
    """Une rangee de grandes cartes de chiffres cles. cartes : [(libelle, valeur, detail, ton)] avec ton parmi '', 'vert', 'gris'."""
    c = "".join(f'<div class="kpi {ton}"><div class="lib">{html.escape(lib)}</div><div class="val">{html.escape(val)}</div>'
                f'<div class="det">{det}</div></div>' for lib, val, det, ton in cartes)
    st.markdown(f'<div class="kpis">{c}</div>', unsafe_allow_html=True)


def section(titre, aide=""):
    st.markdown(f'<div class="section">{html.escape(titre)}</div>' + (f'<div class="aide">{aide}</div>' if aide else ""), unsafe_allow_html=True)


def encadre(titre, puces, ton=""):
    """Une carte avec un titre et une liste. ton : '', 'retenir' (bord vert) ou 'attention' (bord orange). Les puces peuvent contenir du HTML simple."""
    li = "".join(f"<li>{p}</li>" for p in puces)
    st.markdown(f'<div class="carte {ton}"><h3>{html.escape(titre)}</h3><ul>{li}</ul></div>', unsafe_allow_html=True)


def etapes(liste):
    """Les etapes de l'accueil : [(titre, texte)]."""
    c = "".join(f'<div class="carte etape"><div class="num">{i}</div><h3>{html.escape(t)}</h3><p>{x}</p></div>' for i, (t, x) in enumerate(liste, 1))
    st.markdown(f'<div class="grille3">{c}</div>', unsafe_allow_html=True)


def cartes_simples(liste):
    """Trois cartes d'information : [(titre, texte)]."""
    c = "".join(f'<div class="carte"><h3>{html.escape(t)}</h3><p style="margin:0;color:#5B6B7F;line-height:1.6">{x}</p></div>' for t, x in liste)
    st.markdown(f'<div class="grille3">{c}</div>', unsafe_allow_html=True)


def cartes_versions(versions):
    """Une carte par version du moteur : [(nom, badge, chiffre, lignes)]."""
    c = ""
    for nom, badge, chiffre, lignes in versions:
        b = f'<span class="badge">{html.escape(badge)}</span>' if badge else ""
        c += (f'<div class="carte version"><div class="nom">{html.escape(nom)}{b}</div><div class="chiffre">{html.escape(chiffre)}</div>'
              f'<div class="ligne">{"<br>".join(lignes)}</div></div>')
    st.markdown(f'<div class="grille3">{c}</div>', unsafe_allow_html=True)


def carte_graphique(titre, aide=""):
    """Un conteneur borde pour un graphique, avec son titre. A utiliser avec `with carte_graphique(...):`."""
    c = st.container(border=True)
    with c:
        st.markdown(f'<div class="titre-graphique">{html.escape(titre)}</div>' + (f'<div class="sous-graphique">{html.escape(aide)}</div>' if aide else ""),
                    unsafe_allow_html=True)
    return c


# ------------------------------------------------------------------------------------------------ calendrier d'un couple
# Elements ajoutes pour la page "Details des sorties" : calendrier semaine x jour, cartes de camions, pastilles de jours, panneau d'un camion.
# Les couleurs sont des variables : la page reste lisible en theme sombre (voir le bloc prefers-color-scheme).
CSS_CALENDRIER = """
<style>
:root { --cal-case:#FFFFFF; --cal-profil:#EAF3FB; --cal-profil-bord:#BBD7EE; --cal-texte:#2B3A4D; --cal-ferme-a:#F1F3F6; --cal-ferme-b:#E6E9EE; --cal-jauge:rgba(11,37,69,.13); }
@media (prefers-color-scheme: dark) { :root { --cal-case:#1B2433; --cal-profil:#16324A; --cal-profil-bord:#2C5A83; --cal-texte:#D5DDE8;
  --cal-ferme-a:#1E2531; --cal-ferme-b:#262E3C; --cal-jauge:rgba(255,255,255,.18); } }
.kpis.compact { margin: 0 0 14px; gap: 12px; }
.kpis.compact .kpi { padding: 11px 16px 10px; border-radius: 14px; }
.kpis.compact .val { font-size: 1.3rem; margin: 4px 0 2px; white-space: nowrap; }
.kpis.compact .det { font-size: .8rem; }
.kpi .val.ok { color: #1E8E5A; } .kpi .val.non { color: #C0392B; }
.pastilles-jours { display: inline-flex; gap: 5px; vertical-align: middle; }
.pastilles-jours b { width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: .74rem;
  font-weight: 700; background: #E3E8EF; color: #8895A7; }
.pastilles-jours b.on { background: var(--bleu); color: #fff; }
.puce-statut { display: inline-block; padding: 3px 12px; border-radius: 99px; font-size: .78rem; font-weight: 700; background: #E5F4EC; color: #1E8E5A; }
.puce-statut.partiel { background: #FDF0E1; color: #B5651D; } .puce-statut.non { background: #FDF0E1; color: #B5651D; } .puce-statut.vide { background: #E3E8EF; color: #5B6B7F; }
.entete-couple { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin: 4px 0 14px; }
.entete-couple .nom { font-size: 1.35rem; font-weight: 800; color: var(--navy); letter-spacing: -.01em; }
.entete-couple .prof { color: var(--gris); font-size: .9rem; }
.cal { display: grid; grid-template-columns: 62px repeat(5, minmax(0, 1fr)); gap: 6px; color: var(--cal-texte); }
.cal .ent { font-weight: 700; color: var(--gris); text-transform: uppercase; font-size: .68rem; letter-spacing: .07em; text-align: center; padding: 2px 0 4px; }
.cal .sem { font-weight: 700; color: var(--navy); font-size: .72rem; padding-top: 7px; line-height: 1.25; }
.cal .sem small { display: block; color: var(--gris); font-weight: 600; }
.cal .j { background: var(--cal-case); border: 1px solid var(--bord); border-radius: 10px; padding: 5px 6px 6px; min-height: 52px; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.cal .j.prof { background: var(--cal-profil); border-color: var(--cal-profil-bord); }
.cal .j.ferme { background: repeating-linear-gradient(45deg, var(--cal-ferme-a), var(--cal-ferme-a) 6px, var(--cal-ferme-b) 6px, var(--cal-ferme-b) 12px); }
.cal .j .d { font-size: .66rem; color: var(--gris); font-weight: 600; display: flex; justify-content: space-between; }
.cal .j .d i { font-style: normal; color: var(--bleu); font-weight: 700; }
.cam { border-radius: 8px; padding: 5px 7px 6px; border-left: 4px solid var(--typ); background: var(--typfond); color: #2B3A4D; font-size: .72rem; line-height: 1.3; }
.cam.opt { --typ: #0072B2; --typfond: #E1EFFA; } .cam.exc { --typ: #C0392B; --typfond: #FBE6E2; }
.cam.non { --typ: #D9822B; --typfond: #FDEFDC; } .cam.act { --typ: #8895A7; --typfond: #ECEFF4; }
.cam.sel { outline: 2px solid var(--navy); outline-offset: 1px; }
.cam .t { font-weight: 700; color: var(--navy); display: flex; justify-content: space-between; gap: 4px; }
.cam .prix { font-weight: 700; } .cam .b { color: #5B6B7F; font-size: .68rem; }
.jauge { height: 5px; background: var(--cal-jauge); border-radius: 3px; overflow: hidden; margin: 3px 0; }
.jauge i { display: block; height: 100%; background: var(--typ, #0072B2); border-radius: 3px; }
.jauge.grande { height: 10px; border-radius: 5px; margin: 5px 0 12px; } .jauge.grande i { border-radius: 5px; }
.pt { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: var(--pt, #8895A7); margin-right: 4px; vertical-align: middle; }
.bes { font-size: .7rem; line-height: 1.3; padding: 2px 4px; border-radius: 5px; color: var(--cal-texte); }
.bes small { color: var(--gris); } .bes.sel { background: rgba(11,37,69,.10); font-weight: 600; }
.legende { display: flex; flex-wrap: wrap; gap: 16px; font-size: .78rem; color: var(--gris); margin: 6px 0 14px; }
.legende span::before { content: ""; display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; background: var(--c); border: 1px solid rgba(11,37,69,.15); }
.panneau-titre { font-size: 1.1rem; font-weight: 800; color: var(--navy); } .panneau-sous { color: var(--gris); font-size: .86rem; margin-bottom: 8px; }
.ligne-chiffres { display: flex; flex-wrap: wrap; gap: 22px; margin: 6px 0 10px; }
.ligne-chiffres div { font-size: .78rem; color: var(--gris); text-transform: uppercase; letter-spacing: .05em; } .ligne-chiffres b { display: block; font-size: 1.15rem; color: var(--navy); text-transform: none; letter-spacing: 0; }
</style>
"""


def appliquer_style_calendrier():
    """Injecte les styles du calendrier (a appeler apres `appliquer_style`)."""
    st.markdown(CSS_CALENDRIER, unsafe_allow_html=True)


def kpis_compacts(cartes):
    """La ligne d'indicateurs du haut de chaque page : [(libelle, valeur, detail, ton)], ton parmi '', 'vert', 'gris', 'rouge'."""
    c = ""
    for lib, val, det, ton in cartes:
        accent = {"rouge": "style=\"--accent:#C0392B\""}.get(ton, "")
        classe_val = {"vert": "ok", "rouge": "non"}.get(ton, "")
        c += (f'<div class="kpi {"vert" if ton == "vert" else ton}" {accent}><div class="lib">{html.escape(lib)}</div>'
              f'<div class="val {classe_val}">{html.escape(val)}</div><div class="det">{det}</div></div>')
    st.markdown(f'<div class="kpis compact">{c}</div>', unsafe_allow_html=True)


def _css_haut():
    st.markdown("<style>.logo-haut{font-size:1.25rem;font-weight:800;color:#0B2545;letter-spacing:-.01em}.logo-haut span{color:#0072B2}"
                "section[data-testid='stSidebar'],div[data-testid='stSidebarCollapsedControl']{display:none}"
                "header[data-testid='stHeader']{background:#F4F6FA !important;border-bottom:1px solid #E3E8EF;z-index:1000}</style>", unsafe_allow_html=True)
