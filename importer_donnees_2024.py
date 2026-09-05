"""
importer_donnees_2024.py
Importe les nouveaux fichiers .xls (debits instantanes 2024) dans la table
`debits`, en faisant correspondre les noms de stations des fichiers Excel
aux codes stations reels de la base (station/stations_base).

ETAPE 1 (par defaut) - VERIFICATION SEULEMENT :
    python importer_donnees_2024.py
Affiche la correspondance nom_excel -> code_station trouvee, avec un score
de confiance. NE TOUCHE PAS A LA BASE. Verifiez la sortie avant de continuer.

ETAPE 2 - CORRECTIONS MANUELLES SI BESOIN :
Si une correspondance est fausse ou manquante, ajoutez une entree dans
CORRESPONDANCES_MANUELLES ci-dessous (nom exact de la colonne Excel,
sans le " / Debit" -> code_station), puis relancez l'etape 1 pour verifier.

ETAPE 3 - IMPORT REEL :
    python importer_donnees_2024.py --confirmer
Insere les donnees dans `debits`. Les lignes (Id_Station, Date) deja
presentes dans la base sont ignorees automatiquement (pas de doublon).
"""

import sys
import os
import re
import glob
import unicodedata
import difflib
import argparse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ----------------------------------------------------------------------
# Si l'appariement automatique se trompe pour un nom, ajoutez-le ici :
# "Nom exact dans le fichier Excel (sans '/ Debit')": "code_station exact"
# Exemple : "BOU SALEM": "1483800110"
CORRESPONDANCES_MANUELLES = {
    "SILIANA LAOUJ": "1485501635",   # Jebel Laoudj
    "Siliana pt rte": "1485501610",  # Pont GP4 Siliana
    "GP17  MLG": "1485101211",       # Mellegue GP17
    "Lahmar": "1485802270",   
    
}
# ----------------------------------------------------------------------

FICHIERS_XLS = sorted(glob.glob("jet*.xls"))

SEUIL_CONFIANCE = 0.6  # en dessous, la correspondance est jugee douteuse


def normaliser(nom):
    """Normalise un nom de station pour la comparaison (majuscules, sans
    accents, sans ponctuation ni espaces multiples)."""
    nom = str(nom).upper().strip()
    nom = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii")
    nom = re.sub(r"[^A-Z0-9 ]", " ", nom)
    nom = re.sub(r"\s+", " ", nom).strip()
    return nom


def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "hydrometry"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
    }


def charger_stations_connues(engine):
    """Recupere (code_station, nom) depuis `station` ET `stations_base`,
    pour maximiser les chances de trouver une correspondance."""
    stations = {}

    try:
        df = pd.read_sql('SELECT code_station, nom FROM station', engine)
        for _, row in df.iterrows():
            stations[str(row["code_station"])] = row["nom"]
    except Exception as e:
        print(f"[avertissement] lecture de 'station' impossible : {e}")

    try:
        df = pd.read_sql('SELECT "Id_Station" AS code_station, "Nom" AS nom FROM stations_base', engine)
        for _, row in df.iterrows():
            code = str(row["code_station"])
            if code not in stations and pd.notna(row["nom"]):
                stations[code] = row["nom"]
    except Exception as e:
        print(f"[avertissement] lecture de 'stations_base' impossible : {e}")

    return stations


def trouver_correspondance(nom_excel, stations_connues):
    """Retourne (code_station, nom_matche, score) ou (None, None, 0) si rien
    de suffisamment proche n'est trouve. Le score combine une similarite au
    niveau caractere (difflib) et une similarite au niveau mots (Jaccard),
    en prenant le maximum des deux. Pas de bonus de "contient" : un mot
    generique court (PONT, AVAL, AMONT) partage par de nombreux noms de
    stations ne doit pas faire remonter artificiellement un mauvais match."""
    if nom_excel in CORRESPONDANCES_MANUELLES:
        code = CORRESPONDANCES_MANUELLES[nom_excel]
        return code, stations_connues.get(code, "(nom inconnu)"), 1.0

    nom_norm = normaliser(nom_excel)
    tokens_excel = set(nom_norm.split())
    meilleur_code, meilleur_nom, meilleur_score = None, None, 0.0

    for code, nom_db in stations_connues.items():
        nom_db_norm = normaliser(nom_db)
        tokens_db = set(nom_db_norm.split())

        ratio_car = difflib.SequenceMatcher(None, nom_norm, nom_db_norm).ratio()

        union = tokens_excel | tokens_db
        jaccard = len(tokens_excel & tokens_db) / len(union) if union else 0.0

        score = max(ratio_car, jaccard)
        if score > meilleur_score:
            meilleur_score = score
            meilleur_code = code
            meilleur_nom = nom_db

    return meilleur_code, meilleur_nom, meilleur_score


def charger_fichier_xls(chemin):
    """Lit un fichier .xls large format et le transforme en format long
    (Date, nom_excel, Valeur)."""
    df = pd.read_excel(chemin, sheet_name="Datasheet")
    df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    colonnes_stations = [c for c in df.columns if c != "Date"]
    long_df = df.melt(id_vars=["Date"], value_vars=colonnes_stations,
                       var_name="nom_excel", value_name="Valeur")
    long_df["nom_excel"] = long_df["nom_excel"].str.replace(r"\s*/\s*D[ée]bit", "", regex=True).str.strip()
    long_df["Valeur"] = pd.to_numeric(long_df["Valeur"], errors="coerce")
    long_df = long_df.dropna(subset=["Date", "Valeur"])
    return long_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmer", action="store_true",
                         help="Insere reellement les donnees (sinon, verification seule)")
    args = parser.parse_args()

    db_config = get_db_config()
    db_url = URL.create("postgresql+psycopg2", username=db_config["user"],
                         password=db_config["password"], host=db_config["host"],
                         port=db_config["port"], database=db_config["database"])
    engine = create_engine(db_url, connect_args={"client_encoding": "utf8"})

    print("Chargement des stations connues en base...")
    stations_connues = charger_stations_connues(engine)
    print(f"{len(stations_connues)} stations connues (station + stations_base).\n")

    if not FICHIERS_XLS:
        print("[ERREUR] Aucun fichier 'jet*.xls' trouve dans le dossier courant :")
        print(f"  {os.getcwd()}")
        print("Fichiers .xls presents ici :", [f for f in os.listdir('.') if f.lower().endswith('.xls')])
        print("Placez les fichiers jet*.xls dans ce dossier, ou lancez le script depuis le bon dossier.")
        return

    toutes_les_donnees = []
    correspondance_par_nom = {}

    for fichier in FICHIERS_XLS:
        if not os.path.exists(fichier):
            print(f"[ATTENTION] fichier introuvable : {fichier} (le cherche dans le dossier courant)")
            continue
        print(f"Lecture de {fichier} ...")
        long_df = charger_fichier_xls(fichier)
        toutes_les_donnees.append(long_df)

        for nom_excel in long_df["nom_excel"].unique():
            if nom_excel not in correspondance_par_nom:
                code, nom_db, score = trouver_correspondance(nom_excel, stations_connues)
                correspondance_par_nom[nom_excel] = (code, nom_db, score)

    print("\n" + "=" * 70)
    print("CORRESPONDANCES TROUVEES")
    print("=" * 70)
    douteuses = []
    for nom_excel, (code, nom_db, score) in sorted(correspondance_par_nom.items()):
        marqueur = "OK " if score >= SEUIL_CONFIANCE else "??? "
        print(f"{marqueur} {nom_excel!r:35s} -> {code} ({nom_db})  [score={score:.2f}]")
        if score < SEUIL_CONFIANCE:
            douteuses.append(nom_excel)

    if douteuses:
        print("\n" + "!" * 70)
        print(f"{len(douteuses)} correspondance(s) DOUTEUSE(S) (score < {SEUIL_CONFIANCE}) :")
        for nom in douteuses:
            print(f"  - {nom!r}")
        print("Ajoutez ces noms dans CORRESPONDANCES_MANUELLES en haut du script,")
        print("avec le bon code_station, puis relancez ce script.")
        print("!" * 70)

    if not args.confirmer:
        print("\n[Mode verification uniquement - aucune donnee inseree]")
        print("Une fois les correspondances validees, relancez avec --confirmer")
        return

    if douteuses:
        print("\n[ARRET] Des correspondances restent douteuses. "
              "Corrigez-les avant de relancer avec --confirmer.")
        return

    print("\nFusion des fichiers et preparation de l'insertion...")
    df_final = pd.concat(toutes_les_donnees, ignore_index=True)
    df_final["Id_Station"] = df_final["nom_excel"].map(lambda n: correspondance_par_nom[n][0])
    df_final = df_final[["Id_Station", "Date", "Valeur"]].dropna(subset=["Id_Station"])
    print(f"{len(df_final)} lignes au total a inserer (avant dedoublonnage).")

    # Dedoublonnage : ne pas re-inserer des (Id_Station, Date) deja en base
    print("Verification des doublons deja en base...")
    stations_concernees = tuple(df_final["Id_Station"].unique())
    existants = pd.read_sql(
        'SELECT "Id_Station", "Date" FROM debits WHERE "Id_Station" = ANY(%(stations)s)',
        engine, params={"stations": list(stations_concernees)}
    )
    existants["cle"] = existants["Id_Station"].astype(str) + "|" + existants["Date"].astype(str)
    df_final["cle"] = df_final["Id_Station"].astype(str) + "|" + df_final["Date"].astype(str)
    avant = len(df_final)
    df_final = df_final[~df_final["cle"].isin(set(existants["cle"]))].drop(columns=["cle"])
    print(f"{avant - len(df_final)} ligne(s) deja presentes ignorees. {len(df_final)} a inserer.")

    if df_final.empty:
        print("Rien a inserer (tout est deja en base).")
        return

    print("Insertion en base (par lots de 5000 lignes)...")
    df_final.to_sql("debits", engine, if_exists="append", index=False, method="multi", chunksize=5000)
    print(f"[OK] {len(df_final)} lignes inserees dans 'debits'.")
    print("\nVous pouvez maintenant recalculer les statistiques/crues pour 2024, "
          "puis generer l'annuaire 2024.")


if __name__ == "__main__":
    main()