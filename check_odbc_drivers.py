# script/check_odbc_drivers.py
import pyodbc

# Lister tous les pilotes ODBC installés
drivers = pyodbc.drivers()
print("Pilotes ODBC disponibles :")
for driver in drivers:
    print(f"  - {driver}")

# Vérifier si le pilote Access est installé
access_driver = None
for driver in drivers:
    if "Access" in driver or "ACE" in driver:
        access_driver = driver
        break

if access_driver:
    print(f"\n✅ Pilote Access trouvé : {access_driver}")
else:
    print("\n❌ Pilote Access non trouvé !")
    print("💡 Installez Microsoft Access Database Engine :")
    print("   https://www.microsoft.com/en-us/download/details.aspx?id=54920")