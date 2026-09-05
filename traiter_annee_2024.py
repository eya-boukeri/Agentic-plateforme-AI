"""
traiter_annee_2024.py
Calcule les debits journaliers, statistiques annuelles et crues pour TOUTES
les stations de l'annee 2024 (necessaire une seule fois apres l'import des
nouveaux debits, avant de pouvoir generer l'annuaire 2024).

Usage :
    python traiter_annee_2024.py
    python traiter_annee_2024.py --annee 2024   (par defaut 2024)
"""

import sys
import os
import argparse

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from dotenv import load_dotenv
load_dotenv()

from agents.agent_calcul import AgentCalcul


def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "hydrometry"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--annee", type=int, default=2024)
    args = parser.parse_args()

    agent = AgentCalcul(db_config=get_db_config())
    try:
        print(f"Traitement complet de l'annee {args.annee} (debits/statistiques/crues)...")
        agent.traiter_annee(args.annee)
        print(f"\n[OK] Annee {args.annee} traitee. Vous pouvez maintenant generer l'annuaire {args.annee}.")
    finally:
        agent.close()


if __name__ == "__main__":
    main()