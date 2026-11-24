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
