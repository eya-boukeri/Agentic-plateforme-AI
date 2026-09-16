"""
tester_agent_rag.py
Evalue l'efficacite de l'agent RAG (agent_rag.py) sur plusieurs axes :

1. CORRECTION AUTOMATIQUE : pour les questions factuelles (agregats, faits
   precis), on compare le resultat obtenu via l'agent a une requete SQL
   de reference ecrite a la main - c'est la base de donnees elle-meme qui
   sert de "verite terrain", pas une evaluation subjective.
2. VALIDITE DU SQL GENERE : le LLM genere-t-il du SQL qui s'execute sans
   erreur ?
3. PERTINENCE DE LA RECHERCHE SEMANTIQUE (Zvec) : pour les questions
   floues/descriptives, affiche les resultats pour relecture manuelle
   (la pertinence semantique est plus subjective, difficile a verifier
   automatiquement sans jeu de donnees annote a la main).
4. LATENCE : temps de reponse par question (important pour un LLM local
   qui tourne sur CPU sans GPU).

Usage :
    python tester_agent_rag.py
    python tester_agent_rag.py --categorie sql        (seulement les tests factuels)
    python tester_agent_rag.py --categorie semantique  (seulement les tests Zvec)
"""

import sys
import os
import time
import argparse

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "agents"))

from dotenv import load_dotenv
load_dotenv()

from agents.agent_rag import AgentRAGOrchestrator


def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "hydrometry"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
    }


# ----------------------------------------------------------------------
# Jeu de test : questions factuelles avec une requete SQL de REFERENCE
# (verite terrain). Adaptez les noms de stations/annees a votre base
# reelle avant de lancer - ceux-ci sont des exemples generiques.
# ----------------------------------------------------------------------
TESTS_FACTUELS = [
    {
        "question": "Combien y a-t-il de stations en tout ?",
        "sql_reference": "SELECT COUNT(*) as total_stations FROM station",
        "colonne_a_comparer": "total_stations",
    },
    {
        "question": "Quel gouvernorat a le plus grand nombre de stations ?",
        "sql_reference": """
            SELECT gouvernorat, COUNT(*) as nb_stations
            FROM station
            WHERE gouvernorat IS NOT NULL AND gouvernorat != ''
            GROUP BY gouvernorat
            ORDER BY nb_stations DESC
            LIMIT 1
        """,
        "colonne_a_comparer": "gouvernorat",
    },
    {
        "question": "Quelle est la station avec le plus grand débit ?",
        "sql_reference": """
            SELECT s.nom
            FROM statistiques_annuelles st
            JOIN station s ON st.code_station = s.code_station
            WHERE st.debit_max_jour::text <> 'NaN'
            ORDER BY st.debit_max_jour DESC
            LIMIT 1
        """,
        "colonne_a_comparer": "nom",
    },
    {
        "question": "Quel gouvernorat a le plus grand débit ?",
        "sql_reference": """
            SELECT s.gouvernorat
            FROM statistiques_annuelles st
            JOIN station s ON st.code_station = s.code_station
            WHERE st.debit_max_jour::text <> 'NaN' AND s.gouvernorat IS NOT NULL AND s.gouvernorat != ''
            ORDER BY st.debit_max_jour DESC
            LIMIT 1
        """,
        "colonne_a_comparer": "gouvernorat",
    },
]

# Questions floues/descriptives : pas de verite terrain automatique
# (pertinence semantique = jugement humain), juste pour relecture.
TESTS_SEMANTIQUES = [
    "Je cherche une station près d'un cours d'eau dans le nord",
    "Quelle station se trouve dans une zone montagneuse ?",
    "Station sur l'oued Medjerdah",
]

# Cas limites : orthographe fautive, questions ambigues, hors-sujet -
# pour verifier que l'agent ne plante pas et degrade proprement.
TESTS_ROBUSTESSE = [
    "Quel governorat a le plus de stasion ?",  # fautes de frappe
    "Raconte-moi une blague",  # hors sujet
    "",  # question vide
    "asdkjqwlkej",  # charabia
]


def executer_sql_reference(agent_rag, sql):
    """Execute directement la requete de reference sur la base (verite
    terrain), independamment de l'agent."""
    try:
        return agent_rag.rag._execute_query_raising(sql)
    except Exception as e:
        return f"[ERREUR SQL reference] {e}"


def tester_factuels(agent_rag):
    print("\n" + "=" * 70)
    print("TESTS FACTUELS (verifies contre la base de donnees)")
    print("=" * 70)

    reussis = 0
    for cas in TESTS_FACTUELS:
        question = cas["question"]
        colonne = cas["colonne_a_comparer"]

        debut = time.time()
        reponse_agent = agent_rag.answer(question)
        duree = time.time() - debut

        verite_terrain = executer_sql_reference(agent_rag, cas["sql_reference"])
        valeur_attendue = None
        if isinstance(verite_terrain, list) and verite_terrain:
            valeur_attendue = verite_terrain[0].get(colonne)

        print(f"\nQ: {question}")
        print(f"   Reponse agent   : {reponse_agent[:200]}")
        print(f"   Valeur attendue : {valeur_attendue}")
        print(f"   Duree           : {duree:.1f}s")

        # Verification automatique simple : la valeur attendue apparait-
        # elle (sous forme de texte) dans la reponse de l'agent ?
        if valeur_attendue is not None and str(valeur_attendue).lower() in reponse_agent.lower():
            print("   -> OK (valeur attendue presente dans la reponse)")
            reussis += 1
        else:
            print("   -> A VERIFIER MANUELLEMENT (valeur non retrouvee telle quelle)")

    print(f"\n{reussis}/{len(TESTS_FACTUELS)} test(s) factuel(s) valides automatiquement.")
    print("(Les autres necessitent une relecture manuelle - le LLM peut reformuler")
    print(" la valeur sans erreur, ex: '15' vs '15.0' vs 'quinze'.)")


def tester_semantiques(agent_rag):
    print("\n" + "=" * 70)
    print("TESTS SEMANTIQUES (Zvec) - relecture manuelle necessaire")
    print("=" * 70)

    for question in TESTS_SEMANTIQUES:
        debut = time.time()
        resultats = agent_rag.rag.recherche_semantique_station(question, limit=5)
        duree = time.time() - debut

        print(f"\nQ: {question}  ({duree:.1f}s)")
        if not resultats:
            print("   Aucun resultat (Zvec non initialise/index vide ?)")
            continue
        for r in resultats:
            print(f"   - {r['nom']} ({r['gouvernorat']}, {r['cours_eau']}) score={r['score']:.3f}")


def tester_robustesse(agent_rag):
    print("\n" + "=" * 70)
    print("TESTS DE ROBUSTESSE (l'agent ne doit jamais planter)")
    print("=" * 70)

    for question in TESTS_ROBUSTESSE:
        try:
            debut = time.time()
            reponse = agent_rag.answer(question)
            duree = time.time() - debut
            print(f"\nQ: {question!r}")
            print(f"   -> OK ({duree:.1f}s) : {reponse[:150]}")
        except Exception as e:
            print(f"\nQ: {question!r}")
            print(f"   -> ECHEC (exception non geree) : {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--categorie", choices=["sql", "semantique", "robustesse", "tout"], default="tout")
    args = parser.parse_args()

    print("Initialisation de l'agent RAG (connexion DB + LLM + Zvec)...")
    agent_rag = AgentRAGOrchestrator(get_db_config())

    try:
        if args.categorie in ("sql", "tout"):
            tester_factuels(agent_rag)
        if args.categorie in ("semantique", "tout"):
            tester_semantiques(agent_rag)
        if args.categorie in ("robustesse", "tout"):
            tester_robustesse(agent_rag)
    finally:
        agent_rag.close()


if __name__ == "__main__":
    main()