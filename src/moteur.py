"""Moteur de consolidation des livraisons (milestone 3).

Pour chaque couple fournisseur x usine, le moteur :
  1. evalue chacun des 166 profils de livraison par programmation dynamique exacte (le meilleur choix des jours utiles) ;
  2. garde le profil le moins cher ;
  3. lisse la charge de chaque usine dans la semaine parmi les profils presque aussi bons (R4) ;
  4. reconstruit le contenu de chaque camion, puis valide la solution.

Trois versions existent (hypothese H21) :
  - "strict"        : tous les jours du profil sont retenus, chaque semaine. C'est la version recommandee par defaut :
                      un profil propose est un engagement envers le fournisseur ;
  - "intermediaire" : au moins MIN_SEMAINES_RESPECTEES semaines du profil sont respectees ;
  - "libre"         : le profil est un maximum, le moteur retient les jours utiles au moins cher (comparaison).

Le calendrier de livraison commence 7 jours avant le premier besoin (R1) : un besoin du lundi 09/11 peut partir des le
lundi 02/11. Cette premiere semaine compte comme une semaine du profil (comme dans le notebook du milestone 3).

Le code des methodes reprend, sans changement de calcul, celui du notebook notebooks/milestone3.ipynb ;
les variables globales du notebook sont devenues des attributs (`self.AVANCE_MAX`, `self.COUPLES`...).
"""
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd

from .config import PARAMETRES_MOTEUR, VERSIONS
from .tarifs import ligne_texte


class ValidationEchouee(ValueError):
    """La solution calculee viole une regle : le moteur refuse de la publier."""


@dataclass
class Resultat:
    """Ce que renvoie `Moteur.lancer` pour une version."""
    mode: str
    choix: dict            # (fournisseur, usine) -> profil retenu apres lissage
    cout: float            # cout total apres lissage
    etape1: dict           # meilleur profil de chaque couple, avant lissage
    contenu: pd.DataFrame  # sortie 2 : une ligne par ligne de besoin, avec son camion
    temps: dict = field(default_factory=dict)
    total: float = 0.0     # temps total (secondes)
    controles: list = field(default_factory=list)   # [(nom du controle, ok)]


def en_jours(serie):
    """Dates -> nombre de jours (entiers), pour comparer avec les dates du profil."""
    return pd.to_datetime(serie).values.astype("datetime64[D]").astype(int)


def semaine_de(d):
    dt = pd.Timestamp(d); return (dt - pd.Timedelta(dt.weekday(), "D")).date()


class Moteur:
    """Moteur de consolidation. S'initialise avec le planning propre et la grille de prix ; `lancer()` calcule une version."""

    def __init__(self, planning, grille, parametres=None):
        """planning : planning propre (sortie de preparation.preparer_donnees) ; grille : prix finaux (lignes = km, colonnes = kg)."""
        p = {**PARAMETRES_MOTEUR, **(parametres or {})}
        if p["MODE_PROFIL"] not in VERSIONS:
            raise ValueError(f"MODE_PROFIL doit valoir l'une de {VERSIONS}, pas {p['MODE_PROFIL']!r}.")
        for nom, valeur in p.items():              # AVANCE_MAX, CAP_POIDS, MODE_PROFIL...
            setattr(self, nom, valeur)
        self.grille = grille.copy()
        self.grille.columns = self.grille.columns.astype(str)
        self.grille.index = self.grille.index.astype(str)
        # Precalcul des prix : np.searchsorted trouve la tranche de poids en un seul appel (le moteur reste rapide).
        self.BORNES = np.array(self.TRANCHES_KG, dtype=float)
        self.PRIX_LIGNE = {lg: self.grille.loc[lg].values.astype(float) for lg in self.grille.index}

        # Notre perimetre : les lignes optimisables (H15). ligne_grille en texte entier.
        self.planning = planning
        self.opt = planning[planning["statut"] == "optimise"].copy()
        self.opt["ligne_grille"] = self.opt["ligne_grille"].apply(ligne_texte)

        # Profils et calendrier (jours ouvres de l'horizon, hors semaines fermees H7)
        self.PROFILS = self.generer_profils()
        premier_besoin = self.opt["date"].min()
        self.d1 = self.opt["date"].max()
        # Premier jour de livraison possible : la regle des 7 jours vaut aussi au debut de l'horizon, donc un besoin du
        # lundi 09/11 peut partir des le lundi 02/11. Par defaut : premier besoin - AVANCE_MAX ; reglable avec PREMIER_JOUR_LIVRAISON.
        if self.PREMIER_JOUR_LIVRAISON is None:
            self.d0 = premier_besoin - pd.Timedelta(self.AVANCE_MAX, unit="D")
        else:
            self.d0 = pd.Timestamp(self.PREMIER_JOUR_LIVRAISON)
        while self.d0.weekday() >= 5:                 # un jour de livraison est un jour ouvre (lundi a vendredi)
            self.d0 -= pd.Timedelta(1, unit="D")
        self.lundi0 = self.d0 - pd.Timedelta(int(self.d0.weekday()), unit="D")   # lundi de la premiere semaine du calendrier
        self.fermees = set(pd.to_datetime(self.SEMAINES_FERMEES))
        self.jours_ouvres = pd.DatetimeIndex([d for d in pd.date_range(self.d0, self.d1, freq="D")
                                              if d.weekday() < 5 and not self.semaine_fermee(d)])
        self.DATES_PROFIL = [self.dates_profil(p) for p in self.PROFILS]
        self.SEM_PROFIL = [self.semaines_du_profil(d) for d in self.DATES_PROFIL]
        self.IDX_TOUS = list(range(len(self.PROFILS)))

        # Les couples : besoins normaux tries par date, lignes exceptionnelles a part (H20)
        self.COUPLES = {}
        for (s, pl), g in self.opt.groupby(["supplier_id", "plant"]):
            g = g.sort_values("date")
            exc = (g["weight"].values > self.CAP_POIDS) | (g["volume"].values > self.CAP_VOLUME)
            normal = g[~exc]; excep = g[exc]
            self.COUPLES[(s, pl)] = {
                "besoins": normal["date"].values.astype("datetime64[D]"),
                "poids": normal["weight"].values.astype(float),
                "volume": normal["volume"].values.astype(float),
                "mat": normal["material"].values, "up": normal["unloading_point"].values,
                "qte": normal["schedule_quantity"].values.astype(float),
                "ligne": g["ligne_grille"].iloc[0], "distance": g["distance"].iloc[0],
                "exc_dates": excep["date"].values.astype("datetime64[D]"),
                "exc_poids": excep["weight"].values.astype(float),
                "exc_vol": excep["volume"].values.astype(float), "exc_mat": excep["material"].values,
                "exc_up": excep["unloading_point"].values, "exc_qte": excep["schedule_quantity"].values.astype(float),
                "df": g}

        # Couples dont un meme jour de besoin depasse un camion : la DP ne s'applique pas (voir ci-dessous).
        jour_sum = self.opt.groupby(["supplier_id", "plant", "date"]).agg(w=("weight", "sum"), v=("volume", "sum")).reset_index()
        jours_lourds = jour_sum[(jour_sum.w > self.CAP_POIDS) | (jour_sum.v > self.CAP_VOLUME)]
        self.COUPLES_CAP = set(zip(jours_lourds.supplier_id, jours_lourds.plant))

    # ----------------------------------------------------------------------
    # Tarifs : le prix d'un camion
    # ----------------------------------------------------------------------

    def tranche_poids(self, kg):
        """Colonne de la grille : la tranche de poids juste au-dessus (au-dela de 4000 -> '>4000')."""
        for t in self.TRANCHES_KG:
            if kg <= t:
                return str(t)
        return ">4000"

    def prix_camion(self, ligne_grille, poids_kg):
        """Prix d'un camion : case (ligne = distance, colonne = tranche de poids), via searchsorted.
        side='left' reproduit self.tranche_poids : un poids pile sur une borne reste dans sa tranche."""
        col = int(np.searchsorted(self.BORNES, poids_kg, side="left"))   # 0..14 (14 = '>4000')
        return float(self.PRIX_LIGNE[str(ligne_grille)][col])

    def prix_exceptionnel(self, ligne_grille):
        """Prix d'un envoi exceptionnel : tarif '>4000' de la ligne de grille (H20)."""
        return float(self.PRIX_LIGNE[str(ligne_grille)][-1])

    # ----------------------------------------------------------------------
    # Profils de livraison et calendrier
    # ----------------------------------------------------------------------

    def libelle_profil(self, p):
        """Libelle lisible d'un profil (ex. '2 / semaine : lundi, jeudi')."""
        noms = ", ".join(self.JOURS[j] for j in sorted(p["jours"]))
        if p["periode"] == 1:
            return f"{len(p['jours'])} / semaine : {noms}"
        return f"1 semaine sur {p['periode']} (semaine {p['phase'] + 1}) : {noms}"

    def sous_ensembles(self, jours, tailles):
        """Toutes les combinaisons de jours des tailles demandees."""
        return [frozenset(c) for k in tailles for c in combinations(jours, k)]

    def generer_profils(self):
        """Construit la liste des profils candidats (periodes 1 a 4, H18)."""
        profils = []
        for d in self.sous_ensembles([0, 1, 2, 3, 4], range(1, 6)):          # periode 1 : 31 profils
            profils.append({"periode": 1, "phase": 0, "jours": d})
        for periode in (2, 3, 4):                                        # periodes 2,3,4 : 1 ou 2 jours
            for phase in range(periode):
                for d in self.sous_ensembles([0, 1, 2, 3, 4], [1, 2]):
                    profils.append({"periode": periode, "phase": phase, "jours": d})
        for p in profils:
            p["libelle"] = self.libelle_profil(p)
            p["type"] = "PDF" if (p["periode"] == 1 and len(p["jours"]) in (1, 2, 3, 5)) else "elargi"
        return profils

    def semaine_fermee(self, dt):
        """Vrai si la date tombe dans une semaine fermee (H7)."""
        return (dt - pd.Timedelta(int(dt.weekday()), unit="D")) in self.fermees

    def dates_profil(self, p):
        """Les dates de livraison d'un profil sur l'horizon (semaine du cycle modulo la periode)."""
        out = []
        for d in self.jours_ouvres:
            if d.weekday() in p["jours"]:
                semaine = ((d - pd.Timedelta(int(d.weekday()), unit="D")) - self.lundi0).days // 7
                if semaine % p["periode"] == p["phase"]:
                    out.append(d)
        return np.array(out, dtype="datetime64[D]")

    # ----------------------------------------------------------------------
    # Evaluation d'un profil pour un couple : programmation dynamique (version libre)
    # ----------------------------------------------------------------------

    def cout_exceptionnels(self, couple, dates):
        """Cout et nombre des envois exceptionnels d'un couple pour un profil ; None si un sans jour (R1)."""
        cout = 0.0; nb = 0
        for bd in couple["exc_dates"]:
            pos = int(np.searchsorted(dates, bd, side="right")) - 1
            if pos < 0:
                return None
            if int((bd - dates[pos]).astype("timedelta64[D]").astype(int)) > self.AVANCE_MAX:
                return None
            cout += self.prix_exceptionnel(couple["ligne"]); nb += 1
        return cout, nb

    def evaluer_dp(self, couple, idx_profil):
        """Programmation dynamique : meilleur cout pour 'chaque ligne part au dernier jour retenu <= son besoin'."""
        dates = self.DATES_PROFIL[idx_profil]
        if len(dates) == 0:
            return None
        ce = self.cout_exceptionnels(couple, dates)
        if ce is None:
            return None
        cout_exc, nb_exc = ce
        besoins = couple["besoins"]; poids = couple["poids"]; volume = couple["volume"]; ligne = couple["ligne"]
        if len(besoins) == 0:
            return {"cout": cout_exc, "camions": nb_exc, "livraisons": 0,
                    "jours": np.array([], dtype="datetime64[D]"), "idx": idx_profil, "exc": nb_exc}
        ordre = np.argsort(besoins); poids = poids[ordre]; volume = volume[ordre]
        bjours = besoins[ordre].astype("datetime64[D]").astype(int)
        djours = dates.astype("datetime64[D]").astype(int)
        m = len(dates); INF = float("inf")
        cout = [INF] * m; prev = [-1] * m
        for j in range(m):                                   # premier jour retenu valable : aucun besoin avant lui
            if int(np.searchsorted(bjours, djours[j], side="left")) == 0:
                cout[j] = 0.0; prev[j] = -1
            else:
                break
        for i in range(m):
            if cout[i] == INF:
                continue
            k = int(np.searchsorted(bjours, djours[i], side="left"))   # premier besoin >= dates[i]
            cw = 0.0; cv = 0.0; maxneed = -1
            for j in range(i + 1, m):
                while k < len(bjours) and bjours[k] < djours[j]:        # besoins dans [dates[i], dates[j])
                    cw += poids[k]; cv += volume[k]; maxneed = bjours[k]; k += 1
                if maxneed >= 0:
                    if maxneed - djours[i] > self.AVANCE_MAX:               # R1 : un besoin trop ancien -> stop
                        break
                    if cw > self.CAP_POIDS + 1e-6 or cv > self.CAP_VOLUME + 1e-6:  # capacite (H19)
                        break
                c = self.prix_camion(ligne, cw) if cw > 1e-9 else 0.0
                if cout[i] + c < cout[j]:
                    cout[j] = cout[i] + c; prev[j] = i
        best = INF; best_i = -1                               # fin : le camion sur i porte les besoins >= dates[i]
        for i in range(m):
            if cout[i] == INF:
                continue
            lo = int(np.searchsorted(bjours, djours[i], side="left"))
            if lo < len(bjours):
                if bjours[-1] - djours[i] > self.AVANCE_MAX:
                    continue
                cw = float(poids[lo:].sum()); cv = float(volume[lo:].sum())
                if cw > self.CAP_POIDS + 1e-6 or cv > self.CAP_VOLUME + 1e-6:
                    continue
                c = self.prix_camion(ligne, cw)
            else:
                c = 0.0
            if cout[i] + c < best:
                best = cout[i] + c; best_i = i
        if best == INF:
            return None
        retenus = []; i = best_i
        while i >= 0:
            retenus.append(i); i = prev[i]
        retenus = sorted(retenus)
        jours_liv = []
        for a in range(len(retenus)):
            lo = int(np.searchsorted(bjours, djours[retenus[a]], side="left"))
            dj = djours[retenus[a + 1]] if a + 1 < len(retenus) else 10**9
            hi = int(np.searchsorted(bjours, dj, side="left"))
            if hi > lo:                                       # jour non vide = une vraie livraison
                jours_liv.append(dates[retenus[a]])
        return {"cout": best + cout_exc, "camions": len(jours_liv) + nb_exc, "livraisons": len(jours_liv),
                "jours": np.array(jours_liv, dtype="datetime64[D]"), "idx": idx_profil, "exc": nb_exc}

    # ----------------------------------------------------------------------
    # Version intermediaire : semaines du profil respectees
    # ----------------------------------------------------------------------

    def semaines_du_profil(self, dates):
        """Pour chaque date du profil : le numero de sa semaine (0, 1, 2...) parmi les semaines du profil."""
        if len(dates) == 0:
            return np.array([], dtype=int)
        j = dates.astype("datetime64[D]").astype(int)
        lundis = j - ((j + 3) % 7)                 # le 01/01/1970 est un jeudi : (j + 3) % 7 = 0 le lundi
        return np.unique(lundis, return_inverse=True)[1]

    def objectif_semaines(self, idx_profil):
        """(semaines a respecter, semaines du profil) : MIN_SEMAINES_RESPECTEES, ou toutes s'il y en a moins."""
        nb = int(self.SEM_PROFIL[idx_profil].max()) + 1 if len(self.SEM_PROFIL[idx_profil]) else 0
        return min(self.MIN_SEMAINES_RESPECTEES, nb), nb

    def semaines_ok(self, idx_profil, liv, besoin):
        """Pour chaque semaine du profil : vrai si elle est respectee, lu sur les livraisons. liv et besoin donnent,
        pour chaque ligne normale, son jour de livraison et son jour de besoin. Un jour du profil compte comme retenu
        s'il est livre, ou si aucune ligne ne le saute (livree avant lui alors que son besoin tombe ce jour-la ou
        apres) : il n'y avait alors rien a y livrer. Une semaine est respectee si tous ses jours du profil sont retenus."""
        dates = self.DATES_PROFIL[idx_profil].astype("datetime64[D]").astype(int); sem = self.SEM_PROFIL[idx_profil]
        if len(dates) == 0:
            return np.array([], dtype=bool)
        liv = np.asarray(liv, dtype=int); besoin = np.asarray(besoin, dtype=int)
        livre = np.isin(dates, liv)
        if len(liv):
            saute = ((liv[:, None] < dates[None, :]) & (besoin[:, None] >= dates[None, :])).any(axis=0)
        else:
            saute = np.zeros(len(dates), dtype=bool)
        retenu = livre | ~saute
        jours_manques = np.bincount(sem, weights=(~retenu).astype(float), minlength=int(sem.max()) + 1)
        return jours_manques == 0

    def semaines_respectees(self, idx_profil, liv, besoin):
        """(semaines respectees, semaines du profil)."""
        ok = self.semaines_ok(idx_profil, liv, besoin)
        return int(ok.sum()), len(ok)

    def lignes_dp(self, couple, jours):
        """Pour une solution de la DP : jour de livraison (dernier jour livre <= besoin) et jour de besoin de chaque ligne."""
        bj = couple["besoins"].astype("datetime64[D]").astype(int)
        jj = np.sort(np.asarray(jours).astype("datetime64[D]").astype(int))
        if len(bj) == 0:
            return bj, bj
        return jj[np.searchsorted(jj, bj, side="right") - 1], bj

    def evaluer_dp_inter(self, couple, idx_profil):
        """DP de la version 'intermediaire'. Etat = (jour retenu, semaines respectees jusqu'ici plafonnees a
        l'objectif, semaine en cours encore respectee ou non). Seules les fins qui atteignent l'objectif comptent."""
        dates = self.DATES_PROFIL[idx_profil]
        if len(dates) == 0:
            return None
        ce = self.cout_exceptionnels(couple, dates)
        if ce is None:
            return None
        cout_exc, nb_exc = ce
        besoins = couple["besoins"]; poids = couple["poids"]; volume = couple["volume"]; ligne = couple["ligne"]
        if len(besoins) == 0:
            return {"cout": cout_exc, "camions": nb_exc, "livraisons": 0,
                    "jours": np.array([], dtype="datetime64[D]"), "idx": idx_profil, "exc": nb_exc}
        K = self.objectif_semaines(idx_profil)[0]
        sem = self.SEM_PROFIL[idx_profil]; m = len(dates)
        premier = np.r_[True, sem[1:] != sem[:-1]]          # premier jour du profil dans sa semaine
        dernier = np.r_[sem[1:] != sem[:-1], True]          # dernier jour du profil dans sa semaine
        ordre = np.argsort(besoins); poids = poids[ordre]; volume = volume[ordre]
        bjours = besoins[ordre].astype("datetime64[D]").astype(int)
        djours = dates.astype("datetime64[D]").astype(int)
        NS = 2 * (K + 1)                                     # etat s = 2 x semaines respectees + semaine en cours ok
        INF = float("inf")
        cout = [[INF] * NS for _ in range(m)]; prev = [[None] * NS for _ in range(m)]
        for j in range(m):                                   # premier jour retenu : les jours avant lui sont sautes
            if int(np.searchsorted(bjours, djours[j], side="left")) == 0:
                cout[j][1 if premier[j] else 0] = 0.0
            else:
                break
        for i in range(m):
            etats = [(s, cout[i][s]) for s in range(NS) if cout[i][s] < INF]
            if not etats:
                continue
            k = int(np.searchsorted(bjours, djours[i], side="left"))
            cw = 0.0; cv = 0.0; maxneed = -1
            for j in range(i + 1, m):
                while k < len(bjours) and bjours[k] < djours[j]:
                    cw += poids[k]; cv += volume[k]; maxneed = bjours[k]; k += 1
                if maxneed >= 0:
                    if maxneed - djours[i] > self.AVANCE_MAX:               # R1
                        break
                    if cw > self.CAP_POIDS + 1e-6 or cv > self.CAP_VOLUME + 1e-6:  # capacite (H19)
                        break
                c = self.prix_camion(ligne, cw) if cw > 1e-9 else 0.0
                for s, val in etats:
                    nbs, en_cours = divmod(s, 2)
                    if sem[j] == sem[i]:                     # meme semaine : un jour saute entre i et j la casse
                        s2 = 2 * nbs + (en_cours if j == i + 1 else 0)
                    else:                                    # la semaine de i se ferme ; les semaines entre i et j sont sautees
                        fermee_ok = 1 if (en_cours and dernier[i]) else 0
                        s2 = 2 * min(K, nbs + fermee_ok) + (1 if premier[j] else 0)
                    if val + c < cout[j][s2]:
                        cout[j][s2] = val + c; prev[j][s2] = (i, s)
        best = INF; best_etat = None                         # fin : le camion sur i porte les besoins >= dates[i]
        for i in range(m):
            lo = int(np.searchsorted(bjours, djours[i], side="left"))
            if lo < len(bjours):
                if bjours[-1] - djours[i] > self.AVANCE_MAX:
                    continue
                cw = float(poids[lo:].sum()); cv = float(volume[lo:].sum())
                if cw > self.CAP_POIDS + 1e-6 or cv > self.CAP_VOLUME + 1e-6:
                    continue
                c = self.prix_camion(ligne, cw)
            else:
                c = 0.0
            for s in range(NS):
                if cout[i][s] == INF:
                    continue
                nbs, en_cours = divmod(s, 2)
                if min(K, nbs + (1 if (en_cours and dernier[i]) else 0)) < K:   # objectif non atteint
                    continue
                if cout[i][s] + c < best:
                    best = cout[i][s] + c; best_etat = (i, s)
        if best == INF:
            return None
        retenus = []; e = best_etat
        while e is not None:
            retenus.append(e[0]); e = prev[e[0]][e[1]]
        retenus = sorted(retenus)
        jours_liv = []
        for a in range(len(retenus)):
            lo = int(np.searchsorted(bjours, djours[retenus[a]], side="left"))
            dj = djours[retenus[a + 1]] if a + 1 < len(retenus) else 10**9
            hi = int(np.searchsorted(bjours, dj, side="left"))
            if hi > lo:                                      # jour retenu non vide = une vraie livraison
                jours_liv.append(dates[retenus[a]])
        return {"cout": best + cout_exc, "camions": len(jours_liv) + nb_exc, "livraisons": len(jours_liv),
                "jours": np.array(jours_liv, dtype="datetime64[D]"), "idx": idx_profil, "exc": nb_exc}

    # ----------------------------------------------------------------------
    # Couples aux jours trop lourds (methode approchee), version stricte, ancien comportement
    # ----------------------------------------------------------------------

    def evaluer_cap(self, couple, idx_profil):
        """Affectation avec capacite (glouton) pour un couple dont un jour depasse un camion :
        chaque ligne au jour du profil le plus tardif <= son besoin ou il reste de la place (tous les jours du profil)."""
        dates = self.DATES_PROFIL[idx_profil]
        if len(dates) == 0:
            return None
        ce = self.cout_exceptionnels(couple, dates)
        if ce is None:
            return None
        cout_exc, nb_exc = ce
        besoins = couple["besoins"]; poids = couple["poids"]; volume = couple["volume"]
        if len(besoins) == 0:
            return {"cout": cout_exc, "camions": nb_exc, "livraisons": 0, "affect": {},
                    "jours": np.array([], dtype="datetime64[D]"), "idx": idx_profil, "exc": nb_exc}
        djours = dates.astype("datetime64[D]").astype(int)
        bjours = besoins.astype("datetime64[D]").astype(int)
        ordre = sorted(range(len(besoins)), key=lambda i: (bjours[i], -poids[i]))   # date croissante, plus lourd d'abord
        charge_p = defaultdict(float); charge_v = defaultdict(float); affect = defaultdict(list)
        for i in ordre:
            cand = [k for k in range(len(dates)) if djours[k] <= bjours[i] and bjours[i] - djours[k] <= self.AVANCE_MAX]
            cand.sort(key=lambda k: -djours[k])                 # jour le plus tardif d'abord
            place = False
            for k in cand:
                if charge_p[k] + poids[i] <= self.CAP_POIDS + 1e-6 and charge_v[k] + volume[i] <= self.CAP_VOLUME + 1e-6:
                    charge_p[k] += poids[i]; charge_v[k] += volume[i]; affect[k].append(i); place = True; break
            if not place:
                return None
        return self.resultat_cap(couple, idx_profil, dict(affect), cout_exc, nb_exc)

    def resultat_cap(self, couple, idx_profil, affect, cout_exc, nb_exc):
        """Resultat d'une affectation ligne -> jour : un camion par jour qui porte au moins une ligne."""
        dates = self.DATES_PROFIL[idx_profil]; cout = 0.0; jours_liv = []
        for k in sorted(affect):
            if affect[k]:
                cout += self.prix_camion(couple["ligne"], couple["poids"][affect[k]].sum()); jours_liv.append(dates[k])
        return {"cout": cout + cout_exc, "camions": len(jours_liv) + nb_exc, "livraisons": len(jours_liv),
                "affect": {k: v for k, v in affect.items() if v},
                "jours": np.array(jours_liv, dtype="datetime64[D]"), "idx": idx_profil, "exc": nb_exc}

    def respectees_cap(self, couple, idx_profil, affect):
        """Semaines respectees d'une affectation ligne -> jour (meme regle que la validation)."""
        dj = self.DATES_PROFIL[idx_profil].astype("datetime64[D]").astype(int)
        bj = couple["besoins"].astype("datetime64[D]").astype(int)
        liv = [dj[k] for k, v in affect.items() for i in v]; bes = [bj[i] for k, v in affect.items() for i in v]
        return self.semaines_respectees(idx_profil, liv, bes)[0]

    def evaluer_cap_mode(self, couple, idx_profil, mode):
        """3 couples aux jours trop lourds (methode APPROCHEE). Placement glouton sur tous les jours du profil ;
        en 'libre' et 'intermediaire', nous supprimons ensuite une livraison si toutes ses lignes tiennent sur un
        jour livre precedent (7 jours au plus, capacite respectee) et si le cout baisse, sans passer sous l'objectif
        de semaines respectees en 'intermediaire'. Nous recommencons tant que le cout baisse."""
        r = self.evaluer_cap(couple, idx_profil)
        if r is None or mode == "strict" or not r["affect"]:
            return r
        K = self.objectif_semaines(idx_profil)[0] if mode == "intermediaire" else 0
        dj = self.DATES_PROFIL[idx_profil].astype("datetime64[D]").astype(int)
        bj = couple["besoins"].astype("datetime64[D]").astype(int)
        poids = couple["poids"]; volume = couple["volume"]; ligne = couple["ligne"]
        affect = {k: list(v) for k, v in r["affect"].items()}
        cp = {k: float(poids[v].sum()) for k, v in affect.items()}; cv = {k: float(volume[v].sum()) for k, v in affect.items()}
        while True:
            meilleur_gain = 1e-9; meilleur_mvt = None
            for d in affect:                                   # jour livre que nous essayons de supprimer
                for d2 in affect:                              # jour livre precedent qui recoit ses lignes
                    if d2 >= d:
                        continue
                    if cp[d2] + cp[d] > self.CAP_POIDS + 1e-6 or cv[d2] + cv[d] > self.CAP_VOLUME + 1e-6:
                        continue
                    if max(bj[i] for i in affect[d]) - dj[d2] > self.AVANCE_MAX:      # R1
                        continue
                    gain = self.prix_camion(ligne, cp[d]) + self.prix_camion(ligne, cp[d2]) - self.prix_camion(ligne, cp[d] + cp[d2])
                    if gain <= meilleur_gain:
                        continue
                    if K:
                        essai = {k: v for k, v in affect.items() if k != d}; essai[d2] = affect[d2] + affect[d]
                        if self.respectees_cap(couple, idx_profil, essai) < K:
                            continue
                    meilleur_gain = gain; meilleur_mvt = (d, d2)
            if meilleur_mvt is None:
                break
            d, d2 = meilleur_mvt
            affect[d2] = affect[d2] + affect.pop(d); cp[d2] += cp.pop(d); cv[d2] += cv.pop(d)
        cout_exc, nb_exc = self.cout_exceptionnels(couple, self.DATES_PROFIL[idx_profil])
        return self.resultat_cap(couple, idx_profil, affect, cout_exc, nb_exc)

    def evaluer_strict(self, couple, idx_profil):
        """Version 'strict' : tous les jours du profil retenus, un camion par jour (debordement -> impossible)."""
        dates = self.DATES_PROFIL[idx_profil]
        if len(dates) == 0:
            return None
        ce = self.cout_exceptionnels(couple, dates)
        if ce is None:
            return None
        cout_exc, nb_exc = ce
        besoins = couple["besoins"]; poids = couple["poids"]; volume = couple["volume"]
        if len(besoins) == 0:
            return {"cout": cout_exc, "camions": nb_exc, "livraisons": 0,
                    "jours": np.array([], dtype="datetime64[D]"), "idx": idx_profil, "exc": nb_exc}
        pos = np.searchsorted(dates, besoins, side="right") - 1
        if (pos < 0).any():
            return None
        avance = (besoins - dates[pos]).astype("timedelta64[D]").astype(int)
        if (avance > self.AVANCE_MAX).any():
            return None
        cout = 0.0; jours_liv = []
        for u in np.unique(pos):                       # seuls les jours qui ont quelque chose a livrer ont un camion
            w = poids[pos == u].sum(); v = volume[pos == u].sum()
            if w > self.CAP_POIDS + 1e-6 or v > self.CAP_VOLUME + 1e-6:
                return None
            cout += self.prix_camion(couple["ligne"], w); jours_liv.append(dates[u])
        return {"cout": cout + cout_exc, "camions": len(jours_liv) + nb_exc, "livraisons": len(jours_liv),
                "jours": np.array(jours_liv, dtype="datetime64[D]"), "idx": idx_profil, "exc": nb_exc}

    def evaluer_ancien(self, couple, idx_profil):
        """Sans H19 : plusieurs camions par jour (H13), tous les jours du profil, lignes exceptionnelles coupees."""
        dates = self.DATES_PROFIL[idx_profil]
        if len(dates) == 0:
            return None
        g = couple["df"]; besoins = g["date"].values.astype("datetime64[D]")
        pos = np.searchsorted(dates, besoins, side="right") - 1
        if (pos < 0).any():
            return None
        avance = (besoins - dates[pos]).astype("timedelta64[D]").astype(int)
        if (avance > self.AVANCE_MAX).any():
            return None
        w = g["weight"].values; v = g["volume"].values
        cout = 0.0; nbc = 0; jours_liv = []
        for u in np.unique(pos):
            cams = self.charger_camions_vieux(w[pos == u], v[pos == u])
            cout += sum(self.prix_camion(couple["ligne"], x) for x in cams); nbc += len(cams); jours_liv.append(dates[u])
        return {"cout": cout, "camions": nbc, "livraisons": len(jours_liv),
                "jours": np.array(jours_liv, dtype="datetime64[D]"), "idx": idx_profil, "exc": 0}

    def charger_camions_vieux(self, poids, volume):
        """Chargement multi-camions du milestone 2 (H13) : plus lourdes d'abord, chaque camion au maximum."""
        poids = np.asarray(poids, float); volume = np.asarray(volume, float)
        ordre = np.argsort(poids)[::-1]
        reste_p = poids[ordre].copy(); reste_v = volume[ordre].copy()
        camions = []; cam_p = cam_v = 0.0; i = 0
        while i < len(reste_p):
            if reste_p[i] <= 1e-9 and reste_v[i] <= 1e-9:
                i += 1; continue
            libre_p = self.CAP_POIDS - cam_p; libre_v = self.CAP_VOLUME - cam_v
            densite = (reste_v[i] / reste_p[i]) if reste_p[i] > 1e-12 else 0.0
            ajout_p = reste_p[i]
            if ajout_p > libre_p:
                ajout_p = libre_p
            if densite > 0 and ajout_p * densite > libre_v:
                ajout_p = libre_v / densite
            if ajout_p <= 1e-9:
                camions.append(cam_p); cam_p = cam_v = 0.0; continue
            ajout_v = ajout_p * densite if reste_p[i] > 1e-12 else min(reste_v[i], libre_v)
            cam_p += ajout_p; cam_v += ajout_v
            reste_p[i] -= ajout_p; reste_v[i] -= ajout_v
            if reste_p[i] <= 1e-9 and reste_v[i] <= 1e-9:
                i += 1
            if cam_p >= self.CAP_POIDS - 1e-6 or cam_v >= self.CAP_VOLUME - 1e-6:
                camions.append(cam_p); cam_p = cam_v = 0.0
        if cam_p > 1e-9 or cam_v > 1e-9:
            camions.append(cam_p)
        return camions

    # ----------------------------------------------------------------------
    # Aiguillage et evaluation de tous les couples
    # ----------------------------------------------------------------------

    def evaluer_profil(self, cle, idx_profil, un_camion=None, mode=None):
        """Aiguille vers la bonne methode selon les reglages H19 (un_camion) et H21 (mode : libre, intermediaire, strict)."""
        un_camion = self.UN_CAMION_PAR_JOUR if un_camion is None else un_camion
        mode = self.MODE_PROFIL if mode is None else mode
        couple = self.COUPLES[cle]
        if not un_camion:
            return self.evaluer_ancien(couple, idx_profil)
        if cle in self.COUPLES_CAP:
            return self.evaluer_cap_mode(couple, idx_profil, mode)
        if mode == "strict":
            return self.evaluer_strict(couple, idx_profil)
        r = self.evaluer_dp(couple, idx_profil)
        if mode == "libre" or r is None:
            return r
        # intermediaire : si la meilleure solution libre atteint deja l'objectif, c'est aussi la meilleure ici
        liv, bes = self.lignes_dp(couple, r["jours"])
        if self.semaines_respectees(idx_profil, liv, bes)[0] >= self.objectif_semaines(idx_profil)[0]:
            return r
        return self.evaluer_dp_inter(couple, idx_profil)

    def evaluer_tous(self, indices, un_camion=None, mode=None):
        """Pour chaque couple, la liste des profils possibles avec leur cout."""
        res = {}
        for cle in self.COUPLES:
            poss = []
            for i in indices:
                r = self.evaluer_profil(cle, i, un_camion, mode)
                if r is not None:
                    poss.append(r)
            res[cle] = poss
        return res

    # ----------------------------------------------------------------------
    # Etape 2 : le lissage dans la semaine (R4)
    # ----------------------------------------------------------------------

    def lissage(self, candidats, meilleur, tolerance):
        """Choisit par usine un profil dans la tolerance qui decharge le jour deja le plus charge (R4)."""
        choix = {}; cout = 0.0
        for usine in sorted({pl for (s, pl) in candidats}):
            couples_u = [c for c in candidats if c[1] == usine and candidats[c]]
            couples_u.sort(key=lambda c: -meilleur[c]["cout"])     # du plus cher au moins cher
            charge = defaultdict(int)                               # livraisons par jour de la semaine
            for c in couples_u:
                seuil = meilleur[c]["cout"] * (1 + tolerance) + 1e-9
                toleres = [r for r in candidats[c] if r["cout"] <= seuil]
                pic = max(charge.values()) if charge else 0
                jours_pic = {j for j, v in charge.items() if v == pic}
                def cle_tri(r):
                    wd = [pd.Timestamp(d).weekday() for d in r["jours"]]
                    ajout_pic = sum(1 for j in wd if j in jours_pic)     # charge ajoutee au jour le plus charge
                    essai = dict(charge)
                    for j in wd:
                        essai[j] = essai.get(j, 0) + 1
                    vec = np.array(list(essai.values())) if essai else np.array([0])
                    return (ajout_pic, int(vec.max()), float(vec.std()), r["cout"], r["livraisons"])
                choisi = min(toleres, key=cle_tri)
                choix[c] = choisi; cout += choisi["cout"]
                for d in choisi["jours"]:
                    charge[pd.Timestamp(d).weekday()] += 1
        return choix, cout

    def charge_par_jour_semaine(self, choix):
        """Nombre de livraisons reelles par usine et par jour de la semaine."""
        t = defaultdict(lambda: defaultdict(int))
        for (s, pl), b in choix.items():
            for d in b["jours"]:
                t[pl][pd.Timestamp(d).weekday()] += 1
        return t

    # ----------------------------------------------------------------------
    # Contenu des camions (sortie 2)
    # ----------------------------------------------------------------------

    def reconstruire(self, cle, b):
        """Contenu des camions d'un couple pour le profil choisi b : liste de camions (date, exceptionnel, lignes)."""
        couple = self.COUPLES[cle]; dates = self.DATES_PROFIL[b["idx"]]; trucks = []
        # envois exceptionnels (H20) : une ligne, un camion, jour du profil le plus proche <= besoin
        for e in range(len(couple["exc_dates"])):
            bd = couple["exc_dates"][e]
            k = int(np.searchsorted(dates, bd, side="right")) - 1
            trucks.append({"date": pd.Timestamp(dates[k]), "exceptionnel": True, "lignes": [{
                "material": couple["exc_mat"][e], "unloading_point": couple["exc_up"][e],
                "date_besoin": pd.Timestamp(bd), "quantite": float(couple["exc_qte"][e]),
                "poids": float(couple["exc_poids"][e]), "volume": float(couple["exc_vol"][e])}]})
        besoins = couple["besoins"]
        if len(besoins) == 0:
            return trucks
        def truck(jour, idxs):
            lignes = [{"material": couple["mat"][i], "unloading_point": couple["up"][i],
                       "date_besoin": pd.Timestamp(couple["besoins"][i]), "quantite": float(couple["qte"][i]),
                       "poids": float(couple["poids"][i]), "volume": float(couple["volume"][i])} for i in idxs]
            return {"date": pd.Timestamp(jour), "exceptionnel": False, "lignes": lignes}
        if "affect" in b:                                         # 3 couples aux jours trop lourds : ligne -> jour
            for k in sorted(b["affect"]):
                trucks.append(truck(dates[k], b["affect"][k]))
        else:                                                    # DP ou strict : chaque besoin au dernier jour livre <= lui
            jours = np.sort(b["jours"])
            jj = jours.astype("datetime64[D]").astype(int); bjours = besoins.astype("datetime64[D]").astype(int)
            pos = np.searchsorted(jj, bjours, side="right") - 1
            par_jour = defaultdict(list)
            for i in range(len(besoins)):
                par_jour[int(pos[i])].append(i)
            for k, idxs in par_jour.items():
                trucks.append(truck(jours[k], idxs))
        return trucks

    def construire_contenu(self, choix):
        """Sortie 2 : une ligne par ligne de besoin chargee, avec son camion."""
        lignes_camions = []; numero = 0
        for (s, pl), b in choix.items():
            for t in self.reconstruire((s, pl), b):
                numero += 1; cid = f"C{numero:05d}"
                for L in t["lignes"]:
                    lignes_camions.append({"camion_id": cid, "supplier_id": s, "plant": pl,
                        "date_livraison": t["date"].date(), "material": L["material"],
                        "unloading_point": L["unloading_point"], "date_besoin": L["date_besoin"].date(),
                        "avance_jours": (L["date_besoin"] - t["date"]).days, "quantite": round(L["quantite"], 3),
                        "poids": round(L["poids"], 3), "volume": round(L["volume"], 4),
                        "envoi_exceptionnel": t["exceptionnel"]})
        return pd.DataFrame(lignes_camions)

    # ----------------------------------------------------------------------
    # Validation de la solution
    # ----------------------------------------------------------------------

    def semaines_par_couple(self, choix, contenu):
        """(semaines respectees, semaines du profil) de chaque couple, lues sur le contenu des camions."""
        normal = contenu[~contenu["envoi_exceptionnel"]]
        groupes = {k: g for k, g in normal.groupby(["supplier_id", "plant"])}
        res = {}
        for cle, b in choix.items():
            g = groupes.get(cle)
            liv = en_jours(g["date_livraison"]) if g is not None else []
            bes = en_jours(g["date_besoin"]) if g is not None else []
            res[cle] = self.semaines_respectees(b["idx"], liv, bes)
        return res

    def valider(self, choix, contenu, cout_annonce, mode=None):
        """Passe tous les controles de la solution ; s'arrete si un echoue."""
        mode = self.MODE_PROFIL if mode is None else mode
        controles = []
        normal = contenu[~contenu["envoi_exceptionnel"]]
        excep = contenu[contenu["envoi_exceptionnel"]]
        par_couple = {k: g for k, g in contenu.groupby(["supplier_id", "plant"])}
        # 1. chaque ligne livree une seule fois ; poids et volume conserves
        c1 = (len(contenu) == len(self.opt) and abs(self.opt["weight"].sum() - contenu["poids"].sum()) < 1
              and abs(self.opt["volume"].sum() - contenu["volume"].sum()) < 0.1)
        controles.append(("chaque ligne livree une fois (poids et volume conserves)", bool(c1)))
        # 2. aucune ligne coupee : une ligne = une seule occurrence
        c2 = not contenu.duplicated(subset=["supplier_id", "plant", "material", "unloading_point", "date_besoin"]).any()
        controles.append(("aucune ligne coupee", bool(c2)))
        # 3. avance entre 0 et 7 jours
        av = contenu["avance_jours"]
        controles.append(("avance entre 0 et 7 jours", bool((av >= 0).all() and (av <= self.AVANCE_MAX).all())))
        # 4. jours ouvres, hors semaine fermee, dans l'horizon
        dl = pd.to_datetime(contenu["date_livraison"])
        controles.append(("lundi-vendredi, hors semaine fermee, dans l'horizon",
                          bool((dl.dt.weekday < 5).all() and (~dl.map(self.semaine_fermee)).all() and (dl >= self.d0).all())))
        # 5. capacite des camions normaux
        cap = normal.groupby("camion_id").agg(p=("poids", "sum"), v=("volume", "sum"))
        controles.append(("capacite 24 500 kg / 110,4 m3 (camions normaux)",
                          bool((cap["p"] <= self.CAP_POIDS + 1e-3).all() and (cap["v"] <= self.CAP_VOLUME + 1e-3).all())))
        # 6. un seul couple par camion (R3)
        controles.append(("un seul couple par camion (R3)",
                          bool((contenu.groupby("camion_id")[["supplier_id", "plant"]].nunique() <= 1).all().all())))
        # 7. au plus un camion par couple et par jour, hors exceptionnels (H19)
        c7 = (normal.groupby(["supplier_id", "plant", "date_livraison"])["camion_id"].nunique() <= 1).all()
        controles.append(("au plus un camion par couple et par jour (H19)", bool(c7)))
        # 8. chaque date de livraison est une date exacte du profil choisi ; par semaine <= nombre du profil
        c8 = True
        for cle, b in choix.items():
            dates_p = self.DATES_PROFIL[b["idx"]].astype("datetime64[D]").astype(int)
            g = par_couple.get(cle)
            if g is None:
                continue
            if not np.isin(en_jours(g["date_livraison"]), dates_p).all():
                c8 = False
            dts = pd.to_datetime(g[~g["envoi_exceptionnel"]]["date_livraison"].unique())
            par_sem = Counter(semaine_de(d) for d in dts)
            nb_profil = Counter(semaine_de(d) for d in self.DATES_PROFIL[b["idx"]])
            if any(par_sem[w] > nb_profil.get(w, 0) for w in par_sem):
                c8 = False
        controles.append(("livraisons aux dates exactes du profil, <= nombre du profil par semaine", c8))
        # 9. chaque envoi exceptionnel : une seule ligne plus lourde qu'un camion
        c9 = True
        for cid, g in excep.groupby("camion_id"):
            if len(g) != 1 or not (g["poids"].iloc[0] > self.CAP_POIDS or g["volume"].iloc[0] > self.CAP_VOLUME):
                c9 = False
        controles.append(("chaque envoi exceptionnel = une ligne plus lourde qu'un camion", c9))
        # 10. les jours trop lourds (3 couples) couverts sans depasser la capacite
        c10 = True
        for (s, pl) in self.COUPLES_CAP:
            sous = normal[(normal.supplier_id == s) & (normal.plant == pl)]
            if len(sous) != len(self.COUPLES[(s, pl)]["besoins"]):
                c10 = False
            capc = sous.groupby("camion_id").agg(p=("poids", "sum"), v=("volume", "sum"))
            if not ((capc["p"] <= self.CAP_POIDS + 1e-3).all() and (capc["v"] <= self.CAP_VOLUME + 1e-3).all()):
                c10 = False
        controles.append(("jours trop lourds couverts sans depasser la capacite", c10))
        # 11. jamais de camion vide : les camions annonces sont exactement les camions charges
        c11 = contenu["camion_id"].nunique() == sum(b["camions"] for b in choix.values())
        controles.append(("aucun camion vide (camions annonces = camions charges)", bool(c11)))
        # 12. cout recalcule == cout annonce
        recalc = 0.0
        for cid, g in contenu.groupby("camion_id"):
            lg = self.COUPLES[(g["supplier_id"].iloc[0], g["plant"].iloc[0])]["ligne"]
            recalc += self.prix_exceptionnel(lg) if g["envoi_exceptionnel"].iloc[0] else self.prix_camion(lg, g["poids"].sum())
        controles.append(("cout coherent avec les camions", abs(recalc - cout_annonce) < 1))
        # 13. la regle de la version choisie
        if mode == "strict":
            c13 = True                       # chaque jour du profil qui a quelque chose a livrer est livre
            for cle, b in choix.items():
                g = par_couple.get(cle)
                if g is None:
                    continue
                gn = g[~g["envoi_exceptionnel"]]
                dates_p = self.DATES_PROFIL[b["idx"]].astype("datetime64[D]").astype(int)
                bes = en_jours(gn["date_besoin"]); livres = set(en_jours(gn["date_livraison"]))
                pos = np.searchsorted(dates_p, bes, side="right") - 1      # le jour du profil de chaque besoin
                if any(int(dates_p[k]) not in livres for k in np.unique(pos)):
                    c13 = False
            controles.append(("version strict : chaque jour du profil qui a quelque chose a livrer est livre", c13))
        elif mode == "intermediaire":
            sem = self.semaines_par_couple(choix, contenu)
            c13 = all(sem[cle][0] >= self.objectif_semaines(b["idx"])[0] for cle, b in choix.items())
            controles.append((f"version intermediaire : au moins {self.MIN_SEMAINES_RESPECTEES} semaines respectees "
                              "par couple (toutes si le profil en a moins)", c13))
        else:
            controles.append(("version libre : le profil est un maximum (dates deja verifiees au controle 8)", c8))
        return controles


    # ----------------------------------------------------------------------
    # Situation actuelle (baseline) d'un couple
    # ----------------------------------------------------------------------

    def cout_actuel_couple(self, cle):
        g = self.COUPLES[cle]["df"]; lg = self.COUPLES[cle]["ligne"]; c = 0.0
        for dt, gg in g.groupby("date"):
            exc = (gg["weight"].values > self.CAP_POIDS) | (gg["volume"].values > self.CAP_VOLUME)
            nn = gg[~exc]
            if len(nn):
                c += sum(self.prix_camion(lg, w) for w in self.charger_camions_vieux(nn["weight"].values, nn["volume"].values))
            c += int(exc.sum()) * self.prix_exceptionnel(lg)
        return c

    # ----------------------------------------------------------------------
    # Baselines : la situation actuelle (chaque besoin livre le jour meme)
    # ----------------------------------------------------------------------
    def calculer_baselines(self):
        """Cout et camions de la situation actuelle : baseline du milestone 2 (ligne lourde coupee) et baseline H20
        (la ligne exceptionnelle = un camion au tarif '>4000'). Renvoie un dictionnaire."""
        baseline_m2 = 0.0; camions_m2 = 0
        for (s, pl, dt), g in self.opt.groupby(["supplier_id", "plant", "date"]):
            cams = self.charger_camions_vieux(g["weight"].values, g["volume"].values)
            baseline_m2 += sum(self.prix_camion(g["ligne_grille"].iloc[0], w) for w in cams); camions_m2 += len(cams)
        baseline_h20 = 0.0; camions_h20 = 0
        for (s, pl, dt), g in self.opt.groupby(["supplier_id", "plant", "date"]):
            lg = g["ligne_grille"].iloc[0]
            exc = (g["weight"].values > self.CAP_POIDS) | (g["volume"].values > self.CAP_VOLUME)
            normal = g[~exc]
            if len(normal):
                cams = self.charger_camions_vieux(normal["weight"].values, normal["volume"].values)
                baseline_h20 += sum(self.prix_camion(lg, w) for w in cams); camions_h20 += len(cams)
            for _ in range(int(exc.sum())):
                baseline_h20 += self.prix_exceptionnel(lg); camions_h20 += 1
        return {"baseline_m2": baseline_m2, "camions_m2": camions_m2, "baseline_h20": baseline_h20, "camions_h20": camions_h20,
                "livraisons_actuelles": self.opt.groupby(["supplier_id", "plant", "date"]).ngroups}

    # ----------------------------------------------------------------------
    # Le moteur complet
    # ----------------------------------------------------------------------
    @staticmethod
    def meilleurs(candidats):
        """Pour chaque couple, le profil le moins cher parmi les candidats (etape 1)."""
        return {cle: min(v, key=lambda r: r["cout"]) for cle, v in candidats.items() if v}

    def lancer(self, mode=None, un_camion=None, tolerance=None, limite_secondes=None):
        """Enchaine tout le moteur pour une version et mesure chaque etape.

        mode : 'libre', 'intermediaire' ou 'strict' (par defaut : MODE_PROFIL) ;
        Leve `ValidationEchouee` (avec le detail, et les couples sans profil possible) si la solution viole une regle.
        """
        mode = self.MODE_PROFIL if mode is None else mode
        un_camion = self.UN_CAMION_PAR_JOUR if un_camion is None else un_camion
        tolerance = self.TOLERANCE_LISSAGE if tolerance is None else tolerance
        limite = self.TEMPS_MAX_SECONDES if limite_secondes is None else limite_secondes
        temps = {}
        t = time.perf_counter()
        candidats = self.evaluer_tous(self.IDX_TOUS, un_camion=un_camion, mode=mode)
        meilleur = self.meilleurs(candidats)
        temps["evaluation des couples et profils"] = time.perf_counter() - t
        t = time.perf_counter()
        choix, cout = self.lissage(candidats, meilleur, tolerance)
        temps["lissage"] = time.perf_counter() - t
        t = time.perf_counter()
        contenu = self.construire_contenu(choix)
        temps["construction des sorties"] = time.perf_counter() - t
        t = time.perf_counter()
        controles = self.valider(choix, contenu, cout, mode=mode)
        temps["validations"] = time.perf_counter() - t
        echecs = [nom for nom, ok in controles if not ok]
        if echecs:
            sans_profil = sorted(cle for cle, v in candidats.items() if not v)
            detail = "\n- ".join(echecs)
            if sans_profil:
                detail += f"\nCouples sans aucun profil possible ({len(sans_profil)}) : " + ", ".join(f"{s} x {pl}" for s, pl in sans_profil)
            raise ValidationEchouee(f"Une validation a echoue : nous ne publions pas ce resultat.\n- {detail}")
        total = sum(temps.values())
        if total > limite:
            raise RuntimeError(f"Le moteur a depasse la limite de {limite} s ({total:.1f} s).")
        return Resultat(mode=mode, choix=choix, cout=cout, etape1=meilleur, contenu=contenu, temps=temps, total=total, controles=controles)
