# Projet IA — Consolidation des livraisons

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
jupyter lab
```

**Option 2 — Docker**
```bash
docker build -t projet-ia .
docker run --rm -p 8888:8888 -v "$PWD":/app projet-ia
```
Puis ouvrir http://127.0.0.1:8888/lab

## Règles
- Ne jamais modifier `data/` à la main.
- Nouvelle bibliothèque → l'ajouter dans `requirements.txt` avec sa version.
