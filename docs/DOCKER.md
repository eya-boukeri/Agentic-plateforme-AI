# 🐳 Guide Docker - Plateforme Agentic AI Hydrométrie

Ce document explique comment conteneuriser, construire et exécuter l'application **Annuaire Hydrométrique de Tunisie (DGRE)** avec Docker et Docker Compose.

---

## 📋 Prérequis

1. **Docker Desktop** installé et **démarré** sur votre machine.
2. (Optionnel mais recommandé pour l'IA) : **Ollama** installé sur la machine hôte avec le modèle hydrométrique ou llama :
   ```bash
   ollama run hydrometrie
   ```

---

## 🚀 Option 1 : Déploiement complet avec Docker Compose (Recommandé)

Docker Compose orchestre automatiquement :
- **PostgreSQL 16** (avec initialisation automatique des schémas hydrométriques via `scripts/init_db.sql`).
- **pgAdmin 4** (interface d'administration accessible sur `http://localhost:5050`).
- **Ollama** (serveur LLM autonome avec téléchargement automatique de `nomic-embed-text` et création du modèle `hydrometrie` via le `Modelfile`).
- **L'application Streamlit & Agents IA** (accessible sur `http://localhost:8501`).

### 1. Démarrer tous les services :
```powershell
docker compose up --build -d
```

### 2. Accéder aux services :
- **Application Web (Streamlit)** : [http://localhost:8501](http://localhost:8501)
- **pgAdmin (Gestion base de données)** : [http://localhost:5050](http://localhost:5050)
  - Identifiant : `admin@hydrology.com`
  - Mot de passe : `admin`

### 3. Voir les journaux en direct :
```powershell
docker compose logs -f app
```

### 4. Arrêter les services :
```powershell
docker compose down
```

---

## 🛠️ Option 2 : Construire et exécuter l'image Docker seule

Si vous avez déjà une base PostgreSQL et souhaitez exécuter uniquement l'image de l'application :

### 1. Construire l'image Docker :
```powershell
docker build -t hydrometrie-app .
```

### 2. Lancer le conteneur :
```powershell
docker run -d `
  --name hydrometrie_container `
  -p 8501:8501 `
  -e DB_HOST=host.docker.internal `
  -e DB_PORT=5432 `
  -e DB_NAME=hydrometry `
  -e DB_USER=postgres `
  -e DB_PASSWORD=postgres `
  -e LLM_HOST=http://host.docker.internal:11434 `
  -v ${PWD}/data:/app/data `
  -v ${PWD}/output:/app/output `
  hydrometrie-app
```

---

## ⚙️ Détails techniques de l'image Docker

- **Image de base** : `python:3.11-slim-bookworm` (Debian 12, stable, légère et sécurisée).
- **Dépendances système intégrées** :
  - `mdbtools` : Pour l'import et la lecture des bases Microsoft Access (`.mdb` / `.accdb`).
  - `libpq-dev` & `gcc` : Pour les pilotes PostgreSQL (`psycopg2-binary`, `SQLAlchemy`).
  - `curl` : Pour le healthcheck automatique du conteneur Streamlit.
  - `dos2unix` : Pour garantir la compatibilité des scripts shell sous Windows.
- **Actifs inclus** : Cartes GeoJSON régionales, Modèle Numérique de Terrain (MNT), logos institutionnels DGRE, index vectoriel Zvec.
- **Persistance** : Les dossiers `/app/data` et `/app/output` peuvent être montés en volumes pour conserver les rapports PDF générés et les nouveaux imports.

---

## ☁️ Option 3 : Publier (Push) l'image sur Docker Hub

Pour partager ou déployer votre image sur un serveur distant via **Docker Hub** :

### 1. Se connecter à Docker Hub
Dans votre terminal :
```powershell
docker login
```
*Entrez votre nom d'utilisateur Docker Hub et votre mot de passe (ou Personal Access Token).*

### 2. Construire et taguer l'image avec votre nom d'utilisateur
Le format obligatoire d'un tag Docker Hub est : `<votre_nom_utilisateur>/<nom_image>:<tag>`

```powershell
# Exemple en remplaçant 'monuser' par votre identifiant Docker Hub :
docker build -t monuser/hydrometrie-app:latest -t monuser/hydrometrie-app:1.0 .
```
*(Ou si l'image locale `hydrometrie-app` est déjà construite : `docker tag hydrometrie-app monuser/hydrometrie-app:latest`)*

### 3. Pousser l'image vers Docker Hub
```powershell
docker push monuser/hydrometrie-app:latest
docker push monuser/hydrometrie-app:1.0
```

### 4. Télécharger et exécuter sur n'importe quel serveur
Une fois l'image publiée, elle peut être téléchargée n'importe où sans le code source :
```powershell
docker run -d -p 8501:8501 monuser/hydrometrie-app:latest
```
