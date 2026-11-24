"""Graphiques interactifs du dashboard (Altair).

Les couleurs ont un sens constant dans tout le dashboard : gris = situation actuelle (avant), bleu = solution du moteur (apres).
"""
import altair as alt
import pandas as pd

AVANT, APRES, VERT, ORANGE, NAVY = "#9AA5B1", "#0072B2", "#1E8E5A", "#D9822B", "#0B2545"
SERIES = ["Avant", "Après"]
CATEGORIES = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]       # palette sure pour les daltoniens
POLICE = "Inter, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif"


@alt.theme.register("consolidation", enable=True)
def theme_consolidation() -> alt.theme.ThemeConfig:
    return {"config": {
        "font": POLICE,
        "view": {"stroke": "transparent"},
        "axis": {"domain": False, "ticks": False, "gridColor": "#E8ECF1", "labelColor": "#5B6B7F", "titleColor": "#5B6B7F",
                 "titleFontWeight": "normal", "labelFontSize": 12, "titleFontSize": 12, "labelPadding": 6},
        "legend": {"labelFontSize": 12, "titleFontSize": 12, "orient": "top", "title": None, "symbolType": "square", "labelColor": "#2B3A4D"},
        "range": {"category": CATEGORIES},
    }}


def fr(x, dec=0):
    """Nombre a la francaise : 143 321 ou 0,128 (espace fine insecable pour les milliers, virgule pour les decimales)."""
    return f"{x:,.{dec}f}".replace(",", "\u00a0").replace(".", ",")


def axe_milliers(**options):
    """Un axe dont les nombres s'ecrivent a la francaise (143 321 et non 143,321)."""
    return alt.Axis(labelExpr="replace(format(datum.value, ',.0f'), ',', ' ')", **options)


def _echelle_series():
    return alt.Scale(domain=SERIES, range=[AVANT, APRES])


def barres_groupees(df, x, valeur, serie="serie", ordre=None, titre_y="", hauteur=300, format_valeur=",.0f", angle=0, titre_x=None):
    """Barres groupees Avant / Apres. df : format long, une ligne par (x, serie)."""
    df = df.assign(texte=[fr(v) for v in df[valeur]])
    return alt.Chart(df).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X(f"{x}:N", sort=ordre, title=titre_x, axis=alt.Axis(labelAngle=angle)),
        xOffset=alt.XOffset(f"{serie}:N", sort=SERIES),
        y=alt.Y(f"{valeur}:Q", title=titre_y, axis=axe_milliers()),
        color=alt.Color(f"{serie}:N", scale=_echelle_series(), sort=SERIES),
        tooltip=[alt.Tooltip(f"{x}:N", title=titre_x or x), alt.Tooltip(f"{serie}:N", title=" "),
                 alt.Tooltip("texte:N", title=titre_y or valeur)],
    ).properties(height=hauteur)


def histogramme_cout(df, hauteur=300):
    """Distribution du cout d'un camion, avant et apres. df : colonnes cout, serie."""
    return alt.Chart(df).mark_bar(opacity=0.8, cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("cout:Q", bin=alt.Bin(maxbins=30, extent=[0, 600]), title="coût d'un camion (€)", axis=alt.Axis(values=[0, 100, 200, 300, 400, 500, 600])),
        y=alt.Y("count():Q", stack=None, title="camions"),
        color=alt.Color("serie:N", scale=_echelle_series(), sort=SERIES),
        tooltip=[alt.Tooltip("serie:N", title=" "), alt.Tooltip("count():Q", title="camions")],
    ).properties(height=hauteur)


def comparaison_horizontale(libelles, valeurs, couleurs, format_valeur=",.0f", unite="", hauteur=150):
    """Deux (ou trois) barres horizontales avec leur valeur ecrite au bout : la situation actuelle contre la solution."""
    df = pd.DataFrame({"libelle": libelles, "valeur": valeurs, "couleur": couleurs, "texte": [fr(v) for v in valeurs]})
    base = alt.Chart(df).encode(y=alt.Y("libelle:N", sort=None, title=None, axis=alt.Axis(labelFontSize=13, labelColor=NAVY)))
    barres = base.mark_bar(cornerRadiusEnd=6, height=34).encode(
        x=alt.X("valeur:Q", title=None, axis=None, scale=alt.Scale(domainMin=0)), color=alt.Color("couleur:N", scale=None),
        tooltip=[alt.Tooltip("libelle:N", title=" "), alt.Tooltip("texte:N", title="valeur")])
    texte = base.mark_text(align="left", dx=8, fontSize=15, fontWeight="bold", color=NAVY).encode(x="valeur:Q", text="texte:N")
    return (barres + texte).properties(height=hauteur)


def calendrier(df, jours, semaines, hauteur=260):
    """Carte de chaleur : camions par jour de la semaine (colonnes) et par semaine (lignes). df : semaine, jour, n."""
    seuil = max(df["n"].max() * 0.5, 1)
    base = alt.Chart(df).encode(
        x=alt.X("jour:O", sort=jours, title=None, axis=alt.Axis(orient="top", labelAngle=0, labelFontSize=13, labelColor=NAVY)),
        y=alt.Y("semaine:O", sort=semaines, title=None, axis=alt.Axis(labelFontSize=12)))
    cases = base.mark_rect(cornerRadius=6, stroke="white", strokeWidth=3).encode(
        color=alt.Color("n:Q", scale=alt.Scale(scheme="blues", domainMin=0), legend=None),
        tooltip=[alt.Tooltip("semaine:O", title="semaine du"), alt.Tooltip("jour:O", title="jour"), alt.Tooltip("n:Q", title="camions")])
    chiffres = base.mark_text(fontSize=14, fontWeight="bold").encode(
        text="n:Q", color=alt.condition(alt.datum.n > seuil, alt.value("white"), alt.value(NAVY))).transform_filter(alt.datum.n > 0)
    return (cases + chiffres).properties(height=hauteur)


def realise_contre_potentiel(df, hauteur=340):
    """Chaque point est un couple : potentiel du milestone 2 (x) contre economie realisee (y)."""
    lim = float(max(df["potentiel"].max(), df["realise"].max()) * 1.05)
    df = df.assign(pot_txt=[fr(v) for v in df["potentiel"]], real_txt=[fr(v) for v in df["realise"]])
    diag = alt.Chart(pd.DataFrame({"x": [0, lim], "y": [0, lim]})).mark_line(strokeDash=[5, 5], color=NAVY, opacity=0.6).encode(x="x:Q", y="y:Q")
    points = alt.Chart(df).mark_circle(size=70, color=APRES, opacity=0.65).encode(
        x=alt.X("potentiel:Q", title="potentiel estimé au départ (€)", scale=alt.Scale(domain=[0, lim]), axis=axe_milliers()),
        y=alt.Y("realise:Q", title="économie réalisée (€)", scale=alt.Scale(domain=[0, lim]), axis=axe_milliers()),
        tooltip=[alt.Tooltip("couple:N", title="couple"), alt.Tooltip("pot_txt:N", title="potentiel (€)"), alt.Tooltip("real_txt:N", title="réalisé (€)")])
    return (diag + points).properties(height=hauteur)


def concentration(df, hauteur=300):
    """Courbe cumulee des economies. df : rang, pourcentage."""
    ligne = alt.Chart(df).mark_line(color=APRES, strokeWidth=3).encode(
        x=alt.X("rang:Q", title="nombre de couples (du plus au moins rentable)"),
        y=alt.Y("pourcentage:Q", title="% des économies cumulées", scale=alt.Scale(domain=[0, 100])),
        tooltip=[alt.Tooltip("rang:Q", title="couples"), alt.Tooltip("pourcentage:Q", format=".0f", title="% des économies")])
    repere = alt.Chart(pd.DataFrame({"y": [80]})).mark_rule(strokeDash=[4, 4], color=ORANGE).encode(y="y:Q")
    return (repere + ligne).properties(height=hauteur)


def top_couples(df, hauteur=300):
    """Les couples les plus rentables. df : couple, economie."""
    df = df.assign(texte=[fr(v) for v in df["economie"]])
    base = alt.Chart(df).encode(y=alt.Y("couple:N", sort="-x", title=None, axis=alt.Axis(labelFontSize=12, labelColor=NAVY)))
    barres = base.mark_bar(cornerRadiusEnd=5, color=APRES).encode(
        x=alt.X("economie:Q", title="économie réalisée (€)", axis=axe_milliers(tickCount=5)),
        tooltip=[alt.Tooltip("couple:N", title="couple"), alt.Tooltip("texte:N", title="économie (€)")])
    texte = base.mark_text(align="left", dx=5, fontSize=12, color=NAVY).encode(x="economie:Q", text="texte:N")
    return (barres + texte).properties(height=hauteur)


def courbes_prix(df, y, titre_y, echelle_log=False, hauteur=330, escalier=False):
    """Une courbe par ligne de distance. df : poids, prix, prix_kg, ligne."""
    df = df.assign(poids_txt=[fr(v) for v in df["poids"]], prix_txt=[fr(v, 2) for v in df["prix"]], prixkg_txt=[fr(v, 3) for v in df["prix_kg"]])
    if echelle_log:
        axe_y = alt.Axis(values=[0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5], labelExpr="replace(toString(datum.value), '.', ',')")
    else:
        axe_y = axe_milliers()
    return alt.Chart(df).mark_line(strokeWidth=2.8, interpolate="step-after" if escalier else "monotone").encode(
        x=alt.X("poids:Q", title="poids du camion (kg)", axis=axe_milliers()),
        y=alt.Y(f"{y}:Q", title=titre_y, scale=alt.Scale(type="log", domain=[0.007, 6]) if echelle_log else alt.Scale(zero=True), axis=axe_y),
        color=alt.Color("ligne:N", title="distance", sort=None, legend=alt.Legend(title="Distance", orient="top")),
        tooltip=[alt.Tooltip("ligne:N", title="distance"), alt.Tooltip("poids_txt:N", title="poids (kg)"),
                 alt.Tooltip("prix_txt:N", title="prix (€)"), alt.Tooltip("prixkg_txt:N", title="prix au kilo (€)")],
    ).properties(height=hauteur)
