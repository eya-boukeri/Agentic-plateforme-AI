# 🌊 Plateforme Agentic AI - Annuaire Hydrométrique de Tunisie (DGRE)

Plateforme d'intelligence artificielle agentique dédiée à la gestion, l'analyse et l'exploitation des données hydrométriques nationales de la Tunisie (Direction Générale des Ressources en Eau - DGRE).

---

## 📋 Prérequis

Pour exécuter cette plateforme sur n'importe quel ordinateur (Windows, macOS ou Linux), l'utilisateur doit simplement avoir :

1. **[Git](https://git-scm.com/)** installé.
2. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** installé et **démarré** (avec au moins 8 Go de RAM alloués dans les réglages Docker pour faire tourner confortablement le modèle d'IA).

> [!NOTE]
> Aucun environnement Python, PostgreSQL ou Ollama n'a besoin d'être installé manuellement sur la machine hôte : tout est entièrement géré par Docker !

---

## 🚀 Démarrage rapide (En 3 étapes)

### 1. Cloner le projet
Ouvrez un terminal (PowerShell, Invite de commandes ou Bash) et exécutez :

```bash
git clone https://github.com/eya-boukeri/Agentic-plateforme-AI.git
cd Agentic-plateforme-AI
```

### 2. Lancer la plateforme
Exécutez la commande suivante :

```bash
docker compose up -d
```

#### Ce qui se passe automatiquement en arrière-plan :
- 📥 **Application Streamlit** : Docker télécharge automatiquement l'image pré-compilée depuis Docker Hub (`eya0503/hydrometrie-app:latest`).
- 🐘 **PostgreSQL 16** : Démarre et initialise automatiquement les tables et schémas hydrométriques via `scripts/init_db.sql`.
- 🤖 **Serveur IA (Ollama)** : Démarre et prépare automatiquement :
  - Le modèle d'embeddings vectoriels pour le RAG (`nomic-embed-text`).
  - Le modèle expert hydrométrique personnalisé (`hydrometrie`) via le `Modelfile`.
- 🖥️ **pgAdmin 4** : Démarre l'interface d'administration de la base de données.

---

## 🌐 3. Accéder aux services

Une fois les conteneurs démarrés, ouvrez votre navigateur web :

| Service | URL | Identifiants |
| :--- | :--- | :--- |
| **Application Web (Streamlit)** | [http://localhost:8501](http://localhost:8501) | *Accès direct sans identifiant* |
| **Administration BDD (pgAdmin)** | [http://localhost:5050](http://localhost:5050) | Email : `admin@hydrology.com`<br>Mot de passe : `admin` |
| **API Serveur LLM (Ollama)** | [http://localhost:11435](http://localhost:11435) | *API HTTP interne/externe* |

---

## 💬 Utilisation de la plateforme

L'application propose deux grands espaces :

### 1. Le Tableau de Bord National (Dashboard)
- **KPIs nationaux** : nombre de stations actives, débits moyens, crues récentes enregistrées.
- **Cartographie interactive** : visualisation géographique des cours d'eau, stations hydrométriques, limites régionales et barrages de Tunisie.
- **Analyses et graphiques** : répartition des débits par région et suivi des régimes hydrologiques.

### 2. L'Assistant IA (Chat en langage naturel)
L'assistant est piloté par l'**AgentOrchestrator** et le modèle LLM finetuné **hydrometrie**. Vous pouvez lui poser des questions ou lui donner des ordres comme :
- *"Donne-moi la liste des stations du bassin de la Medjerda."*
- *"Quelle est la crue maximale enregistrée à la station de Jendouba ?"*
- *"Génère l'annuaire hydrométrique complet en PDF pour l'année 2024."*
- *"Affiche la carte des stations du gouvernorat de Bizerte."*

---

## 🛠️ Commandes utiles au quotidien

### Suivre les journaux en direct (Logs)
```bash
# Logs de l'application Streamlit
docker compose logs -f app

# Logs du serveur IA Ollama
docker compose logs -f ollama
```

### Arrêter la plateforme
```bash
# Arrêter les services en conservant les données
docker compose stop

# Arrêter et libérer complètement les conteneurs
docker compose down
```

### Relancer la plateforme ultérieurement
```bash
docker compose up -d
```

---

## ❓ FAQ & Dépannage

- **Erreur : *port is already allocated* (Port déjà utilisé)** :  
  Si le port `8501` ou `5432` est déjà utilisé par un autre logiciel sur votre machine, vérifiez qu'aucune ancienne instance de PostgreSQL ou de Streamlit n'est en cours d'exécution.
- **Temps de premier démarrage** :  
  Le tout premier lancement nécessite le téléchargement des images et des poids du modèle d'IA. Prévoyez quelques minutes selon la vitesse de votre connexion internet. Les démarrages suivants seront instantanés.
