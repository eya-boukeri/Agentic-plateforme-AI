"""
tester_agent_cartographie.py
Teste l'agent de cartographie TOUT SEUL, sans base de donnees ni PDF -
juste pour verifier que les fichiers SIG (data/gouvernorats_tunisie.geojson,
cours_deau_tunisie.geojson, regions_hydrographiques.geojson, mnt_tunisie.tif)
sont bien places et que les dependances (geopandas, rasterio) sont
installees, avant de lancer la generation complete de l'annuaire.

Usage :
    python tester_agent_cartographie.py
    python tester_agent_cartographie.py BIZERTE     (teste un autre gouvernorat)
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "agents"))

import matplotlib
matplotlib.use("Agg")  # pas d'affichage interactif necessaire

from agents.agent_cartographie import AgentCartographie, GEOPANDAS_DISPONIBLE, RASTERIO_DISPONIBLE


def main():
    gouv = sys.argv[1].upper() if len(sys.argv) > 1 else "BEJA"

    print("=" * 60)
    print("TEST DE L'AGENT CARTOGRAPHIE")
    print("=" * 60)
    print(f"geopandas disponible : {GEOPANDAS_DISPONIBLE}")
    print(f"rasterio disponible  : {RASTERIO_DISPONIBLE}")
    if not GEOPANDAS_DISPONIBLE:
        print("\n[ERREUR] geopandas manquant : pip install geopandas")
        return
    if not RASTERIO_DISPONIBLE:
        print("\n[avertissement] rasterio manquant (pip install rasterio) : "
              "la carte avec relief (MNT) ne pourra pas etre generee, "
              "mais les autres cartes fonctionneront quand meme.")

    ac = AgentCartographie()
    print(f"\nDossier de donnees utilise : {ac.data_dir}")
    for nom_fichier in ["gouvernorats_tunisie.geojson", "cours_deau_tunisie.geojson",
                        "regions_hydrographiques.geojson", "mnt_tunisie.tif"]:
        chemin = ac._chemin(nom_fichier)
        present = os.path.exists(chemin)
        marqueur = "OK " if present else "MANQUANT "
        print(f"  [{marqueur}] {nom_fichier}")

    print(f"\nTest sur le gouvernorat : {gouv}\n")

    stations_test = [
        {"nom": "STATION TEST 1", "x_utm": 519962.11, "y_utm": 4065631.93},
        {"nom": "STATION TEST 2", "x_utm": 546325.35, "y_utm": 4049324.39},
    ]

    print("[1/3] Carte de localisation (sans stations)...")
    p1 = ac.carte_gouvernorat(gouv, annee="test")
    print("     ->", p1 or "ECHEC (voir messages ci-dessus)")

    print("[2/3] Carte des stations (fond uni + cours d'eau)...")
    p2 = ac.carte_gouvernorat(gouv, stations=stations_test, annee="test")
    print("     ->", p2 or "ECHEC")

    print("[3/3] Carte reseau hydrometrique (relief MNT + cours d'eau + stations)...")
    p3 = ac.carte_gouvernorat(gouv, stations=stations_test, avec_mnt=True, annee="test")
    print("     ->", p3 or "ECHEC (rasterio installe ? mnt_tunisie.tif present ?)")

    print("\n" + "=" * 60)
    if p1 and p2 and p3:
        print("TOUT FONCTIONNE. Ouvrez les 3 images dans output/graphs/ pour verifier visuellement :")
        for p in [p1, p2, p3]:
            print(" -", p)
    else:
        print("Au moins une carte a echoue - voir les messages ci-dessus pour la cause exacte.")
    print("=" * 60)


if __name__ == "__main__":
    main()