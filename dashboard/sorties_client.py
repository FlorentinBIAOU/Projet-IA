"""Les sorties pour le client, calculees a partir du resultat d'une execution (`ex`, voir src/pipeline.py).

Fonctions pures (aucun appel a Streamlit) : sortie1, sortie2, sortie3, couple, calendrier_couple, repartition_jours, verifier.
Rien n'est ecrit en dur : dates, semaines, couples et usines se deduisent du planning depose ; les regles viennent de src/config.py.

Trois "etats" d'une livraison sont comparables :
  - "aujourd'hui" : une livraison par couple et par jour de besoin (la situation actuelle) ;
  - "avant lissage" : les camions du meilleur profil de chaque couple (resultat.etape1) ;
  - "apres lissage" : les camions retenus (resultat.contenu).
Les lignes a information manquante (non optimisees) sont livrees le jour du besoin, comme aujourd'hui, dans les trois etats.
"""
import numpy as np
import pandas as pd

from src import config

JOURS = list(config.JOURS.values())                 # lundi ... vendredi
TYPE_OPT, TYPE_EXC, TYPE_NON, TYPE_ACT = "Optimisé", "Envoi exceptionnel", "Hors optimisation (données manquantes)", "Livraison actuelle"
ETATS = {"aujourdhui": "Aujourd'hui", "avant": "Avant lissage", "apres": "Après lissage"}
STATUT_OPT, STATUT_PART = "Optimisé", "Partiellement optimisé"
STATUT_NON, STATUT_VIDE = "Hors optimisation (données manquantes)", "Sans besoin sur l'horizon"


# ---------------------------------------------------------------------------------------------- petits outils
def lundi_de(d):
    d = pd.Timestamp(d).normalize()
    return d - pd.Timedelta(int(d.weekday()), unit="D")


def jj_mm(d):
    return pd.Timestamp(d).strftime("%d/%m")


def liste_dates(dates):
    """'12/11, 13/11' : les dates distinctes, triees."""
    return ", ".join(jj_mm(d) for d in sorted({pd.Timestamp(x) for x in dates}))


def _memo(ex, cle, fabrique):
    cache = ex.__dict__.setdefault("_cache_sorties_client", {})
    if cle not in cache:
        cache[cle] = fabrique()
    return cache[cle]


def _non_opt(ex):
    """Lignes non optimisees : le planning propre (statut != optimise) avec leur raison et leur cout estime (pire cas)."""
    def fabrique():
        p = ex.planning_propre
        n = p[p["statut"] != "optimise"].reset_index(drop=True)
        inc = ex.inconnues.reset_index(drop=True)
        n["raison"] = inc["raison"].values                 # `inconnues` est construit dans le meme ordre
        n["cout"] = inc["cout"].values
        n["date"] = pd.to_datetime(n["date"])
        n["camion_id"] = [f"NO{i + 1:04d}" for i in range(len(n))]
        return n
    return _memo(ex, "non_opt", fabrique)


def couples_fichier(ex):
    """Tous les couples du fichier depose (y compris ceux dont les lignes ont ete retirees ou ne sont pas optimisees)."""
    brut = getattr(ex, "planning_brut", None)
    cles = set(zip(ex.planning_propre["supplier_id"], ex.planning_propre["plant"]))
    if brut is not None:
        cles |= set(zip(brut["supplier_id"], brut["plant"]))
    return sorted(cles)


def lundis(ex):
    """Les lundis des semaines de besoin couvertes par le planning depose."""
    return [pd.Timestamp(d) for d in sorted(ex.planning_propre["semaine"].unique())]


def semaine_par_defaut(ex):
    """La 2e semaine de besoins (la 1re si le planning n'en couvre qu'une)."""
    return min(1, len(lundis(ex)) - 1)


def statut(ex, cle):
    moteur = ex.moteur
    nb_non = int((_non_opt(ex)[["supplier_id", "plant"]].apply(tuple, axis=1) == cle).sum()) if len(_non_opt(ex)) else 0
    if cle in moteur.COUPLES:
        return STATUT_PART if nb_non else STATUT_OPT
    return STATUT_NON if nb_non else STATUT_VIDE


def contenu_etat(ex, version, etat):
    """Contenu des camions optimises : apres lissage (resultat.contenu) ou avant lissage (meilleur profil de chaque couple)."""
    r = ex.resultats[version]
    if etat == "apres":
        return r.contenu
    return _memo(ex, ("avant", version), lambda: ex.moteur.construire_contenu(r.etape1))


# ---------------------------------------------------------------------------------------------- couts et camions
def cout_actuel_jours(ex):
    """Cout de la situation actuelle par couple et par jour de besoin, sur le perimetre optimise (comme les slides du client).

    Les lignes non optimisees, livrees a l'identique avant et apres, ont leur cout a part (voir `cout_non_optimise`)."""
    def fabrique():
        m = ex.moteur
        lignes = []
        for cle, c in m.COUPLES.items():
            for dt, gg in c["df"].groupby("date"):
                exc = (gg["weight"].values > m.CAP_POIDS) | (gg["volume"].values > m.CAP_VOLUME)
                nn = gg[~exc]
                camions = m.charger_camions_vieux(nn["weight"].values, nn["volume"].values) if len(nn) else []
                cout = sum(m.prix_camion(c["ligne"], w) for w in camions) + int(exc.sum()) * m.prix_exceptionnel(c["ligne"])
                lignes.append((cle[0], cle[1], pd.Timestamp(dt), cout, len(camions) + int(exc.sum())))
        return pd.DataFrame(lignes, columns=["supplier_id", "plant", "date", "cout", "camions"])
    return _memo(ex, "cout_actuel_jours", fabrique)


def camions(ex, version, etat="apres"):
    """Un camion par ligne : (resume, lignes par material). Les lignes non optimisees y figurent, chacune dans son camion."""
    def fabrique():
        m = ex.moteur
        c = contenu_etat(ex, version, etat).copy()
        c["date_livraison"] = pd.to_datetime(c["date_livraison"]); c["date_besoin"] = pd.to_datetime(c["date_besoin"])
        lignes = []
        for cid, g in c.groupby("camion_id", sort=True):
            s, pl = g["supplier_id"].iloc[0], g["plant"].iloc[0]
            exc = bool(g["envoi_exceptionnel"].iloc[0]); poids = float(g["poids"].sum()); vol = float(g["volume"].sum())
            lg = m.COUPLES[(s, pl)]["ligne"]
            prix = m.prix_exceptionnel(lg) if exc else m.prix_camion(lg, poids)
            lignes.append({"camion_id": cid, "type": TYPE_EXC if exc else TYPE_OPT, "supplier_id": s, "plant": pl,
                           "date_livraison": g["date_livraison"].iloc[0], "nb_lignes": len(g), "nb_materials": g["material"].nunique(),
                           "quantite": float(g["quantite"].sum()), "poids": poids, "volume": vol,
                           "remplissage_poids_%": poids / m.CAP_POIDS * 100, "remplissage_volume_%": vol / m.CAP_VOLUME * 100,
                           "livraisons_remplacees": g["date_besoin"].nunique(), "jours_besoin": liste_dates(g["date_besoin"]), "prix": prix})
        det = c[["camion_id", "material", "unloading_point", "date_besoin", "quantite", "poids", "volume"]].copy()
        n = _non_opt(ex)
        for r in n.itertuples():
            lignes.append({"camion_id": r.camion_id, "type": TYPE_NON, "supplier_id": r.supplier_id, "plant": r.plant, "date_livraison": r.date,
                           "nb_lignes": 1, "nb_materials": 1, "quantite": float(r.schedule_quantity),
                           "poids": float(r.weight) if pd.notna(r.weight) else np.nan, "volume": float(r.volume) if pd.notna(r.volume) else np.nan,
                           "remplissage_poids_%": np.nan, "remplissage_volume_%": np.nan, "livraisons_remplacees": 1,
                           "jours_besoin": jj_mm(r.date), "prix": float(r.cout)})
        if len(n):
            det = pd.concat([det, pd.DataFrame({"camion_id": n["camion_id"], "material": n["material"], "unloading_point": n["unloading_point"],
                                                "date_besoin": n["date"], "quantite": n["schedule_quantity"].astype(float),
                                                "poids": n["weight"], "volume": n["volume"]})], ignore_index=True)
        return pd.DataFrame(lignes), det
    return _memo(ex, ("camions", version, etat), fabrique)


def _jour(d):
    return JOURS[pd.Timestamp(d).weekday()]


def sortie2(ex, version):
    """Sortie 2 : (resume par camion, materials par camion)."""
    resume, det = camions(ex, version, "apres")
    resume = resume.copy()
    resume["jour"] = resume["date_livraison"].map(_jour)
    res = resume[["camion_id", "type", "supplier_id", "plant", "date_livraison", "jour", "nb_lignes", "nb_materials", "quantite", "poids", "volume",
                  "remplissage_poids_%", "livraisons_remplacees", "jours_besoin", "prix"]].rename(columns={
        "supplier_id": "fournisseur", "plant": "usine", "nb_lignes": "lignes", "nb_materials": "materials",
        "remplissage_poids_%": "remplissage_%", "livraisons_remplacees": "livraisons_remplacees"})
    res = res.sort_values(["date_livraison", "camion_id"]).reset_index(drop=True)
    res["date_livraison"] = res["date_livraison"].dt.strftime("%d/%m/%Y")
    g = det.groupby(["camion_id", "material", "unloading_point"], sort=True).agg(
        besoins=("date_besoin", lambda s: liste_dates(s)), quantite=("quantite", "sum"), poids=("poids", "sum"), volume=("volume", "sum")).reset_index()
    g = g.rename(columns={"unloading_point": "quai", "besoins": "besoins_regroupes"})
    return res, g


def sortie1(ex, version, lundi=None):
    """Sortie 1 : une ligne par couple du fichier. `lundi` : la semaine choisie (par defaut, la 2e semaine de besoins)."""
    m = ex.moteur; r = ex.resultats[version]
    lundi = pd.Timestamp(lundi) if lundi is not None else lundis(ex)[semaine_par_defaut(ex)]
    p = ex.planning_propre
    nb_sem = p["semaine"].nunique()
    besoins = p.groupby(["supplier_id", "plant"])
    dist = {}
    brut_d = getattr(ex, "distances_brutes", None)
    if brut_d is not None:
        dist = dict(zip(brut_d["supplier_id"], brut_d["distance"]))
    resume, _ = camions(ex, version, "apres")
    resume = resume.assign(lundi=resume["date_livraison"].map(lundi_de))
    n = _non_opt(ex)
    lignes = []
    for cle in couples_fichier(ex):
        s, pl = cle
        g = besoins.get_group(cle) if cle in besoins.groups else None
        jours_besoin = g["date"].drop_duplicates() if g is not None else pd.Series([], dtype="datetime64[ns]")
        liv_sem = int(sum(lundi_de(d) == lundi for d in jours_besoin))
        d = float(g["distance"].iloc[0]) if g is not None and pd.notna(g["distance"].iloc[0]) else dist.get(s, np.nan)
        cam = resume[(resume["supplier_id"] == s) & (resume["plant"] == pl)]
        opt = cam[cam["type"] != TYPE_NON]
        sem = opt[opt["lundi"] == lundi]
        nn = n[(n["supplier_id"] == s) & (n["plant"] == pl)]
        ligne = {"fournisseur": s, "usine": pl, "distance_km": d, "statut": statut(ex, cle),
                 "livraisons_sem_actuelles": liv_sem, "livraisons_sem_moyenne": round(len(jours_besoin) / nb_sem, 2) if nb_sem else 0.0}
        if cle in m.COUPLES:
            b = r.choix[cle]; prof = m.PROFILS[b["idx"]]
            ligne.update({"frequence_cible": (f"{len(prof['jours'])} / semaine" if prof["periode"] == 1 else f"{len(prof['jours'])} / 1 semaine sur {prof['periode']}"),
                          "jours_autorises": ", ".join(JOURS[j] for j in sorted(prof["jours"])), "profil": prof["libelle"]})
        else:
            ligne.update({"frequence_cible": "—", "jours_autorises": "livraison actuelle conservée", "profil": "livraison actuelle conservée"})
        ligne.update({"jours_livres_semaine": ", ".join(f"{_jour(d)[:3]} {jj_mm(d)}" for d in sorted(sem["date_livraison"])),
                      "camions_semaine": len(sem),
                      "remplissage_poids_%": round(float(opt[opt["type"] == TYPE_OPT]["remplissage_poids_%"].mean()), 1) if (opt["type"] == TYPE_OPT).any() else np.nan,
                      "lignes_non_optimisees": len(nn), "dates_non_optimisees": liste_dates(nn["date"]) if len(nn) else ""})
        lignes.append(ligne)
    return pd.DataFrame(lignes)


def sortie3(ex, version, lundi=None):
    """Sortie 3 : cout actuel, cout optimise, economie et %, pour la semaine choisie et sur l'horizon (un camion compte la semaine ou il part)."""
    lundi = pd.Timestamp(lundi) if lundi is not None else lundis(ex)[semaine_par_defaut(ex)]
    act = cout_actuel_jours(ex).assign(lundi=lambda d: d["date"].map(lundi_de))
    resume, _ = camions(ex, version, "apres")
    opt = resume[resume["type"] != TYPE_NON].assign(lundi=lambda d: d["date_livraison"].map(lundi_de))
    non = _non_opt(ex).groupby(["supplier_id", "plant"])["cout"].sum()
    a_h = act.groupby(["supplier_id", "plant"])["cout"].sum()
    a_s = act[act["lundi"] == lundi].groupby(["supplier_id", "plant"])["cout"].sum()
    o_h = opt.groupby(["supplier_id", "plant"])["prix"].sum()
    o_s = opt[opt["lundi"] == lundi].groupby(["supplier_id", "plant"])["prix"].sum()
    lignes = []
    for cle in couples_fichier(ex):
        ah, as_, oh, os_ = (float(x.get(cle, 0.0)) for x in (a_h, a_s, o_h, o_s))
        lignes.append({"fournisseur": cle[0], "usine": cle[1], "cout_actuel_semaine": round(as_, 2), "cout_optimise_semaine": round(os_, 2),
                       "economie_semaine": round(as_ - os_, 2), "economie_semaine_%": round((as_ - os_) / as_ * 100, 1) if as_ > 0 else 0.0,
                       "cout_actuel_horizon": round(ah, 2), "cout_optimise_horizon": round(oh, 2), "economie_horizon": round(ah - oh, 2),
                       "economie_horizon_%": round((ah - oh) / ah * 100, 1) if ah > 0 else 0.0,
                       "cout_non_optimise": round(float(non.get(cle, 0.0)), 2)})
    return pd.DataFrame(lignes)


# ---------------------------------------------------------------------------------------------- un couple
def couple(ex, version, cle):
    """Les chiffres d'un couple : profil, statut, camions optimises, envois non optimises, livraisons d'aujourd'hui, cout avant -> apres."""
    m = ex.moteur; r = ex.resultats[version]
    resume, _ = camions(ex, version, "apres")
    cam = resume[(resume["supplier_id"] == cle[0]) & (resume["plant"] == cle[1])]
    act = cout_actuel_jours(ex)
    act = act[(act["supplier_id"] == cle[0]) & (act["plant"] == cle[1])]
    out = {"cle": cle, "statut": statut(ex, cle), "camions_optimises": int((cam["type"] == TYPE_OPT).sum()),
           "envois_exceptionnels": int((cam["type"] == TYPE_EXC).sum()), "envois_non_optimises": int((cam["type"] == TYPE_NON).sum()),
           "livraisons_aujourdhui": len(act) + int((cam["type"] == TYPE_NON).sum()), "cout_avant": float(act["cout"].sum()),
           "cout_apres": float(cam[cam["type"] != TYPE_NON]["prix"].sum()), "cout_non_optimise": float(cam[cam["type"] == TYPE_NON]["prix"].sum())}
    if cle in m.COUPLES:
        b = r.choix[cle]; prof = m.PROFILS[b["idx"]]
        out.update({"profil": prof["libelle"], "jours_profil": sorted(prof["jours"]), "periode": prof["periode"], "phase": prof["phase"]})
    else:
        out.update({"profil": "livraison actuelle conservée", "jours_profil": [], "periode": 1, "phase": 0})
    return out


def _teinte(i):
    return i % 6


def calendrier_couple(ex, version, cle, etat="apres"):
    """Le calendrier d'un couple, semaine par semaine, pour un etat : 'aujourdhui', 'avant' (avant lissage) ou 'apres' (apres lissage).

    Renvoie {"semaines": [{"lundi", "jours": [{"date", "nom", "ferme", "profil", "camions": [...], "besoins": [...]}]}], "camions": {id: camion}}.
    Un camion : id, type, date, jour, nb_lignes, poids, volume, remplissage_poids, remplissage_volume, prix, besoins (dates), teinte, nb_camions.
    Un besoin : date, nb_lignes, camion (id), parti_le.
    """
    m = ex.moteur; s, pl = cle
    n = _non_opt(ex); nn = n[(n["supplier_id"] == s) & (n["plant"] == pl)]
    trucks, besoins = {}, []              # id -> camion ; liste de (date_besoin, nb_lignes, id)
    if etat == "aujourdhui":
        if cle in m.COUPLES:
            c = m.COUPLES[cle]
            for dt, gg in c["df"].groupby("date"):
                exc = (gg["weight"].values > m.CAP_POIDS) | (gg["volume"].values > m.CAP_VOLUME)
                nor = gg[~exc]
                if len(nor):
                    cams = m.charger_camions_vieux(nor["weight"].values, nor["volume"].values)
                    cid = f"A{pd.Timestamp(dt):%d%m}"
                    trucks[cid] = {"id": cid, "type": TYPE_ACT, "date": pd.Timestamp(dt), "nb_lignes": len(nor), "poids": float(nor["weight"].sum()),
                                   "volume": float(nor["volume"].sum()), "prix": sum(m.prix_camion(c["ligne"], w) for w in cams), "nb_camions": len(cams),
                                   "besoins": [pd.Timestamp(dt)]}
                    besoins.append((pd.Timestamp(dt), len(nor), cid))
                for k, (_, row) in enumerate(gg[exc].iterrows()):
                    cid = f"A{pd.Timestamp(dt):%d%m}x{k + 1}"
                    trucks[cid] = {"id": cid, "type": TYPE_EXC, "date": pd.Timestamp(dt), "nb_lignes": 1, "poids": float(row["weight"]), "volume": float(row["volume"]),
                                   "prix": m.prix_exceptionnel(c["ligne"]), "nb_camions": 1, "besoins": [pd.Timestamp(dt)]}
                    besoins.append((pd.Timestamp(dt), 1, cid))
    else:
        resume, det = camions(ex, version, etat)
        cam = resume[(resume["supplier_id"] == s) & (resume["plant"] == pl) & (resume["type"] != TYPE_NON)]
        c = contenu_etat(ex, version, etat)
        c = c[(c["supplier_id"] == s) & (c["plant"] == pl)].assign(date_besoin=lambda d: pd.to_datetime(d["date_besoin"]))
        for r in cam.itertuples():
            lig = c[c["camion_id"] == r.camion_id]
            trucks[r.camion_id] = {"id": r.camion_id, "type": r.type, "date": r.date_livraison, "nb_lignes": r.nb_lignes, "poids": r.poids, "volume": r.volume,
                                   "prix": r.prix, "nb_camions": 1, "besoins": sorted(lig["date_besoin"].unique())}
        for (db, cid), g in c.groupby(["date_besoin", "camion_id"]):
            besoins.append((pd.Timestamp(db), len(g), cid))
    for r in nn.itertuples():                                          # non optimises : le jour du besoin, comme aujourd'hui
        trucks[r.camion_id] = {"id": r.camion_id, "type": TYPE_NON, "date": r.date, "nb_lignes": 1,
                               "poids": float(r.weight) if pd.notna(r.weight) else np.nan, "volume": float(r.volume) if pd.notna(r.volume) else np.nan,
                               "prix": float(r.cout), "nb_camions": 1, "besoins": [r.date]}
        besoins.append((r.date, 1, r.camion_id))
    for i, cid in enumerate(sorted(trucks, key=lambda k: (trucks[k]["date"], k))):
        t = trucks[cid]; t["teinte"] = _teinte(i); t["jour"] = _jour(t["date"])
        t["remplissage_poids"] = t["poids"] / m.CAP_POIDS * 100 if pd.notna(t["poids"]) else np.nan
        t["remplissage_volume"] = t["volume"] / m.CAP_VOLUME * 100 if pd.notna(t["volume"]) else np.nan
    if etat == "aujourdhui" or cle not in m.COUPLES:
        dates_profil = set()
    else:
        idx = (ex.resultats[version].choix if etat == "apres" else ex.resultats[version].etape1)[cle]["idx"]
        dates_profil = {pd.Timestamp(d) for d in m.DATES_PROFIL[idx]}
    toutes = [t["date"] for t in trucks.values()] + [b[0] for b in besoins] + list(m.jours_ouvres[:1]) + list(m.jours_ouvres[-1:])
    debut, fin = lundi_de(min(toutes)), lundi_de(max(toutes))
    semaines = []
    for lun in pd.date_range(debut, fin, freq="7D"):
        jours = []
        for k in range(5):
            d = lun + pd.Timedelta(k, unit="D")
            jours.append({"date": d, "nom": JOURS[k], "ferme": bool(m.semaine_fermee(d)), "profil": d in dates_profil,
                          "camions": [trucks[i] for i in sorted(trucks) if trucks[i]["date"] == d],
                          "besoins": [{"date": b[0], "nb_lignes": b[1], "camion": b[2], "parti_le": trucks[b[2]]["date"]} for b in sorted(besoins) if b[0] == d]})
        semaines.append({"lundi": lun, "jours": jours})
    return {"semaines": semaines, "camions": trucks, "dates_profil": dates_profil}


def lignes_camion(ex, version, camion_id, etat="apres"):
    """Les lignes d'un camion (material, quai, quantite, poids, volume, date du besoin, avance) pour le panneau d'un camion."""
    if camion_id.startswith("A"):                                    # camion de la situation actuelle : "A" + jour + mois du besoin
        return None
    _, det = camions(ex, version, etat)
    d = det[det["camion_id"] == camion_id].copy()
    livraison = _livraison_camion(ex, version, camion_id, etat)
    d["avance_jours"] = (pd.to_datetime(d["date_besoin"]) - livraison).dt.days if livraison is not None else np.nan
    return d


def _livraison_camion(ex, version, camion_id, etat):
    resume, _ = camions(ex, version, etat)
    r = resume[resume["camion_id"] == camion_id]
    return r["date_livraison"].iloc[0] if len(r) else None


def lignes_jour_actuel(ex, cle, date):
    """Les lignes de besoin d'un couple pour un jour (situation actuelle)."""
    p = ex.planning_propre
    return p[(p["supplier_id"] == cle[0]) & (p["plant"] == cle[1]) & (pd.to_datetime(p["date"]) == pd.Timestamp(date))]


def phrase_deplacement(ex, version, cle):
    """Une ligne si le lissage a change le profil du couple ('profil déplacé du lundi au jeudi, même coût'), sinon ''."""
    r = ex.resultats[version]
    if cle not in r.choix:
        return ""
    avant, apres = r.etape1[cle], r.choix[cle]
    pa, pb = ex.moteur.PROFILS[avant["idx"]], ex.moteur.PROFILS[apres["idx"]]
    if set(pa["jours"]) == set(pb["jours"]) and pa["periode"] == pb["periode"] and pa["phase"] == pb["phase"]:
        return ""
    noms = lambda p: " et ".join(JOURS[j] for j in sorted(p["jours"]))
    dc = apres["cout"] - avant["cout"]
    cout = "même coût" if abs(dc) < 0.005 else f"{dc:+,.2f} €".replace(",", " ").replace(".", ",")
    return f"profil déplacé : {noms(pa)} → {noms(pb)}, {cout}"


# ---------------------------------------------------------------------------------------------- lissage
def repartition_jours(ex, version):
    """Nombre de livraisons par usine, par jour de la semaine et par etat. Colonnes : plant, etat, jour (0 = lundi), n.

    Une livraison = un couple livre un jour donne (les lignes non optimisees comptent, a l'identique, dans les trois etats).
    """
    def fabrique():
        n = _non_opt(ex)
        non = n[["supplier_id", "plant", "date"]].drop_duplicates() if len(n) else pd.DataFrame(columns=["supplier_id", "plant", "date"])
        sources = {"aujourdhui": ex.planning_propre[["supplier_id", "plant", "date"]].drop_duplicates()}
        for etat in ("avant", "apres"):
            c = contenu_etat(ex, version, etat)[["supplier_id", "plant", "date_livraison"]].rename(columns={"date_livraison": "date"})
            sources[etat] = pd.concat([c, non]).drop_duplicates()
        lignes = []
        for etat, d in sources.items():
            d = d.assign(jour=pd.to_datetime(d["date"]).dt.weekday)
            for (pl, j), nb in d.groupby(["plant", "jour"]).size().items():
                lignes.append({"plant": pl, "etat": etat, "jour": int(j), "n": int(nb)})
        return pd.DataFrame(lignes)
    return _memo(ex, ("repartition", version), fabrique)


def couples_deplaces(ex, version):
    """Les couples dont le lissage a change le profil."""
    r = ex.resultats[version]
    return [cle for cle in r.choix if phrase_deplacement(ex, version, cle)]


# ---------------------------------------------------------------------------------------------- controles
def _res(nom, cas):
    """Un controle : OK si le tableau des cas en defaut est vide."""
    return {"nom": nom, "ok": len(cas) == 0, "nb": len(cas), "cas": cas}


def verifier(ex, version):
    """Controles calcules sur le resultat du fichier depose. Liste de {nom, ok, nb (cas en defaut), cas (tableau)}."""
    return _memo(ex, ("verifier", version), lambda: _verifier(ex, version))


def _verifier(ex, version):
    m = ex.moteur; r = ex.resultats[version]
    p = ex.planning_propre.copy(); p["date"] = pd.to_datetime(p["date"])
    opt = p[p["statut"] == "optimise"]
    nonopt = _non_opt(ex)
    c = r.contenu.copy(); c["date_livraison"] = pd.to_datetime(c["date_livraison"]); c["date_besoin"] = pd.to_datetime(c["date_besoin"])
    cle = ["supplier_id", "plant", "material", "unloading_point", "date_besoin"]
    res = []
    # 1. chaque ligne du planning est dans un camion, ou dans les lignes non optimisees
    a = opt.rename(columns={"date": "date_besoin"})[cle[:-1] + ["date_besoin"]].assign(n_planning=1).groupby(cle, as_index=False).sum()
    b = c[cle].assign(n_camions=1).groupby(cle, as_index=False).sum()
    mm = a.merge(b, on=cle, how="outer").fillna(0)
    res.append(_res("Chaque ligne du planning est dans un camion (une seule fois)", mm[mm["n_planning"] != mm["n_camions"]]))
    n_total, n_camion, n_non = len(p), len(c), len(nonopt)
    res.append(_res("Lignes du planning = lignes en camion + lignes non optimisées",
                    pd.DataFrame([{"planning": n_total, "en camion": n_camion, "non optimisées": n_non}]) if n_total != n_camion + n_non else pd.DataFrame()))
    q_plan = p.groupby("material")["schedule_quantity"].sum()
    q_liv = c.groupby("material")["quantite"].sum().add(nonopt.groupby("material")["schedule_quantity"].sum(), fill_value=0)
    ecart = pd.concat([q_plan.rename("planning"), q_liv.rename("livré")], axis=1).fillna(0)
    res.append(_res("Par material : quantité du planning = quantité livrée", ecart[~np.isclose(ecart["planning"], ecart["livré"], atol=0.01)].reset_index()))
    l_plan = p.groupby(["supplier_id", "plant"]).size()
    l_liv = c.groupby(["supplier_id", "plant"]).size().add(nonopt.groupby(["supplier_id", "plant"]).size(), fill_value=0)
    ecart = pd.concat([l_plan.rename("planning"), l_liv.rename("livré")], axis=1).fillna(0)
    res.append(_res("Par couple : lignes du planning = lignes livrées", ecart[ecart["planning"] != ecart["livré"]].reset_index()))
    # 2. retard, avance
    c["avance_calc"] = (c["date_besoin"] - c["date_livraison"]).dt.days
    cols = ["camion_id", "supplier_id", "plant", "date_livraison", "date_besoin", "avance_calc"]
    res.append(_res("Aucun retard de livraison", c[c["avance_calc"] < 0][cols]))
    res.append(_res(f"Aucune avance de plus de {config.AVANCE_MAX} jours", c[c["avance_calc"] > config.AVANCE_MAX][cols]))
    # 3. capacite, un couple par camion
    pc = c.groupby("camion_id").agg(poids=("poids", "sum"), volume=("volume", "sum"), fournisseurs=("supplier_id", "nunique"),
                                    usines=("plant", "nunique"), exc=("envoi_exceptionnel", "max")).reset_index()
    nor = pc[~pc["exc"].astype(bool)]
    res.append(_res("Aucun camion au-dessus de la capacité (poids et volume)",
                    nor[(nor["poids"] > config.CAP_POIDS + 1e-3) | (nor["volume"] > config.CAP_VOLUME + 1e-3)]))
    res.append(_res("Un seul couple fournisseur × usine par camion", pc[(pc["fournisseurs"] != 1) | (pc["usines"] != 1)]))
    # 4. jour autorise par le profil
    hors = []
    for (s, pl, cid), g in c.groupby(["supplier_id", "plant", "camion_id"]):
        if (s, pl) in r.choix:
            autorises = {pd.Timestamp(d) for d in m.DATES_PROFIL[r.choix[(s, pl)]["idx"]]}
            if g["date_livraison"].iloc[0] not in autorises:
                hors.append({"camion_id": cid, "supplier_id": s, "plant": pl, "date_livraison": g["date_livraison"].iloc[0]})
    res.append(_res("Chaque camion optimisé part un jour autorisé par le profil de son couple", pd.DataFrame(hors)))
    # 5. coherence des sorties
    s1, (s2, _), s3 = sortie1(ex, version), sortie2(ex, version), sortie3(ex, version)
    attendu = len(couples_fichier(ex))
    res.append(_res("Sortie 1 : tous les couples du fichier", pd.DataFrame([{"sortie 1": len(s1), "couples du fichier": attendu}]) if len(s1) != attendu else pd.DataFrame()))
    p2, pp = float(c["poids"].sum()), float(opt["weight"].sum())
    res.append(_res("Sortie 2 : poids des camions = poids du planning optimisé",
                    pd.DataFrame([{"sortie 2 (kg)": p2, "planning (kg)": pp}]) if abs(p2 - pp) > 0.5 else pd.DataFrame()))
    attendus = {"coût actuel": ex.baselines["baseline_h20"], "coût optimisé": r.cout}
    obtenus = {"coût actuel": float(s3["cout_actuel_horizon"].sum()), "coût optimisé": float(s3["cout_optimise_horizon"].sum())}
    ecarts = [{"indicateur": k, "sortie 3": round(obtenus[k], 2), "global": round(attendus[k], 2)} for k in attendus if abs(obtenus[k] - attendus[k]) > 0.5]
    res.append(_res("Sortie 3 : somme des coûts = coûts globaux (périmètre optimisé)", pd.DataFrame(ecarts)))
    return res
