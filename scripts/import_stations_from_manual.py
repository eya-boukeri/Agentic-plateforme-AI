"""
scripts/import_stations_only.py
Importe les stations dans la table 'station' uniquement
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
import pandas as pd

# ============================================================
# DONNÉES EXTRAITES DU MANUEL (format simplifié pour table station)
# ============================================================

STATIONS_DATA = {
    "L'ARIANA": [
        ("1485900188", "PONT DE BIZERTE", "Medjerda", 593997, 4095444, 7, 23000, "Mejerdah", "BS-MJD"),
        ("1485900187", "HENCHIR TOBIAS", "Medjerda", 595644, 4097539, None, 623700, "Mejerdah", "BS-MJD"),
    ],
    "MANOUBA": [
        ("1485900170", "JEDAIDA PONT VILLE", "Medjerda", 582687, 4078289, 21, 22100, "Mejerdah", "BS-MJD"),
        ("1483602040", "PONT TINE", "Joumine", 559720.3, 1408167, 0.37, 79385, "Joumine", "ND-ICHK"),
    ],
    "BIZERTE": [
        ("1483306050", "PONT GP11 GRAA", None, 563039, 4121144, None, 6096, "Bizerte", "ND-ICHK"),
        ("1483401550", "SIDI SALEM", "Melah", 541101.67, 4089759.5, 11, 5155, "Bizerte", "ND-ICHK"),
        ("1483402550", "G P 11 DOUIMIS", None, 555381, 4117033, None, 957, "Lac", "ND-ICHK"),
        ("1483600130", "MATEUR", "Joumine", 560481.1, 4099291.9, 12, 1096, "Joumine", "ND-ICHK"),
        ("1483602050", "CASSIS TINE", "Tine", 563898.72, 4091363.16, 3, 9418, "Joumine", "ND-ICHK"),
        ("1483600110", "JEBEL ANTRA", "Joumine", 548021.79, 4106818.42, 18, 130234, "Joumine", "ND-ICHK"),
    ],
    "BEJA": [
        ("1483700250", "OUCHTATA", "El Melah", 500883, 4089871, 25, 315, "Zouara", "ND-ICHK"),
        ("1483700350", "JBEL BOU BRIMA", "Maadenne", 510703, 4083210, 95, 145, "Zouara", "ND-ICHK"),
        ("1485501635", "JEBEL LAOUDJ", "Siliana", 540942.95, 4036958.04, 125, 2066, "Siliana", "MY-MJD"),
        ("1485793050", "AVAL MKHACHBIA", None, 535935, 4064085, 13, 4106, "Zarga", "MY-MJD"),
        ("1485602240", "PONT GP6 BEJA", None, 519962.11, 4065631.93, 147, 207, "Beja", "MY-MJD"),
        ("1485900130", "SLOUGUIA", "Mejerdah", 546325.35, 4049324.39, 67, 20995, "Mejerdah", "BS-MJD"),
        ("1485801890", "AVAL KHALLED", None, 535489.64, 4044793.93, 90, 449, "Medjerdah", "MY-MJD"),
        ("1485900139", "MEJEZ GP5", "Mejerdah", 554423.34, 4055163.76, 43, 21000, "Mejerdah", "BS-MJD"),
        ("1485900140", "MEJEZ ELMOURADI", "Mejerdah", 554187.86, 4056108.94, 40, 21000, "Mejerdah", "BS-MJD"),
        ("1485900141", "EL HERRI", "Mejerdah", 559412.43, 4064233.79, 40, 21910, "Mejerdah", "BS-MJD"),
        ("1485802270", "LAHMAR GP5", "Lahmar", 563553.84, 4055959.57, 82, 520, "Mejerdah", "BS-MJD"),
    ],
    "JENDOUBA": [
        ("1483800150", "TABARKA", "Kébir", 478023, 4085502, 5, 165, "Tabarka", "ND-ICHK"),
        ("1483800110", "PONT ROUTE BOU TERFES", "Bou Terfes", None, None, 23, 2081, "Tabarka", "ND-ICHK"),
        ("1485001110", "RARAI SUPERIEUR", "Rarai", 442202, 4034887, 230, 91, "Rarai", "HT-MJD"),
        ("1485001160", "RARAI PLAINE", "Rarai", 459024.73, 4037832.9, 175, 370, "Rarai", "HT-MJD"),
        ("1485003245", "BAIN ROMAINS", "Hammam", None, None, 230, 29.8, "Rarai", "HT-MJD"),
        ("1485400110", "GHARDIMAOU", "Mejerdah", 449355.47, 4034112.42, 192, 1480, "Mejerdah", "HT-MJD"),
        ("1485400111", "GHARDIMAOU PVF", "Mejerdah", 447876.125, 4031485.75, None, 1434.52, "Mejerdah", "HT-MJD"),
        ("1485400105", "PVF", "Mejerdah", None, None, None, 2301410, "Mejerdah", "HT-MJD"),
        ("1485400160", "JENDOUBA", "Mejerdah", 479257.9, 4039545.66, 142, 2410, "Mejerdah", "HT-MJD"),
        ("1485400180", "BOU SALEM GP6", "Mejerdah", 496980.46, 4050557.95, 127, 16330, "Mejerdah", "HT-MJD"),
        ("1483902060", "HAMMAM BOURGUIBA", "Mellila", 462093, 4069256, 130, 3083, "Barbar", "ND-ICHK"),
        ("1483900150", "JOUEOUDA", "Barbar", 459381, 4058572, 190, 108.6, "Barbar", "ND-ICHK"),
        ("1485303510", "FERNANA", "Rhezaia", 473254, 4054877, 230, 137, "Rhezaia", "HT-MJD"),
        ("1485101211", "MELLEGUE GP17", "Mellègue", 477464.22, 4028848.19, None, 11000, "Mellegue", "HT-MJD"),
    ],
    "KEF": [
        ("1485101210", "MELLEGUE K13", "Melleque", 454610, 3996638, 327, 9000, "Mellègue", "HT-MJD"),
        ("1485104380", "PONT ROUTE RMEL", "Rmel", 467559, 3996372, 162, 1520, "Mellègue", "HT-MJD"),
        ("1485100506", "PONT ROUTE SARRATH", "Sarrath", 460806, 3962234, 565, 1520, "Mellègue", "HT-MJD"),
        ("1485106125", "SIDI ABDELKADER", "Haidra", 450568, 3935106, 735, 328, "Mellègue", "HT-MJD"),
        ("1485201355", "SIDI MEDIEN", "Tessa", 495570, 4017708, 280, 1952, "Tessa", "MY-MJD"),
        ("1485201356", "TESSA PONT RTE", "Tessa", 495351, 4002975, 350, 1950, "Tessa", "MY-MJD"),
    ],
    "SILIANA": [
        ("1485501610", "PONT GP4 SILIANA", "Siliana", 535230.77, 3992432.06, 413, 743, "Siliana", "MY-MJD"),
        ("1485504670", "ENTREE PLAINE SILIANA", "Ousafa", 538783, 3979305, 508, 390, "Siliana", "MY-MJD"),
    ],
    "BEN AROUS": [
        ("1484100180", "LA MADELEINE", "Miliane", 611922.35, 4065086.4, 10, 1946, "Miliane", "CB-MI"),
        ("1484102580", "AVAL EL HMA", None, 613455, 4058721, None, 32221, "Miliane", "CB-MI"),
    ],
    "NABEUL": [
        ("1484200150", "PONT ROUTE N41 EL BEY", "El Bey", 633397, 4060558, 14, 464, "Grombalia", "CB-MI"),
        ("1484501510", "JAUGEAGE EL OUIDIANE", "El Ouidiane", 666616, 4075377, 35, 568, "Lebna", "CB-MI"),
        ("1484700120", "PONT ROUTE N15 SOUHIL", "Souhil", 652518, 4038316, 50, 14, "FlancSud", "CB-MI"),
    ],
    "ZAGHOUAN": [
        ("1484100110", "TUBURBO MAJUS", "Miliane", 581667.63, 4028058.18, 171, 748.3, "Miliane", "CB-MI"),
        ("1484800540", "PONT NOIR", "Esbaïhia", 608578.47, 4029622.32, 113, 224, "Rmel", "CB-MI"),
    ],
    "KAIROUAN": [
        ("1486100170", "HAFFOUZ TELEPERIQUE", "Merguelli", 559484, 3942831, 250, 675, "Merguelli", "SBK"),
        ("1486100340", "KEF EL ABIODH", "Skhira", 550977.36, 3955437.4, 600, 188, "Merguelli", "SBK"),
        ("1486102250", "ZEBBES TELEPERIQUE", "Zebbes", 555075, 3943461, 320, 180, "Merguelli", "SBK"),
    ],
    "KASSERINE": [
        ("1486200110", "CASSIS AIN SABOUN", "Hatob", 510250.02, 3935088.59, 560, 813, "Hatob", "SBK"),
        ("1486300140", "KHANGUET ZAZIA", "Hatab", 510521.09, 3883087.58, 537, 2200, "Hatab", "SBK"),
    ],
    "SIDI BOUZID": [
        ("1486300220", "BLED LASSOUED", "Negada", 544975.07, 3898378.74, 295, 5290, "Hatab", "SBK"),
        ("1486300210", "CASSIS GP3 EL FEKKA", "El Fekka", 524572.23, 3875281.01, 396, 2637, "Hatab", "SBK"),
    ],
    "SOUSSE": [
        ("1484900430", "ENFIDHA", "El Breck", 624798, 3999944, 17, 65.4, "Nord", "CB-MI"),
        ("1487900230", "KALAA SGHIRA", "Laya", 640720, 3965684, 20, 149.25, "Sousse", "SSS"),
        ("1487900330", "HAMMAM SOUSSE", "Laya", 643504, 3969870, 8, 217, "Sousse", "SSS"),
    ],
    "SFAX": [
        ("1487401010", "PONT VOIE FERREE CHAFFAR", "Chaffar", 643165, 3825113, 15, 236, "Sahel Sfax", "SSS"),
        ("1487402050", "SIDI SALAH", "Sidi Salah", 660503, 3860237, 35, 211, "Sahel Sfax", "SSS"),
        ("1487301090", "PONT VOIE FERREE OUADRANE", "Ouadrane", 608752, 3814107, 46, 2700, "Sahel Sfax", "SSS"),
        ("1487500110", "PONT VOIE FERREE MAAOU", "Maaou", 657523, 3842013, 55, 41, "Aqareb", "SSS"),
    ],
    "GAFSA": [
        ("1488200180", "CASSI GP3 BAIECH", "Baiech", 481197, 3807352, 290, 2900, "Baiech", "CHG-LB"),
        ("1488201570", "SIDI AICH", "Sidi Aich", 477582, 3842800, 525, 1780, "Baiech", "CHG-LB"),
        ("1488201630", "SIDI BOUBAKER", "Kébir", 450757, 3836359, 580, 2630, "Baiech", "CHG-LB"),
    ],
    "GABES": [
        ("1489500170", "TELEPHERIQUE EL HAMMA", "El Hamma", 570641.05, 3749365.14, 65, 5735, "Fedjej", "SE-JRD"),
        ("1489600280", "BARRAGE MATMATA NOUVELLE", "Jir", 594198, 3723823, 14, 5146, "Jir", "SE-JRD"),
    ],
    "MEDENINE": [
        ("1489804571", "KOUTINE TELEPHERIQUE", "Oum Zeussar", 628933, 3700930, 98, 276, "Golf Gabes", "SE-JRD"),
    ]
}

# ============================================================
# SCRIPT D'IMPORT - TABLE STATION UNIQUEMENT
# ============================================================

def import_stations_to_station_table():
    """
    Importe les stations dans la table 'station' uniquement
    La table station a la structure suivante:
    - code_station (PRIMARY KEY)
    - nom
    - cours_eau
    - x_utm
    - y_utm
    - altitude
    - superficie_km2
    - bassin
    - region (zone hydrographique)
    - gouvernorat
    - created_at
    - updated_at
    """
    
    # Connexion
    engine = create_engine('postgresql://postgres:postgres@localhost:5432/hydrometry')
    print("✅ Connexion établie")
    
    total_stations = 0
    total_gouvernorats = 0
    
    # Créer la table station si elle n'existe pas
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS station (
        code_station VARCHAR(50) PRIMARY KEY,
        nom VARCHAR(200),
        cours_eau VARCHAR(200),
        x_utm DECIMAL(15,3),
        y_utm DECIMAL(15,3),
        altitude DECIMAL(10,2),
        superficie_km2 DECIMAL(15,2),
        bassin VARCHAR(100),
        region VARCHAR(100),
        gouvernorat VARCHAR(100),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    with engine.begin() as conn:
        conn.execute(text(create_table_sql))
        print("✅ Table 'station' vérifiée/créée")
    
    for gouvernorat, stations in STATIONS_DATA.items():
        total_gouvernorats += 1
        print(f"\n📌 Importation du gouvernorat: {gouvernorat} ({len(stations)} stations)")
        
        for station in stations:
            try:
                code = station[0]
                
                # Vérifier si la station existe déjà
                check = "SELECT code_station FROM station WHERE code_station = :code"
                with engine.begin() as conn:
                    existing = conn.execute(text(check), {"code": code}).fetchone()
                
                if existing:
                    # Mise à jour
                    update_sql = """
                        UPDATE station SET
                            nom = :nom,
                            cours_eau = :cours_eau,
                            x_utm = :x_utm,
                            y_utm = :y_utm,
                            altitude = :altitude,
                            superficie_km2 = :superficie,
                            bassin = :bassin,
                            region = :region,
                            gouvernorat = :gouvernorat,
                            updated_at = NOW()
                        WHERE code_station = :code
                    """
                    with engine.begin() as conn:
                        conn.execute(text(update_sql), {
                            "code": code,
                            "nom": station[1],
                            "cours_eau": station[2],
                            "x_utm": station[3],
                            "y_utm": station[4],
                            "altitude": station[5],
                            "superficie": station[6],
                            "bassin": station[7],
                            "region": station[8],
                            "gouvernorat": gouvernorat
                        })
                    print(f"   ✅ Mise à jour: {code} - {station[1]}")
                else:
                    # Insertion
                    insert_sql = """
                        INSERT INTO station (
                            code_station, nom, cours_eau, x_utm, y_utm,
                            altitude, superficie_km2, bassin, region, gouvernorat,
                            created_at, updated_at
                        ) VALUES (
                            :code, :nom, :cours_eau, :x_utm, :y_utm,
                            :altitude, :superficie, :bassin, :region, :gouvernorat,
                            NOW(), NOW()
                        )
                    """
                    with engine.begin() as conn:
                        conn.execute(text(insert_sql), {
                            "code": code,
                            "nom": station[1],
                            "cours_eau": station[2],
                            "x_utm": station[3],
                            "y_utm": station[4],
                            "altitude": station[5],
                            "superficie": station[6],
                            "bassin": station[7],
                            "region": station[8],
                            "gouvernorat": gouvernorat
                        })
                    print(f"   ✅ Insertion: {code} - {station[1]}")
                
                total_stations += 1
                
            except Exception as e:
                print(f"   ❌ Erreur pour {station[0]}: {e}")
    
    # ============================================================
    # RÉSULTAT
    # ============================================================
    print("\n" + "="*60)
    print("📊 RÉSULTAT DE L'IMPORTATION")
    print("="*60)
    print(f"   Gouvernorats importés: {total_gouvernorats}")
    print(f"   Stations importées: {total_stations}")
    
    # Vérification
    df = pd.read_sql("""
        SELECT gouvernorat, COUNT(*) as nb 
        FROM station 
        WHERE gouvernorat IS NOT NULL
        GROUP BY gouvernorat
        ORDER BY gouvernorat
    """, engine)
    print("\n📋 Répartition par gouvernorat:")
    print(df.to_string(index=False))

if __name__ == "__main__":
    import_stations_to_station_table()