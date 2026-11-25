# Projet IA — Consolidation des livraisons

Ce projet regroupe les livraisons de fournisseurs vers 4 usines pour **réduire le coût de transport** : au lieu de livrer chaque
besoin le jour même, on choisit pour chaque couple fournisseur × usine un **profil de livraison** (quels jours de la semaine livrer)
et on charge les camions en conséquence, en respectant les règles du client.

Sur les données du client (6 semaines, 171 couples optimisés, 4 252 lignes de besoin), avec la version **stricte** recommandée :

| | Avant | Après |
|---|---|---|
| Coût du périmètre | 143 321 € | **82 111 €** (−42,7 %) |
| Camions | 1 604 | **652** |

## Lancer le programme

```bash
python main.py                          # planning du client, version « stricte » (recommandée)
python main.py mon_planning.csv         # un autre planning, même format
python main.py --version toutes         # les trois versions du moteur, avec leur comparaison
python main.py mon_planning.csv --sortie dossier_resultats/
```

Le programme enchaîne : **préparation du planning → moteur → contrôles → fichiers**. Il dure quelques secondes.
Il s'arrête avec un message clair si le fichier est à corriger (colonnes manquantes, doublons, dates illisibles...).

**Fichiers d'entrée** (par défaut ceux du client, dans `data/` et `docs/`) :
- le planning : un CSV avec les colonnes `date, supplier_id, material, plant, unloading_point, schedule_quantity, weight, volume, transmission_date, version_date` ;
- `--distances` : un CSV `supplier_id, distance` ;
- `--grille` : la grille tarifaire du transporteur (PDF, `docs/rate_sheet.pdf`).

**Fichiers de sortie** (dossier `resultats/` par défaut) :

| Fichier | Contenu |
|---|---|
| `profils_couples.csv` | **sortie 1** : le profil de livraison à appliquer à chaque couple, avec son coût actuel, son coût optimisé et son économie |
| `contenu_camions.csv` | **sortie 2** : le matériel chargé dans chaque camion (une ligne par ligne de besoin, avec son camion et sa date de livraison) |
| `resume_economies.csv` | le résumé : coûts avant/après, camions, livraisons, avec et sans les lignes incomplètes |
| `planning_propre.csv`, `journal_pipeline.csv`, `lignes_inconnues.csv` | le planning nettoyé, le journal du nettoyage, et l'estimation des lignes à information manquante |
| `comparaison_versions.csv` | avec `--version toutes` : les trois versions côte à côte |

## Le dashboard

```bash
streamlit run app.py        # ou ./lancer_app.sh  ->  http://localhost:8501
```

Dans la colonne de gauche, on **dépose les fichiers d'entrée** (planning, distances, grille tarifaire ; sans fichier, ceux du client sont utilisés), on choisit
la version du moteur (stricte, intermédiaire, libre, ou les trois pour les comparer) et on clique sur **Lancer le calcul**. On choisit ensuite la
**semaine** (ou toutes), les **usines** et les **fournisseurs** à regarder (en mode « Comparer les trois », la version affichée) : ces choix valent pour toutes les pages.
En haut de chaque page, trois indicateurs : coût avant → après et camions avant → après (pour la semaine choisie, ou tout l'horizon), couples couverts / couples du fichier.

| Page | Contenu |
|---|---|
| **Sorties** | les trois sorties du projet (slides « Livrables attendus »). **Sortie 1** : un profil par couple (tous les couples du fichier, avec leur statut), **sortie 2** : le contenu de chaque camion et ses materials, **sortie 3** : le saving par couple (semaine choisie et horizon). Chaque tableau se télécharge en CSV, « Tout télécharger » donne tous les CSV dans une archive .zip ; cliquer une ligne ouvre le couple dans la page suivante |
| **Détails des sorties** | on choisit un couple et on voit son calendrier semaine × jour : fond bleu = jour du profil, un camion par ligne (poids / volume / prix), trait bleu = optimisé, rouge = exceptionnel, orange = hors optimisation (données manquantes). Trois vues : **aujourd'hui**, **avant lissage**, **après lissage** (avec une phrase si le lissage a déplacé le profil) |
| **Gains** | avant/après (coût, camions, livraisons, remplissage, camions par semaine), par usine (économies, calendrier d'une usine), lissage (part des livraisons par jour de la semaine), couples (réalisé contre potentiel, les 10 plus rentables) |

Le calcul des sorties est dans `dashboard/sorties_client.py` (fonctions pures, testées) ; l'affichage dans `dashboard/explorateur.py` et les pages `dashboard/page_*.py`.
Le calendrier est en HTML/CSS (`st.html`).

En cas de fichier à corriger (colonne manquante, doublons...), un message clair l'explique au lieu d'un résultat.

## Comment ça marche

1. **Préparation** (`src/preparation.py`) : retire les lignes à quantité 0 et les dates « fourre-tout », complète les poids et volumes vides
   (en les marquant), ajoute la distance et la ligne de la grille de prix, marque les lignes à information manquante (non optimisées).
2. **Moteur** (`src/moteur.py`) : pour chaque couple, évalue les **166 profils** candidats par **programmation dynamique exacte** (le meilleur choix des
   jours de livraison utiles), garde le moins cher, puis **lisse** la charge de chaque usine dans la semaine parmi les profils presque aussi bons.
3. **Contrôles** : le moteur refuse de publier une solution qui viole une règle (13 contrôles internes), et `src/controles.py` la recalcule de façon
   indépendante (exhaustivité par ligne, par matériau et par usine, capacité, avance, coût...).

**Règles du client** (`src/config.py`) : un besoin est livré le jour même ou **au plus 7 jours avant**, jamais en retard (R1) ;
un camion porte au plus 24 500 kg et 110,4 m³ (R2) ; un camion ne sert qu'un couple fournisseur × usine (R3).
**Calendrier de livraison** : la règle des 7 jours vaut aussi au début de l'horizon, donc un besoin du lundi 09/11 peut partir dès le lundi 02/11. Le premier jour de livraison est par défaut le premier besoin moins 7 jours ; il se règle avec `PREMIER_JOUR_LIVRAISON` dans `src/config.py` (par exemple `"2026-11-09"` pour interdire toute livraison avant le premier besoin).

**Trois versions du moteur** (`--version`) :

| Version | Principe | Coût | Économie | Semaines du profil respectées |
|---|---|---|---|---|
| **`strict`** (par défaut) | tous les jours du profil sont retenus, chaque semaine : le profil proposé est un **engagement** envers le fournisseur | 82 111 € | 42,7 % | 100 % |
| `intermediaire` | au moins 4 semaines du profil sont respectées | 79 096 € | 44,8 % | 73,3 % |
| `libre` | le profil est un maximum : le moteur choisit les jours utiles au moins cher (version de comparaison) | 74 908 € | 47,7 % | 48,9 % |

Plus on laisse de souplesse, moins ça coûte, mais moins le rythme annoncé aux fournisseurs est tenu.

## Structure du projet

```
main.py                 point d'entree en ligne de commande : python main.py
app.py                  dashboard Streamlit : streamlit run app.py (ou ./lancer_app.sh)
dashboard/              le dashboard : sorties_client.py (calcul des sorties), explorateur.py (calendrier), page_*.py (les 3 pages), style.py, graphiques.py
outils/                 regenerer_moteur.py : regenere src/moteur.py quand le moteur du notebook change
Dockerfile.app          image de l'application (dashboard et programme) ; docker-compose.yml la lance
src/
  config.py             regles, parametres et chemins (un seul endroit)
  preparation.py        nettoyage du planning (milestone 1)
  tarifs.py             grille de prix, situation actuelle, lignes inconnues (milestone 2)
  moteur.py             moteur de consolidation (milestone 3)
  controles.py          controles independants d'une solution (milestone 4)
  sorties.py            tableaux et fichiers de resultats
  pipeline.py           le flux complet, reutilisable (ligne de commande, dashboard)
tests/                  tests automatiques (moteur, programme, dashboard) : pytest tests
notebooks/              les notebooks de chaque milestone (analyse, explications, graphiques)
docs/                   enonce, grille du transporteur, simulateur interactif
data/                   donnees du client et fichiers intermediaires
```

## Tests

```bash
pytest tests -v
```

Ces tests vérifient que les modules reproduisent le moteur des notebooks : les fonctions (prix, profils, programmation dynamique contre une force brute),
les règles sur chaque version, la reproductibilité, la non-régression (résultats de référence figés dans `tests/reference_resultats.json`, ceux du
milestone 3), le programme complet (fichiers identiques à ceux publiés dans `data/processed/`, erreurs claires, planning modifié) et le dashboard
(exécuté sans navigateur : les coûts affichés sont ceux des notebooks).

La suite de tests du projet, avec ses six familles et l'analyse des gains, est celle du notebook `notebooks/milestone4.ipynb`.

**Quand le moteur du notebook change** (milestone 3), `src/moteur.py` doit être régénéré : `python outils/regenerer_moteur.py`. Un test (`tests/test_outils.py`)
l'échoue tant que ce n'est pas fait, et `python outils/regenerer_moteur.py --verifier` indique si c'est nécessaire.

## Limites connues

Celles des notebooks :

- les profils sont stables sur 7 semaines de livraison (6 semaines de besoins) : sur un horizon plus long, il faudrait vérifier qu'ils tiennent ;
- le lissage et le traitement des **3 couples aux jours trop lourds** sont approchés (règles gloutonnes), là où le reste du moteur est exact ;
- les **138 lignes à information manquante** (poids, volume ou distance) ne sont pas optimisées : elles sont conservées et estimées au pire cas (un camion
  plein par ligne). Compléter leurs données ouvrirait une économie supplémentaire ;
- le remplissage médian reste bas, car un camion ne porte qu'un seul fournisseur : le gain vient du nombre de camions en moins ;
- la semaine de Noël (21/12/2026) est supposée sans livraison (hypothèse H7, réglable dans `src/config.py`).

Une note technique sur les modules : pour retrouver exactement les fichiers des notebooks, le moteur lit la grille de prix telle qu'elle est enregistrée dans
`grille_prix.csv` (voir `preparation.relire_grille`). Les prix en mémoire diffèrent en effet de 10⁻¹⁶ sur quelques cases, ce qui peut départager autrement
deux profils de même coût.

## Installer le projet

```bash
git clone https://github.com/FlorentinBIAOU/Projet-IA.git
cd Projet-IA
```

**Option 1 — Python**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py        # lancer le programme (resultats dans resultats/)
jupyter lab           # ou explorer les notebooks
```

**Option 2 — Docker**
```bash
docker build -t projet-ia .
docker run --rm -p 8888:8888 -v "$PWD":/app projet-ia
```
Puis ouvrir http://127.0.0.1:8888/lab. Pour lancer le programme dans ce conteneur :
`docker run --rm -v "$PWD":/app projet-ia python main.py`

**Option 3 — Docker Compose (l'application)**
```bash
docker compose up                                  # le dashboard sur http://localhost:8501
docker compose --profile calcul run --rm calcul    # le programme en ligne de commande, les trois versions (résultats dans ./resultats)
docker compose --profile notebooks up              # JupyterLab sur http://localhost:8888
```
L'image de l'application est décrite dans `Dockerfile.app` ; le `Dockerfile` d'origine reste celui des notebooks.


## Règles
- Ne jamais modifier `data/` à la main.
- Nouvelle bibliothèque → l'ajouter dans `requirements.txt` avec sa version.
