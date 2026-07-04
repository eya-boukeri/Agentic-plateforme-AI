"""
scripts/import_access_to_postgres.py
Importation Access → PostgreSQL (depuis Windows)
"""

import pyodbc
import pandas as pd
from sqlalchemy import create_engine, text
import os
import re

# ============================================================
# CONFIGURATION
# ============================================================

# Fichier Access
ACCESS_FILE = r"C:\Users\Admin\Desktop\stage\2019_2020.mdb"

# PostgreSQL
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "hydrometry"
DB_USER = "postgres"
DB_PASSWORD = "postgres"

# ============================================================
# FONCTIONS
# ============================================================

def get_access_connection():
    """Connexion à Access"""
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb)};"
        f"DBQ={ACCESS_FILE};"
    )
    return pyodbc.connect(conn_str)

def get_postgres_engine():
    """Connexion à PostgreSQL"""
    return create_engine(
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

def clean_table_name(table_name):
    """Nettoie le nom de la table"""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', table_name)
    return clean.lower()

def import_table(access_conn, pg_engine, table_name):
    """Importe une table Access dans PostgreSQL"""
    print(f"\n📥 Importation : {table_name}")
    print("-" * 50)
    
    try:
        df = pd.read_sql(f"SELECT * FROM [{table_name}]", access_conn)
        print(f"   ✅ {len(df)} lignes lues")
        
        if df.empty:
            print("   ⚠️  Table vide")
            return False
        
        table_clean = clean_table_name(table_name)
        
        with pg_engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_clean} CASCADE"))
            conn.commit()
        
        df.to_sql(table_clean, pg_engine, if_exists='replace', index=False)
        print(f"   ✅ {len(df)} lignes importées dans {table_clean}")
        return True
        
    except Exception as e:
        print(f"   ❌ Erreur : {e}")
        return False

def main():
    print("\n" + "=" * 60)
    print("📥 IMPORTATION ACCESS → POSTGRESQL")
    print("=" * 60)
    
    if not os.path.exists(ACCESS_FILE):
        print(f"❌ Fichier Access non trouvé : {ACCESS_FILE}")
        return
    
    access_conn = get_access_connection()
    pg_engine = get_postgres_engine()
    
    print("✅ Connexions établies")
    
    tables = [
        "Stations_Base",
        "Debits",
        "Cotes",
        "Dossiers_Stations",
        "Etal_HQ",
        "Etal_HK",
        "Jaugeages",
        "Pluies",
        "Codes_Nature",
        "Codes_Origine",
        "Codes_Qualite",
        "Bassins",
        "Regions",
        "Rivieres",
        "Capteurs",
        "Equipements"
    ]
    
    print("\n📋 Tables à importer :")
    for t in tables:
        print(f"   - {t}")
    
    imported = 0
    for table in tables:
        if import_table(access_conn, pg_engine, table):
            imported += 1
    
    access_conn.close()
    
    print("\n" + "=" * 60)
    print(f"✅ Importation terminée : {imported}/{len(tables)} tables importées")
    print("=" * 60)

if __name__ == "__main__":
    main()