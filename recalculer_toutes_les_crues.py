"""
recalculer_toutes_les_crues.py
Recalcule et reecrit les crues (table `crues`) pour TOUTES les stations
et TOUTES les annees presentes dans la base, avec la version corrigee
de calculer_crues (fusion des segments proches, filtre de duree/marge).

Ne touche pas aux debits journaliers ni aux statistiques annuelles
(plus rapide que de tout retraiter via traiter_annee).

Usage :
    python recalculer_toutes_les_crues.py
    python recalculer_toutes_les_crues.py --annee 2019          # une seule annee
    python recalculer_toutes_les_crues.py --station 1485900188  # une seule station
"""

import sys
import os
import argparse

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from dotenv import load_dotenv
load_dotenv()

from agents.agent_calcul import AgentCalcul


def get_stations_annees(agent, only_station=None, only_annee=None):
    """Retourne la liste des couples (id_station, annee) presents dans `debits`."""
    cursor = agent.conn.cursor()
    query = 'SELECT DISTINCT "Id_Station", EXTRACT(YEAR FROM "Date")::int AS annee FROM debits'
    conditions = []
    params = []
    if only_station:
        conditions.append('"Id_Station" = %s')
        params.append(only_station)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += ' ORDER BY 1, 2'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()

    paires = [(id_station, int(annee_brute)) for id_station, annee_brute in rows]

    # L'annee "hydrologique" commence le 1er septembre : une ligne datee de
    # janvier-aout appartient a l'annee hydro precedente. On deduplique donc
    # sur (station, annee_hydro-1) ET (station, annee_hydro) pour ne rien
    # manquer, calculer_crues() se chargeant lui-meme de fenetrer correctement.
    candidats = set()
    for id_station, annee in paires:
        candidats.add((id_station, annee))
        candidats.add((id_station, annee - 1))

    if only_annee is not None:
        candidats = {(s, a) for s, a in candidats if a == only_annee}

    return sorted(candidats)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--annee", type=int, default=None)
    parser.add_argument("--station", type=str, default=None)
    args = parser.parse_args()

    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "hydrometry"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
    }

    agent = AgentCalcul(db_config=db_config)
    recap = []
    try:
        paires = get_stations_annees(agent, only_station=args.station, only_annee=args.annee)
        print(f"\n{len(paires)} couple(s) station/annee a traiter.\n")

        for id_station, annee in paires:
            try:
                df_crues = agent.calculer_crues(id_station, annee)
                nb = 0 if df_crues is None else len(df_crues)
                if nb == 0:
                    continue  # rien a sauvegarder / pas de donnees cette annee-la
                agent.sauvegarder_crues(id_station, annee, df_crues)
                print(f"[OK] {id_station} / {annee} : {nb} crue(s)")
                recap.append((id_station, annee, nb))
            except Exception as e:
                print(f"[ERREUR] {id_station} / {annee} : {e!r}")

        print("\n" + "=" * 60)
        print(f"TERMINE : {len(recap)} station/annee mises a jour avec des crues.")
        print("=" * 60)
        for id_station, annee, nb in recap:
            print(f"  {id_station:20s} {annee}  -> {nb} crue(s)")

    finally:
        agent.close()


if __name__ == "__main__":
    main()