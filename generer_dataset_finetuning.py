"""
generer_dataset_finetuning.py
VERSION HYBRIDE :
- Actions FIXES (annuaire, PDF partiel, carte hydrometrique, recalcul) :
  appel d'outil structure <tool_call>{"name":...,"arguments":{...}}</tool_call>,
  valide contre un schema JSON, execute par du code deja teste/sur.
- Graphiques LIBRES/personnalises (non couverts par un outil fixe) :
  le modele repond DIRECTEMENT avec le code Python complet, executable,
  sans wrapper JSON - comme le fait un projet de reference examine
  (dataset_mixed_clean.jsonl, generation de cartes isohyetes). Aucun outil
  fixe ne peut couvrir la diversite infinie des graphiques possibles ;
  laisser le modele ecrire le code est le bon niveau de flexibilite ici,
  la ou pour les actions fixes ca ajouterait un risque inutile
  (hallucination de code touchant PDF/base plutot qu'un simple argument
  JSON valide-able avant execution).

Usage :
    python generer_dataset_finetuning.py --sortie dataset_finetuning.jsonl
"""

import sys
import os
import json
import random
import argparse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


OUTILS = [
    {
        "name": "generer_annuaire",
        "description": "Genere l'annuaire hydrometrique PDF complet pour une annee donnee.",
        "parameters": {
            "type": "object",
            "properties": {
                "annee": {"type": "integer", "description": "Annee hydrologique (ex: 2024)"}
            },
            "required": ["annee"]
        }
    },
    {
        "name": "generer_pdf_periode",
        "description": "Genere un PDF partiel de l'annuaire pour une periode de quelques mois "
                        "au lieu de l'annee complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "annee": {"type": "integer"},
                "mois_debut": {"type": "integer", "description": "1=Janvier ... 12=Decembre"},
                "mois_fin": {"type": "integer"}
            },
            "required": ["annee", "mois_debut", "mois_fin"]
        }
    },
    {
        "name": "generer_carte_hydrometrique",
        "description": "Genere une carte du reseau hydrometrique (stations, cours d'eau, "
                        "relief) pour un gouvernorat ou pour toute la Tunisie, sur une "
                        "periode donnee.",
        "parameters": {
            "type": "object",
            "properties": {
                "zone": {"type": "string", "description": "Nom du gouvernorat, ou 'Tunisie' pour le pays entier"},
                "nb_mois_precedents": {"type": "integer", "description": "Nombre de mois precedents a couvrir"}
            },
            "required": ["zone"]
        }
    },
    {
        "name": "recalculer_statistiques",
        "description": "Recalcule les debits journaliers, statistiques annuelles et crues "
                        "pour une annee donnee (a utiliser apres l'insertion de nouvelles "
                        "donnees de debit pour cette annee).",
        "parameters": {
            "type": "object",
            "properties": {
                "annee": {"type": "integer"}
            },
            "required": ["annee"]
        }
    },
    {
        "name": "repondre_question_donnees",
        "description": "Repond a une question factuelle sur les donnees hydrometriques "
                        "deja calculees (debits, crues, statistiques, stations) sans "
                        "generer de fichier.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string"}
            },
            "required": ["question"]
        }
    },
]

SYSTEME = (
    "Tu es l'assistant agentic de la DGRE pour l'annuaire hydrometrique de la Tunisie. "
    "Tu reponds aux questions sur les donnees hydrometriques (debits, crues, statistiques, "
    "stations) et tu peux declencher des actions via les outils disponibles (generation de "
    "PDF, de cartes, recalcul de statistiques). Reponds toujours en francais.\n\n"
    "Pour un GRAPHIQUE LIBRE ou PERSONNALISE (non couvert par l'outil "
    "generer_carte_hydrometrique - par exemple comparer deux variables, un type de "
    "graphique specifique, une agregation particuliere), ne passe PAS par un appel "
    "d'outil : reponds directement avec le code Python COMPLET et EXECUTABLE "
    "(matplotlib/pandas/numpy uniquement), sans texte explicatif avant ou apres, en "
    "utilisant le DataFrame pandas deja charge dans la variable `df`. Termine toujours "
    "par plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')."
)


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


def message_tool_call(nom_outil, arguments):
    return {
        "role": "assistant",
        "content": f'<tool_call>\n{json.dumps({"name": nom_outil, "arguments": arguments}, ensure_ascii=False)}\n</tool_call>'
    }


def message_code_direct(code_python):
    """Reponse en code Python BRUT (pas de wrapper JSON) pour les
    graphiques libres."""
    return {"role": "assistant", "content": code_python}


def exemple(messages):
    return {
        "messages": [{"role": "system", "content": SYSTEME}] + messages,
        "tools": OUTILS,
    }


def generer_exemples_outils():
    exemples = []

    formulations_annuaire = [
        "Génère-moi l'annuaire {annee}",
        "Je voudrais l'annuaire hydrométrique complet de {annee}",
        "Peux-tu produire le PDF de l'année {annee} ?",
        "Lance la génération de l'annuaire pour {annee}",
    ]
    for annee in [2019, 2020, 2021, 2022, 2023, 2024]:
        for f in formulations_annuaire:
            exemples.append(exemple([
                {"role": "user", "content": f.format(annee=annee)},
                message_tool_call("generer_annuaire", {"annee": annee}),
            ]))

    for annee in [2023, 2024]:
        exemples.append(exemple([
            {"role": "user", "content": f"Génère-moi un pdf pour 6 mois de {annee}, pas tout l'annuaire"},
            message_tool_call("generer_pdf_periode", {"annee": annee, "mois_debut": 1, "mois_fin": 6}),
        ]))
        exemples.append(exemple([
            {"role": "user", "content": f"Fais un rapport {annee} du mois 3 au mois 9"},
            message_tool_call("generer_pdf_periode", {"annee": annee, "mois_debut": 3, "mois_fin": 9}),
        ]))

    for zone in ["Tunisie", "Béja", "Bizerte", "Jendouba", "Ariana"]:
        for n in [3, 6, 12]:
            exemples.append(exemple([
                {"role": "user", "content": f"Génère-moi la carte hydrométrique de {zone} pour les {n} derniers mois"},
                message_tool_call("generer_carte_hydrometrique", {"zone": zone, "nb_mois_precedents": n}),
            ]))

    formulations_recalcul = [
        "J'ai inséré de nouvelles données pour {annee}, recalcule les statistiques",
        "Peux-tu recalculer les crues pour {annee} ? J'ai ajouté des données",
        "Nouvelles données importées pour {annee}, fais le calcul automatique",
        "Recalcule les statistiques et les crues de {annee}",
        "J'ai importé des débits pour {annee}, il faut refaire les calculs",
        "Mets à jour les statistiques de {annee} avec les nouvelles données",
        "Lance le recalcul automatique pour l'année {annee}",
        "Les données de {annee} ont changé, relance le calcul des crues",
    ]
    for annee in [2019, 2020, 2021, 2022, 2023, 2024, 2025]:
        for f in formulations_recalcul:
            exemples.append(exemple([
                {"role": "user", "content": f.format(annee=annee)},
                message_tool_call("recalculer_statistiques", {"annee": annee}),
            ]))

    return exemples


def generer_exemples_graphiques_code_direct():
    exemples = []

    cas = [
        (
            "Trace-moi le débit en fonction de la hauteur d'eau pour cette station",
            "import matplotlib.pyplot as plt\n\n"
            "plt.figure(figsize=(8, 5))\n"
            "plt.scatter(df['hauteur_cm'], df['debit_m3s'], s=10, color='#1a5276')\n"
            "plt.xlabel('Hauteur (cm)')\n"
            "plt.ylabel('Débit (m³/s)')\n"
            "plt.title('Débit en fonction de la hauteur')\n"
            "plt.grid(True, alpha=0.3)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')"
        ),
        (
            "Je veux un histogramme de la distribution des débits",
            "import matplotlib.pyplot as plt\n\n"
            "plt.figure(figsize=(8, 5))\n"
            "plt.hist(df['debit_m3s'], bins=30, color='#2e5aac', edgecolor='black')\n"
            "plt.xlabel('Débit (m³/s)')\n"
            "plt.ylabel(\"Nombre d'observations\")\n"
            "plt.title('Distribution des débits')\n"
            "plt.grid(True, alpha=0.3)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')"
        ),
        (
            "Compare-moi le débit moyen mensuel entre deux années sur un même graphique",
            "import matplotlib.pyplot as plt\n\n"
            "plt.figure(figsize=(9, 5))\n"
            "for annee, groupe in df.groupby('annee'):\n"
            "    plt.plot(groupe['mois'], groupe['debit_moyen'], marker='o', label=str(annee))\n"
            "plt.xlabel('Mois')\n"
            "plt.ylabel('Débit moyen (m³/s)')\n"
            "plt.title('Comparaison du débit moyen mensuel')\n"
            "plt.legend()\n"
            "plt.grid(True, alpha=0.3)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')"
        ),
        (
            "Fais-moi un boxplot des débits par gouvernorat",
            "import matplotlib.pyplot as plt\n\n"
            "fig, ax = plt.subplots(figsize=(10, 5))\n"
            "df.boxplot(column='debit_m3s', by='gouvernorat', rot=45, ax=ax)\n"
            "ax.set_xlabel('Gouvernorat')\n"
            "ax.set_ylabel('Débit (m³/s)')\n"
            "ax.set_title('Distribution des débits par gouvernorat')\n"
            "plt.suptitle('')\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')"
        ),
        (
            "Montre-moi l'évolution du volume écoulé année par année en barres",
            "import matplotlib.pyplot as plt\n\n"
            "plt.figure(figsize=(9, 5))\n"
            "plt.bar(df['annee'].astype(str), df['volume_total_hm3'], color='#1a7a3c')\n"
            "plt.xlabel('Année')\n"
            "plt.ylabel('Volume total écoulé (Hm³)')\n"
            "plt.title(\"Volume total écoulé par année\")\n"
            "plt.grid(True, alpha=0.3, axis='y')\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')"
        ),
        (
            "Fais un camembert de la répartition des débits par saison",
            "import matplotlib.pyplot as plt\n\n"
            "def saison(mois):\n"
            "    if mois in [12, 1, 2]:\n"
            "        return 'Hiver'\n"
            "    if mois in [3, 4, 5]:\n"
            "        return 'Printemps'\n"
            "    if mois in [6, 7, 8]:\n"
            "        return 'Été'\n"
            "    return 'Automne'\n\n"
            "df['saison'] = df['mois'].apply(saison)\n"
            "repartition = df.groupby('saison')['debit_m3s'].sum()\n"
            "plt.figure(figsize=(7, 7))\n"
            "plt.pie(repartition.values, labels=repartition.index, autopct='%1.1f%%',\n"
            "        colors=['#4292c6', '#74c476', '#fd8d3c', '#c0392b'])\n"
            "plt.title('Répartition des débits par saison')\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')"
        ),
    ]

    for question, code in cas:
        exemples.append(exemple([
            {"role": "user", "content": question},
            message_code_direct(code),
        ]))

    formulations_scatter = [
        "Peux-tu me tracer un nuage de points débit vs hauteur ?",
        "Je voudrais visualiser la relation entre hauteur et débit",
        "Fais un graphique X/Y avec la hauteur en abscisse et le débit en ordonnée",
    ]
    code_scatter = (
        "import matplotlib.pyplot as plt\n\n"
        "plt.figure(figsize=(8, 5))\n"
        "plt.scatter(df['hauteur_cm'], df['debit_m3s'], s=10, color='#1a5276')\n"
        "plt.xlabel('Hauteur (cm)')\n"
        "plt.ylabel('Débit (m³/s)')\n"
        "plt.title('Débit en fonction de la hauteur')\n"
        "plt.grid(True, alpha=0.3)\n"
        "plt.tight_layout()\n"
        "plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')"
    )
    for f in formulations_scatter:
        exemples.append(exemple([
            {"role": "user", "content": f},
            message_code_direct(code_scatter),
        ]))

    return exemples


def generer_exemples_qa(engine, limite_stations=40):
    exemples = []
    try:
        stats = pd.read_sql(
            """
            SELECT s.nom, s.gouvernorat, st.annee, st.debit_moyen, st.debit_max_jour,
                   st.date_max_jour, st.volume_total_hm3
            FROM statistiques_annuelles st
            JOIN station s ON s.code_station = st.code_station
            ORDER BY st.annee DESC
            LIMIT %(lim)s
            """,
            engine, params={"lim": limite_stations}
        )
    except Exception as e:
        print(f"[avertissement] impossible de lire statistiques_annuelles : {e}")
        return exemples

    for _, row in stats.iterrows():
        nom = row["nom"]
        annee = int(row["annee"])
        if pd.notna(row["debit_moyen"]):
            exemples.append(exemple([
                {"role": "user", "content": f"Quel est le débit moyen à la station {nom} en {annee} ?"},
                {"role": "assistant", "content": f"Le débit moyen annuel à la station {nom} pour l'année {annee} est de {row['debit_moyen']:.2f} m³/s."},
            ]))
        if pd.notna(row["debit_max_jour"]):
            date_txt = pd.to_datetime(row["date_max_jour"]).strftime("%d/%m/%Y") if pd.notna(row["date_max_jour"]) else "date inconnue"
            exemples.append(exemple([
                {"role": "user", "content": f"Quel a été le débit maximal journalier de {nom} pour l'année {annee} ?"},
                {"role": "assistant", "content": f"Le débit maximal journalier à {nom} en {annee} a été de {row['debit_max_jour']:.2f} m³/s, atteint le {date_txt}."},
            ]))
        if pd.notna(row["volume_total_hm3"]):
            exemples.append(exemple([
                {"role": "user", "content": f"Quel volume total a été écoulé à {nom} en {annee} ?"},
                {"role": "assistant", "content": f"Le volume total écoulé à la station {nom} en {annee} est de {row['volume_total_hm3']:.2f} Hm³."},
            ]))

    return exemples


def generer_exemples_vocabulaire():
    paires = [
        ("Qu'est-ce qu'une crue ?",
         "Une crue est une augmentation rapide et significative du débit d'un cours d'eau, "
         "généralement causée par des précipitations importantes, qui dépasse un seuil "
         "défini par rapport au régime habituel de la station."),
        ("Que signifie le temps de base d'une crue ?",
         "Le temps de base est la durée totale pendant laquelle le débit reste supérieur "
         "au seuil de crue, du début de la montée des eaux jusqu'au retour au débit normal."),
        ("Qu'est-ce que l'étalonnage d'une station hydrométrique ?",
         "L'étalonnage (ou courbe de tarage) est la relation entre la hauteur d'eau lue à "
         "l'échelle limnimétrique et le débit réel, établie par des jaugeages sur le terrain."),
        ("Qu'est-ce qu'un jaugeage d'étiage ?",
         "Un jaugeage d'étiage est une mesure directe du débit d'un cours d'eau réalisée "
         "en période de basses eaux, pour caractériser le régime minimal de la station."),
    ]
    return [exemple([
        {"role": "user", "content": q},
        {"role": "assistant", "content": a},
    ]) for q, a in paires]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sortie", default="dataset_finetuning.jsonl")
    parser.add_argument("--sans-base", action="store_true")
    args = parser.parse_args()

    tous_exemples = []
    tous_exemples += generer_exemples_outils()
    tous_exemples += generer_exemples_graphiques_code_direct()
    tous_exemples += generer_exemples_vocabulaire()

    nb_qa = 0
    if not args.sans_base:
        try:
            engine = get_engine()
            exemples_qa = generer_exemples_qa(engine)
            tous_exemples += exemples_qa
            nb_qa = len(exemples_qa)
        except Exception as e:
            print(f"[avertissement] connexion base impossible, Q&A ignorees : {e}")

    random.shuffle(tous_exemples)

    with open(args.sortie, "w", encoding="utf-8") as f:
        for ex in tous_exemples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"{len(tous_exemples)} exemple(s) ecrit(s) dans {args.sortie}")
    print("Repartition :")
    print(f"  - outils (tool_call)       : {len(generer_exemples_outils())}")
    print(f"  - graphiques (code direct) : {len(generer_exemples_graphiques_code_direct())}")
    print(f"  - vocabulaire              : {len(generer_exemples_vocabulaire())}")
    print(f"  - Q&A donnees              : {nb_qa}")
    print("\nVerification structure (1er exemple) :")
    print("  cles de premier niveau :", list(tous_exemples[0].keys()))
    assert "tools" in tous_exemples[0]
    assert "tools" not in tous_exemples[0]["messages"][0]
    print("  OK.")


if __name__ == "__main__":
    main()