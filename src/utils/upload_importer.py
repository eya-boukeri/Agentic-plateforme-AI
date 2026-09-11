"""
src/utils/upload_importer.py
Pipeline d'import réutilisable pour les fichiers hydrologiques uploadés.
"""

import argparse
import difflib
import glob
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()

CORRESPONDANCES_MANUELLES = {
    "SILIANA LAOUJ": "1485501635",
    "Siliana pt rte": "1485501610",
    "GP17  MLG": "1485101211",
    "Lahmar": "1485802270",
}

SEUIL_CONFIANCE = 0.6


def normaliser(nom):
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


def get_engine(db_config=None):
    db_config = db_config or get_db_config()
    db_url = URL.create(
        "postgresql+psycopg2",
        username=db_config["user"],
        password=db_config["password"],
        host=db_config["host"],
        port=db_config["port"],
        database=db_config["database"],
    )
    return create_engine(db_url, connect_args={"client_encoding": "utf8"})


def charger_stations_connues(engine):
    stations = {}

    try:
        df = pd.read_sql("SELECT code_station, nom FROM station", engine)
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


def _read_tabular_file(chemin: str) -> pd.DataFrame:
    suffix = Path(chemin).suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        try:
            return pd.read_excel(chemin, sheet_name="Datasheet")
        except Exception:
            return pd.read_excel(chemin, sheet_name=0)
    if suffix == ".csv":
        return pd.read_csv(chemin, sep=None, engine="python")
    raise ValueError(f"Format de fichier non supporte : {suffix}")


def charger_fichier(chemin: str) -> pd.DataFrame:
    df = _read_tabular_file(chemin)
    df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)

    colonnes_stations = [c for c in df.columns if c != "Date"]
    long_df = df.melt(
        id_vars=["Date"],
        value_vars=colonnes_stations,
        var_name="nom_excel",
        value_name="Valeur",
    )
    long_df["nom_excel"] = long_df["nom_excel"].astype(str).str.replace(r"\s*/\s*D[ée]bit", "", regex=True).str.strip()
    long_df["Valeur"] = pd.to_numeric(long_df["Valeur"], errors="coerce")
    long_df = long_df.dropna(subset=["Date", "Valeur"])
    return long_df


def detecter_fichiers_par_defaut():
    return sorted(glob.glob("jet*.xls")) + sorted(glob.glob("jet*.xlsx")) + sorted(glob.glob("jet*.csv"))


def importer_fichiers(fichiers, db_config=None, confirmer=False):
    engine = get_engine(db_config)
    stations_connues = charger_stations_connues(engine)

    toutes_les_donnees = []
    correspondance_par_nom = {}
    rapport = {
        "stations_connues": len(stations_connues),
        "fichiers": [],
        "correspondances": [],
        "douteuses": [],
        "lignes_a_inserer": 0,
        "lignes_ignorees": 0,
        "lignes_inserees": 0,
        "statut": "verification",
    }

    for fichier in fichiers:
        if not os.path.exists(fichier):
            rapport["fichiers"].append({"fichier": fichier, "statut": "introuvable"})
            continue
        long_df = charger_fichier(fichier)
        rapport["fichiers"].append({"fichier": fichier, "statut": "lu", "lignes": len(long_df)})
        toutes_les_donnees.append(long_df)

        for nom_excel in long_df["nom_excel"].unique():
            if nom_excel not in correspondance_par_nom:
                code, nom_db, score = trouver_correspondance(nom_excel, stations_connues)
                correspondance_par_nom[nom_excel] = (code, nom_db, score)

    for nom_excel, (code, nom_db, score) in sorted(correspondance_par_nom.items()):
        entree = {
            "nom_excel": nom_excel,
            "code_station": code,
            "nom_db": nom_db,
            "score": score,
        }
        rapport["correspondances"].append(entree)
        if score < SEUIL_CONFIANCE:
            rapport["douteuses"].append(entree)

    if not confirmer:
        rapport["statut"] = "verification"
        return rapport

    if rapport["douteuses"]:
        rapport["statut"] = "bloque"
        return rapport

    if not toutes_les_donnees:
        rapport["statut"] = "vide"
        return rapport

    df_final = pd.concat(toutes_les_donnees, ignore_index=True)
    df_final["Id_Station"] = df_final["nom_excel"].map(lambda n: correspondance_par_nom[n][0])
    df_final = df_final[["Id_Station", "Date", "Valeur"]].dropna(subset=["Id_Station"])
    rapport["lignes_a_inserer"] = len(df_final)

    stations_concernees = tuple(df_final["Id_Station"].unique())
    if stations_concernees:
        existants = pd.read_sql(
            'SELECT "Id_Station", "Date" FROM debits WHERE "Id_Station" = ANY(%(stations)s)',
            engine,
            params={"stations": list(stations_concernees)},
        )
    else:
        existants = pd.DataFrame(columns=["Id_Station", "Date"])

    if not existants.empty:
        existants["cle"] = existants["Id_Station"].astype(str) + "|" + existants["Date"].astype(str)
    df_final["cle"] = df_final["Id_Station"].astype(str) + "|" + df_final["Date"].astype(str)

    avant = len(df_final)
    df_final = df_final[~df_final["cle"].isin(set(existants["cle"]) if not existants.empty else set())].drop(columns=["cle"])
    rapport["lignes_ignorees"] = avant - len(df_final)

    if df_final.empty:
        rapport["statut"] = "aucune_nouvelle_donnee"
        return rapport

    df_final.to_sql("debits", engine, if_exists="append", index=False, method="multi", chunksize=5000)
    rapport["lignes_inserees"] = len(df_final)
    rapport["statut"] = "importe"
    return rapport


def build_default_report(fichiers=None, confirmer=False):
    fichiers = fichiers or detecter_fichiers_par_defaut()
    return importer_fichiers(fichiers, confirmer=confirmer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmer", action="store_true", help="Insere reellement les donnees")
    args = parser.parse_args()

    fichiers = detecter_fichiers_par_defaut()
    if not fichiers:
        print("[ERREUR] Aucun fichier jet*.xls/xlsx/csv trouve dans le dossier courant.")
        return

    rapport = build_default_report(fichiers, confirmer=args.confirmer)
    print(f"Statut: {rapport['statut']}")
    print(f"Fichiers lus: {len([f for f in rapport['fichiers'] if f['statut'] == 'lu'])}")
    print(f"Correspondances douteuses: {len(rapport['douteuses'])}")
    print(f"Lignes a inserer: {rapport['lignes_a_inserer']}")
    print(f"Lignes ignorees: {rapport['lignes_ignorees']}")
    print(f"Lignes inserees: {rapport['lignes_inserees']}")


if __name__ == "__main__":
    main()