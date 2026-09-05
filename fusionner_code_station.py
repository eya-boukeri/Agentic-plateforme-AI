"""
fusionner_code_station.py
Corrige un code_station incoherent entre `station` et `stations_base` en
migrant TOUTES les tables liees (station, debits, crues,
statistiques_annuelles, anomalies) vers le code correct, dans une seule
transaction (tout ou rien).

Cas d'usage concret : "LAHMAR GP5" existe avec le code 1485802270 dans
`station` mais 1485802221 dans `stations_base` (le code faisant reellement
foi puisque c'est celui utilise pour lier aux donnees Access importees).
Sans cette migration, les 33029 lignes de debits deja liees a l'ancien code
resteraient orphelines une fois `station` corrige.

Usage :
    python fusionner_code_station.py 1485802270 1485802221
    (ancien_code, nouveau_code)

Par defaut en mode verification (affiche ce qui serait fait). Ajoutez
--confirmer pour executer reellement la migration.
"""

import sys
import os
import argparse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


def get_engine():
    db_url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "hydrometry"),
    )
    return create_engine(db_url, connect_args={"client_encoding": "utf8"})


# (nom_table, colonne_code, nom_colonne_affichee)
TABLES_A_MIGRER = [
    ("station", "code_station", "code_station"),
    ("debits", '"Id_Station"', "Id_Station"),
    ("crues", "code_station", "code_station"),
    ("statistiques_annuelles", "code_station", "code_station"),
    ("anomalies", "code_station", "code_station"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ancien_code")
    parser.add_argument("nouveau_code")
    parser.add_argument("--confirmer", action="store_true")
    args = parser.parse_args()

    engine = get_engine()

    print(f"Migration : {args.ancien_code!r} -> {args.nouveau_code!r}\n")
    print("Etat actuel (nombre de lignes concernees par table) :")
    total_lignes = 0
    for table, colonne, label in TABLES_A_MIGRER:
        try:
            df = pd.read_sql(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {colonne} = %(c)s",
                engine, params={"c": args.ancien_code}
            )
            n = int(df.iloc[0]["n"])
            print(f"  {table:25s} ({label}) : {n} ligne(s) avec l'ancien code")
            total_lignes += n
        except Exception as e:
            print(f"  {table:25s} : table absente ou erreur ({e})")

    # Verifie aussi qu'on ne va pas creer de doublon (ancien+nouveau code
    # deja tous les deux presents avec des donnees qui se chevauchent)
    print("\nVerification des conflits potentiels avec le nouveau code :")
    for table, colonne, label in TABLES_A_MIGRER:
        try:
            df = pd.read_sql(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {colonne} = %(c)s",
                engine, params={"c": args.nouveau_code}
            )
            n = int(df.iloc[0]["n"])
            if n > 0:
                print(f"  [ATTENTION] {table} a deja {n} ligne(s) sous le nouveau code "
                      f"{args.nouveau_code!r} -> verifiez qu'il n'y a pas de doublon de dates.")
        except Exception:
            pass

    if total_lignes == 0:
        print("\nRien a migrer (aucune ligne trouvee avec l'ancien code).")
        return

    if not args.confirmer:
        print(f"\n[Mode verification uniquement] {total_lignes} ligne(s) seraient migrees au total.")
        print("Relancez avec --confirmer pour executer la migration.")
        return

    print("\nExecution de la migration (transaction unique)...")
    with engine.begin() as conn:  # commit automatique si tout reussit, rollback sinon
        for table, colonne, label in TABLES_A_MIGRER:
            try:
                result = conn.execute(
                    text(f"UPDATE {table} SET {colonne} = :nouveau WHERE {colonne} = :ancien"),
                    {"nouveau": args.nouveau_code, "ancien": args.ancien_code}
                )
                print(f"  {table:25s} : {result.rowcount} ligne(s) mise(s) a jour")
            except Exception as e:
                print(f"  [ERREUR] {table} : {e}")
                raise  # provoque le rollback de toute la transaction

    print("\n[OK] Migration terminee avec succes (transaction validee).")


if __name__ == "__main__":
    main()