# ============================================================
# Dockerfile - Plateforme Agentic AI - Annuaire Hydrométrique (DGRE)
# ============================================================
FROM python:3.11-slim-bookworm

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Dépendances système :
# - gcc, g++, libpq-dev : compilation psycopg2 et extensions C
# - curl : pour le healthcheck Docker
# - mdbtools : extraction des fichiers MS Access (.mdb/.accdb)
# - libexpat1 : gestion XML
# - dos2unix : conversion des fins de ligne Windows (CRLF -> LF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    mdbtools \
    libexpat1 \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier les sources, configurations, scripts et données de référence
COPY src/ ./src/
COPY config/ ./config/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Créer les dossiers de travail et sorties
RUN mkdir -p data/raw data/processed output/pdf output/logs output/maps output/graphs

# Rendre l'entrypoint exécutable et convertir d'éventuels retours CRLF
RUN dos2unix ./scripts/entrypoint.sh && chmod +x ./scripts/entrypoint.sh

# Port Streamlit
EXPOSE 8501

# Vérification d'état de santé du conteneur
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Commande de démarrage par défaut : Streamlit
CMD ["python", "-m", "streamlit", "run", "src/app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]