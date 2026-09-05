"""
diagnostiquer_crues_station.py
Affiche toutes les crues detectees pour une station/annee donnee, triees
par debit de pointe decroissant - pour verifier si la "crue principale"
choisie par _plot_hydrogramme_crue_principale est vraiment la plus grosse,
et repérer d'eventuels faux positifs (crues trop breves/trop faibles).

Usage :
    python diagnostiquer_crues_station.py 1485900188 2024
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


def main():
    if len(sys.argv) < 3:
        print("Usage : python diagnostiquer_crues_station.py <code_station> <annee>")
        sys.exit(1)

    code_station = sys.argv[1]
    annee = int(sys.argv[2])

    db_url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "hydrometry"),
    )
    engine = create_engine(db_url, connect_args={"client_encoding": "utf8"})

    df = pd.read_sql(
        """
        SELECT date_debut, date_fin, temps_base_min, debit_debut, debit_fin,
               debit_max_m3s, volume_ecoule_hm3
        FROM crues
        WHERE code_station = %(code)s AND annee = %(annee)s
        ORDER BY debit_max_m3s DESC
        """,
        engine, params={"code": code_station, "annee": annee}
    )

    if df.empty:
        print(f"Aucune crue trouvee pour {code_station} / {annee}.")
        return

    pd.set_option("display.width", 200)
    print(f"\n{len(df)} crue(s) trouvee(s) pour {code_station} / {annee}, triees par debit de pointe :\n")
    print(df.to_string(index=False))

    print("\n--- La 'crue principale' actuellement choisie pour l'hydrogramme est la 1ere ligne ci-dessus. ---")

    # Comparaison rapide avec le debit journalier max de l'annee (pour reperer
    # si un pic plus fort existe dans les debits mais n'a pas ete detecte
    # comme une crue distincte)
    debits = pd.read_sql(
        """
        SELECT "Date", "Valeur" FROM debits
        WHERE "Id_Station" = %(code)s
          AND "Date" >= %(debut)s AND "Date" < %(fin)s
        ORDER BY "Valeur" DESC LIMIT 5
        """,
        engine, params={"code": code_station, "debut": f"{annee}-09-01", "fin": f"{annee+1}-09-01"}
    )
    print("\nTop 5 des debits instantanes les plus eleves de l'annee (dans `debits`) :")
    print(debits.to_string(index=False))


if __name__ == "__main__":
    main()