#!/bin/bash
echo "🚀 Démarrage de l'application..."
echo "📦 Attente de PostgreSQL..."

max_retries=30
counter=0

while true; do
    counter=$((counter + 1))
    if [ $counter -ge $max_retries ]; then
        echo "❌ PostgreSQL n'est pas disponible après $max_retries tentatives"
        exit 1
    fi
    
    # Tester la connexion avec psycopg2
    python3 -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='postgres',
        port=5432,
        database='hydrometry',
        user='postgres',
        password='postgres'
    )
    conn.close()
    exit(0)
except Exception as e:
    exit(1)
" && break
    
    echo "⏳ En attente de PostgreSQL... (${counter}/${max_retries})"
    sleep 2
done

echo "✅ PostgreSQL est prêt !"
exec "$@"