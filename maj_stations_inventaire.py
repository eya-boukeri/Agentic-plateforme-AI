"""
maj_stations_inventaire.py
Met a jour les tables `station` et `stations_base` a partir du fichier
d'inventaire du reseau (feuille "ETat"), en ne gardant que les stations
de type "Hydrométrique" et "Hydro-pluviométrique" (les stations purement
"Pluviométrique" sont exclues).

Comportement :
- UPSERT dans `station` : insere les nouvelles stations, met a jour
  nom/x_utm/y_utm/gouvernorat/type_station pour les stations existantes
  SANS toucher cours_eau/bassin/region/altitude/superficie_km2 (absents
  de ce fichier, donc laisses tels quels si deja renseignes).
- Ajoute une colonne `type_station` a `station` si elle n'existe pas deja
  (Hydrometrique / Hydro-pluviometrique).
- Ligne minimale dans `stations_base` (Id_Station/Nom) pour les codes qui
  n'y sont pas du tout, comme dans ajouter_station.py.

Usage :
    python maj_stations_inventaire.py                 (verification uniquement)
    python maj_stations_inventaire.py --confirmer      (ecriture reelle)
"""

import sys
import os
import argparse
import unicodedata

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL

FICHIER_INVENTAIRE = "inventaire reseau (2).xlsx"
FEUILLE = "ETat"
LIGNE_ENTETE = 12  # 0-indexe : la vraie ligne d'en-tete du tableau


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


def normaliser_gouvernorat(gouv):
    if not gouv:
        return None
    gouv = str(gouv).upper().strip()
    correspondances = [
        "ARIANA", "MANOUBA", "BIZERTE", "BEJA", "JENDOUBA", "KEF", "SILIANA",
        "BEN AROUS", "NABEUL", "ZAGHOUAN", "KAIROUAN", "KASSERINE",
        "SIDI BOUZID", "SOUSSE", "MONASTIR", "MAHDIA", "SFAX", "GAFSA",
        "GABES", "KEBILI", "TOZEUR", "MEDENINE", "TATAOUINE", "TUNIS",
    ]
    for cle in correspondances:
        if cle in gouv:
            return "L'ARIANA" if cle == "ARIANA" else cle
    return gouv


def charger_inventaire():
    chemins_possibles = [FICHIER_INVENTAIRE, "inventaire_reseau__2_.xlsx", "inventaire_reseau.xlsx"]
    chemin = next((c for c in chemins_possibles if os.path.exists(c)), None)
    if chemin is None:
        print(f"[ERREUR] Fichier introuvable. Essaye : {chemins_possibles}")
        print(f"Dossier courant : {os.getcwd()}")
        sys.exit(1)

    df = pd.read_excel(chemin, sheet_name=FEUILLE, header=LIGNE_ENTETE)
    df = df.dropna(how="all")
    df = df.dropna(subset=["Code Station"])

    df["code_station"] = df["Code Station"].astype(str).str.strip()
    df["nom"] = df["Nom de la station"].astype(str).str.strip()
    df["gouvernorat"] = df["Gouvernorat"].apply(normaliser_gouvernorat)
    df["x_utm"] = pd.to_numeric(df["x"], errors="coerce")
    df["y_utm"] = pd.to_numeric(df["y"], errors="coerce")
    df["type_station"] = df["Type"].astype(str).str.strip()

    # Ne garder que les stations hydrometriques et hydro-pluviometriques
    # (on exclut les stations purement pluviometriques).
    types_retenus = ["Hydrométrique", "Hydro-pluviométrique"]
    avant = len(df)
    df = df[df["type_station"].isin(types_retenus)]
    print(f"Filtre applique : {avant} -> {len(df)} station(s) "
          f"(types retenus : {', '.join(types_retenus)})")

    return df[["code_station", "nom", "gouvernorat", "x_utm", "y_utm", "type_station"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmer", action="store_true")
    args = parser.parse_args()

    df = charger_inventaire()
    print(f"{len(df)} station(s) lues dans l'inventaire.\n")
    print("Repartition par type :")
    print(df["type_station"].value_counts().to_string())

    engine = get_engine()
    insp = inspect(engine)

    # Combien sont deja connues vs nouvelles
    codes_existants = set(pd.read_sql("SELECT code_station FROM station", engine)["code_station"].astype(str))
    nouveaux = df[~df["code_station"].isin(codes_existants)]
    existants = df[df["code_station"].isin(codes_existants)]
    print(f"\n{len(nouveaux)} nouvelle(s) station(s) a inserer.")
    print(f"{len(existants)} station(s) existante(s) a mettre a jour (nom/coordonnees/gouvernorat/type).")

    if not args.confirmer:
        print("\n[Mode verification uniquement - rien n'a ete ecrit]")
        if len(nouveaux) > 0:
            print("\nExemples de nouvelles stations :")
            print(nouveaux[["code_station", "nom", "gouvernorat", "type_station"]].head(10).to_string(index=False))
        print("\nRelancez avec --confirmer pour ecrire reellement.")
        return

    with engine.begin() as conn:
        # Ajoute la colonne type_station si elle n'existe pas
        colonnes_station = {c["name"] for c in insp.get_columns("station")}
        if "type_station" not in colonnes_station:
            conn.execute(text("ALTER TABLE station ADD COLUMN type_station VARCHAR(50)"))
            print("[OK] Colonne 'type_station' ajoutee a 'station'.")

        nb_inseres = 0
        nb_maj = 0
        for _, row in df.iterrows():
            existe = conn.execute(
                text("SELECT 1 FROM station WHERE code_station = :c"),
                {"c": row["code_station"]}
            ).fetchone()

            if existe:
                conn.execute(text("""
                    UPDATE station
                    SET nom = :nom, gouvernorat = :gouvernorat,
                        x_utm = :x_utm, y_utm = :y_utm, type_station = :type_station,
                        updated_at = NOW()
                    WHERE code_station = :code_station
                """), row.to_dict())
                nb_maj += 1
            else:
                conn.execute(text("""
                    INSERT INTO station (code_station, nom, gouvernorat, x_utm, y_utm, type_station, created_at, updated_at)
                    VALUES (:code_station, :nom, :gouvernorat, :x_utm, :y_utm, :type_station, NOW(), NOW())
                """), row.to_dict())
                nb_inseres += 1

        print(f"\n[OK] {nb_inseres} station(s) inseree(s), {nb_maj} station(s) mise(s) a jour dans 'station'.")

        # Ligne minimale dans stations_base pour les codes absents
        try:
            colonnes_base = {c["name"] for c in insp.get_columns("stations_base")}
            if "Id_Station" in colonnes_base and "Nom" in colonnes_base:
                codes_base_existants = set(
                    pd.read_sql('SELECT "Id_Station" FROM stations_base', engine)["Id_Station"].astype(str)
                )
                manquants = df[~df["code_station"].isin(codes_base_existants)]
                for _, row in manquants.iterrows():
                    conn.execute(
                        text('INSERT INTO stations_base ("Id_Station", "Nom") VALUES (:code, :nom)'),
                        {"code": row["code_station"], "nom": row["nom"]}
                    )
                print(f"[OK] {len(manquants)} ligne(s) minimale(s) ajoutee(s) dans 'stations_base'.")
        except Exception as e:
            print(f"[avertissement] mise a jour de stations_base ignoree : {e}")

    print("\nTermine.")


if __name__ == "__main__":
    main()