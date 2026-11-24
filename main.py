"""Point d'entree : consolide un planning de livraisons.

Exemples (depuis la racine du projet, environnement Python active) :

    python main.py                                  # planning du client, version stricte (recommandee)
    python main.py mon_planning.csv                 # un autre planning, meme format
    python main.py --version toutes                 # les trois versions du moteur, avec leur comparaison
    python main.py mon_planning.csv --sortie out/   # choisir le dossier des resultats

Le programme enchaine : preparation du planning -> moteur de consolidation -> controles -> fichiers.
Resultats (dossier `resultats/` par defaut) :
    profils_couples.csv     sortie 1 : le profil de livraison a appliquer a chaque couple fournisseur x usine
    contenu_camions.csv     sortie 2 : le materiel regroupe dans chaque camion
    resume_economies.csv    le resume des economies
    (et planning_propre.csv, journal_pipeline.csv, lignes_inconnues.csv ; comparaison_versions.csv avec --version toutes)
"""
import argparse
import logging
import sys

from src import config, preparation
from src.moteur import ValidationEchouee
from src.pipeline import executer


def lire_arguments(argv=None):
    p = argparse.ArgumentParser(description="Consolidation des livraisons : planning -> profils de livraison et contenu des camions.")
    p.add_argument("planning", nargs="?", default=str(config.CHEMIN_PLANNING),
                   help="planning de livraisons (CSV). Par defaut : celui du client (data/released_schedule.csv).")
    p.add_argument("--distances", default=str(config.CHEMIN_DISTANCES), help="fichier des distances fournisseur -> usine (CSV)")
    p.add_argument("--grille", default=str(config.CHEMIN_GRILLE), help="grille tarifaire du transporteur (PDF)")
    p.add_argument("--version", default="strict", choices=[*config.VERSIONS, "toutes"],
                   help="version du moteur : strict (recommandee : le profil propose est un engagement), intermediaire, libre (la moins chere), "
                        "ou toutes (comparaison). Defaut : strict")
    p.add_argument("--sortie", default=str(config.DOSSIER_SORTIE), help="dossier des resultats (cree au besoin). Defaut : resultats/")
    p.add_argument("--silencieux", action="store_true", help="n'affiche que le resume final")
    return p.parse_args(argv)


def main(argv=None):
    args = lire_arguments(argv)
    logging.basicConfig(level=logging.WARNING if args.silencieux else logging.INFO, format="%(message)s")
    versions = config.VERSIONS if args.version == "toutes" else (args.version,)
    retenue = "strict" if args.version == "toutes" else args.version
    try:
        planning = preparation.charger_planning(args.planning)
        distances = preparation.charger_distances(args.distances)
        grille = preparation.charger_grille_pdf(args.grille)
        ex = executer(planning, distances, grille, versions=versions, version_retenue=retenue, dossier_sortie=args.sortie)
    except FileNotFoundError as e:
        print(f"Fichier introuvable : {e.filename}", file=sys.stderr)
        return 1
    except ValueError as e:                       # fichier a corriger (colonnes, dates, doublons...) ou solution refusee
        print(f"\nERREUR : {e}", file=sys.stderr)
        return 2 if isinstance(e, ValidationEchouee) else 1

    r = ex.resume.set_index("indicateur")["valeur"]
    print("\n=== Resultat (version %s) ===" % ex.version_retenue)
    print(f"Cout avant : {float(r['Cout avant - baseline H20 (perimetre)']):>12,.2f} EUR".replace(",", " "))
    print(f"Cout apres : {float(r['Cout apres (perimetre)']):>12,.2f} EUR".replace(",", " "))
    print(f"Economie   : {float(r['Economie (EUR)']):>12,.2f} EUR ({r['Economie (%)']} %)".replace(",", " "))
    print(f"Camions    : {r['Camions avant']} -> {r['Camions apres']}")
    if ex.comparaison is not None:
        print("\nComparaison des versions :")
        print(ex.comparaison[["version", "cout", "economie %", "camions", "part semaines respectees %"]].to_string(index=False))
    print("\nFichiers ecrits :")
    for chemin in ex.fichiers.values():
        print("  ", chemin)
    return 0


if __name__ == "__main__":
    sys.exit(main())
