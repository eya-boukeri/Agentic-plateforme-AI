import pyodbc
import os

print("=" * 60)
print("🧪 TEST DE CONNEXION ACCESS (SANS PANDAS)")
print("=" * 60)

# Chemin de votre base
db_path = r"C:\Users\Admin\Desktop\stage\2019_2020.mdb"

# Vérifier si le fichier existe
if not os.path.exists(db_path):
    print(f"❌ Fichier non trouvé: {db_path}")
    print("💡 Vérifiez le chemin du fichier")
    exit()

print(f"✅ Fichier trouvé: {db_path}")

# Essayer différents noms de pilotes Access
drivers_to_try = [
    "Microsoft Access Driver (*.mdb)",
    "Driver do Microsoft Access (*.mdb)",
    "Microsoft Access-Treiber (*.mdb)"
]

print("\n📌 Test de connexion...")

for driver in drivers_to_try:
    try:
        conn_str = f"DRIVER={{{driver}}};DBQ={db_path};"
        print(f"\nTest avec: {driver}")
        conn = pyodbc.connect(conn_str)
        print("✅ Connexion réussie !")
        
        # Lister les tables
        cursor = conn.cursor()
        cursor.tables()
        tables = [row[2] for row in cursor.fetchall() if row[3] == 'TABLE']
        print(f"📋 Tables trouvées: {tables}")
        
        conn.close()
        break
    except Exception as e:
        print(f"❌ Erreur: {e}")

print("\n" + "=" * 60)