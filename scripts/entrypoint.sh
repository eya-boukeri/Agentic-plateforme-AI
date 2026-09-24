#!/bin/bash
set -e

echo "🌊 Initialisation du conteneur Hydrométrie..."

# Paramètres de base de données depuis les variables d'environnement
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-hydrometry}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"
SKIP_DB_CHECK="${SKIP_DB_CHECK:-false}"

if [ "$SKIP_DB_CHECK" != "true" ] && [ -n "$DB_HOST" ]; then
    echo "📦 Vérification de la disponibilité de PostgreSQL ($DB_HOST:$DB_PORT)..."
    max_retries=30
    counter=0
    
    until python3 -c "
import psycopg2, os, sys
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', '$DB_HOST'),
        port=int(os.getenv('DB_PORT', '$DB_PORT')),
        dbname=os.getenv('DB_NAME', '$DB_NAME'),
        user=os.getenv('DB_USER', '$DB_USER'),
        password=os.getenv('DB_PASSWORD', '$DB_PASSWORD'),
        connect_timeout=3
    )
    conn.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
"; do
        counter=$((counter + 1))
        if [ $counter -ge $max_retries ]; then
            echo "⚠️ Attention : PostgreSQL ($DB_HOST:$DB_PORT) n'a pas répondu après $max_retries tentatives. Poursuite du démarrage..."
            break
        fi
        echo "⏳ En attente de PostgreSQL... (${counter}/${max_retries})"
        sleep 2
    done
    
    if [ $counter -lt $max_retries ]; then
        echo "✅ Connexion PostgreSQL validée !"
    fi
fi

echo "🚀 Lancement de l'application..."
exec "$@"