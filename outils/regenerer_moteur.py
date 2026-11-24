"""Regenere src/moteur.py a partir du notebook notebooks/milestone3.ipynb.

Le moteur du milestone 3 vit dans un notebook. Ce script en recopie le code exact (les fonctions, sans rien changer au calcul) dans la
classe `Moteur` de src/moteur.py : les variables globales du notebook deviennent des attributs (`self.AVANCE_MAX`, `self.COUPLES`...).
Le gabarit de la classe (constructeur, `lancer`, `calculer_baselines`) est dans outils/moteur_modele.txt.

A relancer chaque fois que le moteur du notebook change :

    python outils/regenerer_moteur.py            # regenere src/moteur.py
    python outils/regenerer_moteur.py --verifier # dit seulement si src/moteur.py est a jour
    pytest tests                       # verifie que le moteur modulaire donne les memes resultats que le notebook

Les tests comparent le moteur du notebook et celui de src/ : une divergence est detectee immediatement.
"""
import ast, json, re, sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
nb = json.load(open(RACINE / "notebooks" / "milestone3.ipynb", encoding="utf-8"))
SECTIONS = [
 ("Tarifs : le prix d'un camion", ["tranche_poids", "prix_camion", "prix_exceptionnel"]),
 ("Profils de livraison et calendrier", ["libelle_profil", "sous_ensembles", "generer_profils", "semaine_fermee", "dates_profil"]),
 ("Evaluation d'un profil pour un couple : programmation dynamique (version libre)", ["cout_exceptionnels", "evaluer_dp"]),
 ("Version intermediaire : semaines du profil respectees", ["semaines_du_profil", "objectif_semaines", "semaines_ok", "semaines_respectees", "lignes_dp", "evaluer_dp_inter"]),
 ("Couples aux jours trop lourds (methode approchee), version stricte, ancien comportement", ["evaluer_cap", "resultat_cap", "respectees_cap", "evaluer_cap_mode", "evaluer_strict", "evaluer_ancien", "charger_camions_vieux"]),
 ("Aiguillage et evaluation de tous les couples", ["evaluer_profil", "evaluer_tous"]),
 ("Etape 2 : le lissage dans la semaine (R4)", ["lissage", "charge_par_jour_semaine"]),
 ("Contenu des camions (sortie 2)", ["reconstruire", "construire_contenu"]),
 ("Validation de la solution", ["semaines_par_couple", "valider"]),
 ("Situation actuelle (baseline) d'un couple", ["cout_actuel_couple"]),
]
MODULE = {"en_jours", "semaine_de"}   # fonctions sans etat : restent hors de la classe
tout = [f for _, fs in SECTIONS for f in fs]
src_fn = {}
for c in nb["cells"]:
    if c["cell_type"] != "code": continue
    src = "".join(c["source"])
    try: tree = ast.parse(src)
    except SyntaxError: continue
    lignes = src.splitlines()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and (node.name in tout or node.name in MODULE):
            src_fn[node.name] = "\n".join(lignes[node.lineno - 1: node.end_lineno])
manque = [f for f in tout + sorted(MODULE) if f not in src_fn]
assert not manque, manque

ETAT = ["AVANCE_MAX", "BORNES", "CAP_POIDS", "CAP_VOLUME", "COUPLES", "COUPLES_CAP", "JOURS", "MIN_SEMAINES_RESPECTEES", "MODE_PROFIL",
        "PRIX_LIGNE", "SEM_PROFIL", "TRANCHES_KG", "UN_CAMION_PAR_JOUR", "DATES_PROFIL", "d0", "fermees", "jours_ouvres", "lundi0", "opt"]
NOMS = ETAT + tout
motif = re.compile(r"(?<![\w.\"'])(" + "|".join(sorted(NOMS, key=len, reverse=True)) + r")\b(?!\s*=(?!=))")

def reecrire(ligne):
    code, sep, com = ligne.partition("  #") if "  #" in ligne else (ligne, "", "")
    code = motif.sub(lambda m: "self." + m.group(1), code)
    return code + sep + com

def methode(nom):
    lignes = src_fn[nom].splitlines()
    # signature : ajouter self
    lignes[0] = re.sub(r"def (\w+)\(", r"def \1(self, ", lignes[0], count=1).replace("(self, )", "(self)")
    nouvelles = [lignes[0]] + [reecrire(l) for l in lignes[1:]]
    return "\n".join(("    " + l) if l.strip() else l for l in nouvelles)

corps = []
for titre, fs in SECTIONS:
    corps.append(f"    # {'-' * 70}\n    # {titre}\n    # {'-' * 70}\n")
    for f in fs:
        t = methode(f)
        if f == "valider":
            t = t.replace("mode=None, afficher=True):", "mode=None):")
            i = t.index("        if afficher:")
            t = t[:i] + "        return controles\n"
        corps.append(t + "\n")

cell15 = next("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code" and "def evaluer_dp(couple" in "".join(c["source"]))
init_txt = cell15[:cell15.index("def cout_exceptionnels")].strip("\n")
init_txt = "\n".join(l for l in init_txt.splitlines() if not l.startswith("# Nous preparons chaque couple"))
motif_init = re.compile(r"(?<![\w.\"'])(COUPLES_CAP|COUPLES|opt|CAP_POIDS|CAP_VOLUME)\b")
init_txt = "\n".join(motif_init.sub(lambda m: "self." + m.group(1), l) for l in init_txt.splitlines())
init_txt = "\n".join(("        " + l) if l.strip() else l for l in init_txt.splitlines())
modele = (RACINE / "outils" / "moteur_modele.txt").read_text(encoding="utf-8")
sortie = (modele.replace("#__FONCTIONS_MODULE__", src_fn["en_jours"] + "\n\n\n" + src_fn["semaine_de"])
                .replace("    #__METHODES__", "\n".join(corps)).replace("#__INIT_COUPLES__", init_txt))
# Les noms de la classe ont ete reecrits (self.X) jusque dans les phrases d'une docstring : on les remet en clair.
sortie = sortie.replace("self.MIN_SEMAINES_RESPECTEES, ou toutes", "MIN_SEMAINES_RESPECTEES, ou toutes")
cible = RACINE / "src" / "moteur.py"
if "--verifier" in sys.argv:                       # ne rien ecrire : dire seulement si src/moteur.py est a jour
    a_jour = cible.read_text(encoding="utf-8") == sortie
    print("src/moteur.py est a jour avec le notebook." if a_jour else
          "src/moteur.py n'est PLUS a jour : le moteur du notebook a change. Lancer : python outils/regenerer_moteur.py")
    sys.exit(0 if a_jour else 1)
cible.write_text(sortie, encoding="utf-8")
print("src/moteur.py regenere :", len(sortie.splitlines()), "lignes")
