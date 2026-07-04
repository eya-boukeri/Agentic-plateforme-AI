"""
scripts/verify_import.py
Vérification de l'importation des données
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

def verify_import():
    """Vérifie les données importées"""
    print("\n" + "="*60)
    print("🔍 VÉRIFICATION DE L'IMPORTATION")
    print("="*60)
    
    # Connexion PostgreSQL
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'hydrometry'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', '')
    )
    
    cursor = conn.cursor()
    
    # 1. Lister les tables
    print("\n📋 Tables dans PostgreSQL :")
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    
    tables = cursor.fetchall()
    for row in tables:
        print(f"   - {row[0]}")
    
    # 2. Compter les lignes
    print("\n📊 Nombre de lignes :")
    for table in ['stations', 'hauteurs_brutes', 'debits_journaliers_bruts', 'courbes_tarage']:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"   - {table}: {count} lignes")
    
    # 3. Aperçu des stations
    print("\n🏛️ Stations (aperçu) :")
    cursor.execute("SELECT code_station, nom, cours_eau, bassin FROM stations LIMIT 5")
    for row in cursor.fetchall():
        print(f"   {row[0]} | {row[1]} | {row[2]} | {row[3]}")
    
    # 4. Aperçu des hauteurs
    print("\n📊 Hauteurs (aperçu) :")
    cursor.execute("SELECT code_station, date_heure, hauteur_cm FROM hauteurs_brutes LIMIT 5")
    for row in cursor.fetchall():
        print(f"   {row[0]} | {row[1]} | {row[2]}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print("✅ Vérification terminée")
    print("="*60)

if __name__ == "__main__":
    verify_import()