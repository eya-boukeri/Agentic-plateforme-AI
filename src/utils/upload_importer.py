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


def _read_mdb_file(chemin: str) -> pd.DataFrame:
    """Lit une base de données Microsoft Access (.mdb) et extrait les débits.
    Supporte les architectures classiques de bases hydrologiques :
    - Table unique de mesures (format long ou format large)
    - Tables multiples par station
    """
    import subprocess
    import io

    # 1. Lister les tables via pandas_access ou mdb-tables
    tables = []
    try:
        import pandas_access as mdb
        tables = mdb.list_tables(chemin)
    except Exception:
        pass

    if not tables:
        try:
            cmd = ["mdb-tables", "-1", chemin]
            res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            tables = [t.strip() for t in res.decode("utf-8", errors="ignore").split("\n") if t.strip()]
        except Exception as e:
            raise RuntimeError(f"Impossible de lire le fichier .mdb via mdbtools : {e}")

    if not tables:
        raise ValueError("Aucune table trouvée dans le fichier Access .mdb.")

    # Filtrer les tables système Access (commençant par MSys)
    tables_utiles = [t for t in tables if not t.upper().startswith("MSYS")]
    if not tables_utiles:
        tables_utiles = tables

    def _extraire_table(nom_table):
        try:
            import pandas_access as mdb
            return mdb.read_table(chemin, nom_table)
        except Exception:
            cmd = ["mdb-export", chemin, nom_table]
            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            return pd.read_csv(io.StringIO(output.decode("utf-8", errors="ignore")))

    # 2. Chercher les tables contenant des données de débit ou de mesures
    mots_cles = ["debit", "débit", "mesure", "datasheet", "donnee", "donnée", "valeur", "hydro", "station"]
    tables_prioritaires = [t for t in tables_utiles if any(kw in t.lower() for kw in mots_cles)]
    tables_a_tester = tables_prioritaires if tables_prioritaires else tables_utiles

    dfs_long = []
    table_large_trouvee = None

    for t in tables_a_tester:
        try:
            df_t = _extraire_table(t)
            if df_t.empty:
                continue

            col_map = {str(c).lower().strip(): c for c in df_t.columns}

            # Détection colonne Date
            col_date = None
            for cand in ["date", "jour", "date_mesure", "date_debit", "datetime", "temps", "time"]:
                if cand in col_map:
                    col_date = col_map[cand]
                    break

            # Détection colonne Station
            col_station = None
            for cand in ["station", "id_station", "code_station", "nom_station", "code", "nom"]:
                if cand in col_map:
                    col_station = col_map[cand]
                    break

            # Détection colonne Débit
            col_debit = None
            for cand in ["valeur", "debit", "débit", "debit_moyen", "q", "debits", "debit_m3s", "val"]:
                if cand in col_map:
                    col_debit = col_map[cand]
                    break

            # Cas 1 : Format long (Date, Station, Débit)
            if col_date and col_station and col_debit:
                df_sub = pd.DataFrame({
                    "Date": pd.to_datetime(df_t[col_date], errors="coerce", dayfirst=True),
                    "nom_excel": df_t[col_station].astype(str).str.strip(),
                    "Valeur": pd.to_numeric(df_t[col_debit], errors="coerce"),
                }).dropna(subset=["Date", "Valeur"])
                if not df_sub.empty:
                    dfs_long.append(df_sub)
                    continue

            # Cas 2 : Table représentant une station individuelle
            if col_date and col_debit and not col_station:
                nom_station_table = t.replace("debit_", "").replace("debits_", "").strip()
                df_sub = pd.DataFrame({
                    "Date": pd.to_datetime(df_t[col_date], errors="coerce", dayfirst=True),
                    "nom_excel": nom_station_table,
                    "Valeur": pd.to_numeric(df_t[col_debit], errors="coerce"),
                }).dropna(subset=["Date", "Valeur"])
                if not df_sub.empty:
                    dfs_long.append(df_sub)
                    continue

            # Cas 3 : Format large (colonne 0 = Date, colonnes suivantes = stations)
            if col_date and len(df_t.columns) > 2 and table_large_trouvee is None:
                table_large_trouvee = df_t

        except Exception as err:
            print(f"[avertissement] Erreur lecture table {t} : {err}")
            continue

    if dfs_long:
        return pd.concat(dfs_long, ignore_index=True)

    if table_large_trouvee is not None:
        return table_large_trouvee

    # Repli par défaut
    if tables_utiles:
        return _extraire_table(tables_utiles[0])

    raise ValueError("Impossible d'extraire des données exploitables du fichier .mdb.")


def _read_tabular_file(chemin: str) -> pd.DataFrame:
    suffix = Path(chemin).suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        try:
            return pd.read_excel(chemin, sheet_name="Datasheet")
        except Exception:
            return pd.read_excel(chemin, sheet_name=0)
    if suffix == ".csv":
        return pd.read_csv(chemin, sep=None, engine="python")
    if suffix == ".mdb":
        return _read_mdb_file(chemin)
    raise ValueError(f"Format de fichier non supporte : {suffix}")


def charger_fichier(chemin: str) -> pd.DataFrame:
    df = _read_tabular_file(chemin)

    # Si c'est déjà un format long propre (cas MDB ou format normalisé)
    if set(["Date", "nom_excel", "Valeur"]).issubset(df.columns):
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
        df["nom_excel"] = df["nom_excel"].astype(str).str.replace(r"\s*/\s*D[ée]bit", "", regex=True).str.strip()
        df["Valeur"] = pd.to_numeric(df["Valeur"], errors="coerce")
        return df.dropna(subset=["Date", "Valeur"])

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
    return (
        sorted(glob.glob("jet*.xls"))
        + sorted(glob.glob("jet*.xlsx"))
        + sorted(glob.glob("jet*.csv"))
        + sorted(glob.glob("*.mdb"))
        + sorted(glob.glob("jet*.mdb"))
    )


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