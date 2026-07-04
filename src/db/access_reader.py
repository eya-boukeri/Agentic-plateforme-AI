import pyodbc
import pandas as pd

# Connexion
db_path = r"C:\Users\Admin\Desktop\stage\2019_2020.mdb"
conn_str = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + db_path + ";"

# Extraction et calcul
try:
    conn = pyodbc.connect(conn_str)
    
    # Remplacez "NomDeVotreTable" par le nom réel de votre table
    query = "SELECT * FROM Debits"
    df = pd.read_sql(query, conn)
    conn.close()
    
    # Nettoyer les données
    df['Valeur'] = df['Valeur'].str.replace(',', '.').astype(float)
    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y %H:%M:%S')
    
    # Créer une colonne avec uniquement la date
    df['Jour'] = df['Date'].dt.date
    
    # Calculer les débits journaliers
    debit_journalier = df.groupby('Jour')['Valeur'].sum().reset_index()
    debit_journalier.columns = ['Date', 'Debit_Journalier']
    
    print(debit_journalier)
    
except Exception as e:
    print(f"Erreur : {e}")