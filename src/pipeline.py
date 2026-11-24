"""Le flux complet : planning brut -> donnees propres -> moteur -> controles -> fichiers de sortie.

C'est la fonction `executer` que `main.py` (ligne de commande) et un futur dashboard appellent.
"""
import logging
import time
from dataclasses import dataclass, field

import pandas as pd

from . import config, controles, preparation, sorties, tarifs
from .moteur import Moteur

log = logging.getLogger("consolidation")


@dataclass
class Execution:
    """Tout ce que produit une execution du flux."""
    planning_propre: pd.DataFrame
    grille_prix: pd.DataFrame
    journal: pd.DataFrame
    moteur: Moteur
    baselines: dict
    inconnues: pd.DataFrame
    resultats: dict                  # version -> Resultat
    version_retenue: str
    profils_couples: pd.DataFrame    # sortie 1
    contenu_camions: pd.DataFrame    # sortie 2
    resume: pd.DataFrame
    comparaison: pd.DataFrame | None = None
    controles_independants: dict = field(default_factory=dict)   # version -> [(nom, ok, detail)]
    fichiers: dict = field(default_factory=dict)


def executer(planning, distances, grille_brute, versions=("strict",), version_retenue=None,
             dossier_sortie=None, parametres=None):
    """Lance tout le flux.

    planning, distances, grille_brute : DataFrames bruts (voir preparation.charger_*).
    versions : versions du moteur a calculer ('strict' recommandee, 'intermediaire', 'libre') ;
    version_retenue : celle qui donne les fichiers de sortie (par defaut la premiere) ;
    dossier_sortie : ou ecrire les fichiers (None : rien n'est ecrit) ;
    parametres : dictionnaire pour changer des regles du moteur (voir config.PARAMETRES_MOTEUR).
    """
    versions = tuple(versions)
    version_retenue = version_retenue or versions[0]
    if version_retenue not in versions:
        raise ValueError(f"La version retenue ({version_retenue}) doit faire partie des versions calculees {versions}.")

    t0 = time.perf_counter()
    log.info("1/4 Preparation du planning (%d lignes brutes)", len(planning))
    propre, grille_prix, journal = preparation.preparer_donnees(planning, distances, grille_brute)
    optimise = int((propre["statut"] == "optimise").sum())
    log.info("    %d lignes propres, dont %d optimisables et %d a information manquante (conservees telles quelles)",
             len(propre), optimise, len(propre) - optimise)

    log.info("2/4 Preparation du moteur")
    grille_relue = preparation.relire_grille(grille_prix)     # la grille telle qu'enregistree : voir relire_grille
    moteur = Moteur(propre, grille_relue, parametres)
    baselines = moteur.calculer_baselines()
    inconnues = tarifs.lignes_inconnues(propre, grille_relue)
    log.info("    %d couples, %d profils candidats, situation actuelle : %.2f EUR, %d camions",
             len(moteur.COUPLES), len(moteur.PROFILS), baselines["baseline_h20"], baselines["camions_h20"])

    log.info("3/4 Calcul (%s)", ", ".join(versions))
    resultats, independants = {}, {}
    for mode in versions:
        r = moteur.lancer(mode=mode)
        resultats[mode] = r
        liste, _ = controles.controles_solution(r.contenu, moteur.opt, moteur.grille, moteur.jours_ouvres, r.cout)
        independants[mode] = liste
        ko = [nom for nom, ok, _ in liste if not ok]
        if ko:
            raise RuntimeError(f"Controles independants en echec (version {mode}) : " + "; ".join(ko))
        log.info("    %-13s %10.2f EUR, %3d camions, %5.2f s, %d + %d controles OK",
                 mode, r.cout, r.contenu["camion_id"].nunique(), r.total, len(r.controles), len(liste))

    retenu = resultats[version_retenue]
    profils = sorties.profils_couples(moteur, retenu)
    resume = sorties.resume_economies(retenu, baselines, float(inconnues["cout"].sum()))
    comparaison = sorties.comparaison_versions(moteur, resultats, baselines, moteur.TEMPS_MAX_SECONDES) if len(resultats) > 1 else None

    execution = Execution(planning_propre=propre, grille_prix=grille_prix, journal=journal, moteur=moteur, baselines=baselines,
                          inconnues=inconnues, resultats=resultats, version_retenue=version_retenue,
                          profils_couples=profils, contenu_camions=retenu.contenu, resume=resume, comparaison=comparaison,
                          controles_independants=independants)
    if dossier_sortie is not None:
        log.info("4/4 Ecriture des fichiers dans %s", dossier_sortie)
        tableaux = {"profils_couples": profils, "contenu_camions": retenu.contenu, "resume_economies": resume,
                    "planning_propre": propre, "journal_pipeline": journal, "lignes_inconnues": inconnues}
        if comparaison is not None:
            tableaux["comparaison_versions"] = comparaison
        execution.fichiers = sorties.enregistrer(dossier_sortie, **tableaux)
    log.info("Termine en %.1f s.", time.perf_counter() - t0)
    return execution
