# Dockerfile
# Image de base Python 3.11 (stable)
FROM python:3.11-slim-bookworm

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# Définir le répertoire de travail
WORKDIR /app

# Installer les dépendances système
RUN apt-get update -o Acquire::Retries=3 && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements.txt et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier tout le code source
COPY src/ ./src/
COPY config/ ./config/
COPY tests/ ./tests/
COPY scripts/ ./scripts/

# Créer les dossiers pour les données
RUN mkdir -p data/raw data/processed data/metadata output/pdf output/logs output/maps output/graphs

# Copier le script d'entrypoint
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Commande par défaut
CMD ["python", "-c", "print('✅ Application prête !')"]