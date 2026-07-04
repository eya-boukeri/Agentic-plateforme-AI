"""
src/utils/hydrology_reader.py
Lecteur des données hydrologiques depuis Access
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.access_reader import AccessReader
import pandas as pd

class HydrologyAccessReader:
    """
    Lecteur spécifique pour les données hydrologiques Access
    (Adaptez les noms de tables selon votre base)
    """
    
    def __init__(self, access_file: str):
        self.access_file = access_file
        self.reader = AccessReader(access_file)
        self._tables = None
    
    def get_available_years(self) -> list:
        """
        Retourne les années disponibles
        (À adapter selon la structure de votre base)
        """
        query = """
            SELECT DISTINCT YEAR(DateDebit) as annee
            FROM Debits
            ORDER BY annee DESC
        """
        df = self.reader.read_sql(query)
        return df['annee'].tolist() if not df.empty else []
    
    def get_gouvernorats(self) -> list:
        """
        Retourne la liste des gouvernorats
        """
        query = """
            SELECT DISTINCT Gouvernorat
            FROM Stations
            WHERE Gouvernorat IS NOT NULL
            ORDER BY Gouvernorat
        """
        df = self.reader.read_sql(query)
        return df['Gouvernorat'].tolist() if not df.empty else []
    
    def get_stations(self, gouvernorat: str = None) -> pd.DataFrame:
        """
        Retourne la liste des stations
        """
        query = f"""
            SELECT 
                CodeStation,
                NomStation,
                CoursEau,
                Bassin,
                Gouvernorat,
                X_UTM,
                Y_UTM,
                Altitude,
                Superficie,
                SeuilCrue
            FROM Stations
        """
        if gouvernorat:
            query += f" WHERE Gouvernorat = '{gouvernorat}'"
        query += " ORDER BY NomStation"
        
        return self.reader.read_sql(query)
    
    def get_debits_journaliers(self, code_station: str, annee: int) -> pd.DataFrame:
        """
        Retourne les débits journaliers d'une station
        """
        query = f"""
            SELECT 
                DateDebit,
                Debit_m3s,
                Qualite
            FROM Debits
            WHERE CodeStation = '{code_station}'
              AND YEAR(DateDebit) = {annee}
            ORDER BY DateDebit
        """
        return self.reader.read_sql(query)
    
    def get_statistiques(self, code_station: str, annee: int) -> pd.DataFrame:
        """
        Retourne les statistiques annuelles
        """
        query = f"""
            SELECT 
                Annee,
                DebitMoyen,
                DebitMaxJour,
                DebitMinJour,
                VolumeTotal
            FROM Statistiques
            WHERE CodeStation = '{code_station}'
              AND Annee = {annee}
        """
        return self.reader.read_sql(query)
    
    def get_crues(self, code_station: str, annee: int) -> pd.DataFrame:
        """
        Retourne les crues d'une station
        """
        query = f"""
            SELECT 
                DateDebut,
                DateFin,
                DebitMax,
                TempsBase
            FROM Crues
            WHERE CodeStation = '{code_station}'
              AND Annee = {annee}
            ORDER BY DateDebut
        """
        return self.reader.read_sql(query)
    
    def get_stations_qualite(self, annee: int) -> pd.DataFrame:
        """
        Retourne la qualité des stations pour une année
        """
        query = f"""
            SELECT 
                s.CodeStation,
                s.NomStation,
                s.Gouvernorat,
                st.TauxRemplissage,
                st.Qualite
            FROM Stations s
            LEFT JOIN Statistiques st ON s.CodeStation = st.CodeStation
            WHERE st.Annee = {annee}
            ORDER BY st.Qualite DESC, s.NomStation
        """
        return self.reader.read_sql(query)
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """
        Exécute une requête SQL personnalisée
        """
        return self.reader.read_sql(query)
    
    def close(self):
        """Ferme la connexion"""
        self.reader.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()