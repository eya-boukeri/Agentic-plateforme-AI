"""
chercher_station.py
Cherche des stations par mot-cle dans `station` et `stations_base`, pour
verifier/corriger manuellement une correspondance douteuse avant import.

Usage :
    python chercher_station.py Tine
    python chercher_station.py Lahmar
    python chercher_station.py "Oued Beja"
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

if len(sys.argv) < 2:
    print("Usage : python chercher_station.py <mot-cle>")
    sys.exit(1)

mot_cle = sys.argv[1]

db_url = URL.create(
    "postgresql+psycopg2",
    username=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "postgres"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    database=os.getenv("DB_NAME", "hydrometry"),
)
engine = create_engine(db_url, connect_args={"client_encoding": "utf8"})

print(f"\nRecherche '{mot_cle}' dans 'station' (par nom) :")
try:
    df = pd.read_sql(
        "SELECT code_station, nom, cours_eau, gouvernorat FROM station WHERE nom ILIKE %(k)s",
        engine, params={"k": f"%{mot_cle}%"}
    )
    print(df.to_string(index=False) if not df.empty else "  (aucun resultat)")
except Exception as e:
    print("  Erreur :", e)

print(f"\nRecherche '{mot_cle}' dans 'station' (par cours d'eau) :")
try:
    df = pd.read_sql(
        "SELECT code_station, nom, cours_eau, gouvernorat FROM station WHERE cours_eau ILIKE %(k)s",
        engine, params={"k": f"%{mot_cle}%"}
    )
    print(df.to_string(index=False) if not df.empty else "  (aucun resultat)")
except Exception as e:
    print("  Erreur :", e)

print(f"\nRecherche '{mot_cle}' dans 'stations_base' :")
try:
    df = pd.read_sql(
        'SELECT "Id_Station", "Nom" FROM stations_base WHERE "Nom" ILIKE %(k)s',
        engine, params={"k": f"%{mot_cle}%"}
    )
    print(df.to_string(index=False) if not df.empty else "  (aucun resultat)")
except Exception as e:
    print("  Erreur :", e)

print(f"\nParmi ces codes, lesquels ont deja des donnees dans 'debits' :")
try:
    tous_codes = set()
    requetes = [
        ("station", "code_station", "nom"),
        ("stations_base", '"Id_Station"', '"Nom"'),
    ]
    for tbl, code_col, nom_col in requetes:
        try:
            q = f"SELECT DISTINCT {code_col} AS code FROM {tbl} WHERE {nom_col} ILIKE %(k)s"
            d = pd.read_sql(q, engine, params={"k": f"%{mot_cle}%"})
            tous_codes.update(d["code"].astype(str).tolist())
        except Exception:
            pass
    if tous_codes:
        placeholders = ",".join([f"'{c}'" for c in tous_codes])
        d = pd.read_sql(
            f'SELECT "Id_Station", COUNT(*) AS nb_lignes, MIN("Date") AS premiere_date, MAX("Date") AS derniere_date '
            f'FROM debits WHERE "Id_Station" IN ({placeholders}) GROUP BY "Id_Station"',
            engine
        )
        print(d.to_string(index=False) if not d.empty else "  (aucun de ces codes n'a de donnees dans 'debits' actuellement)")
    else:
        print("  (aucun code a verifier)")
except Exception as e:
    print("  Erreur :", e)