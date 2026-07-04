"""
src/agents/agent_calcul.py
Agent Calcul - Statistiques hydrométriques
Version corrigée avec les bons noms de colonnes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy import create_engine

class AgentCalcul:
    def __init__(self, db_config=None):
        self.db_host = db_config.get('host', 'localhost') if db_config else 'localhost'
        self.db_port = db_config.get('port', 5432) if db_config else 5432
        self.db_name = db_config.get('database', 'hydrometry') if db_config else 'hydrometry'
        self.db_user = db_config.get('user', 'postgres') if db_config else 'postgres'
        self.db_password = db_config.get('password', 'postgres') if db_config else 'postgres'
        
        self.conn = None
        self.engine = None
        self.connect()
    
    def connect(self):
        try:
            self.engine = create_engine(
                f"postgresql+psycopg2://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
            )
            self.conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            print(f"✅ Connexion PostgreSQL : {self.db_host}:{self.db_port}/{self.db_name}")
        except Exception as e:
            print(f"❌ Erreur de connexion : {e}")
            raise
    
    def close(self):
        if self.conn:
            self.conn.close()
        if self.engine:
            self.engine.dispose()
            print("🔒 Connexion fermée")
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statistiques_annuelles (
                id SERIAL PRIMARY KEY,
                code_station VARCHAR(50),
                annee INTEGER,
                debit_moyen DECIMAL(10,3),
                debit_max_jour DECIMAL(10,3),
                date_max_jour DATE,
                debit_min_jour DECIMAL(10,3),
                date_min_jour DATE,
                debit_max_inst DECIMAL(10,3),
                date_max_inst TIMESTAMP,
                debit_min_inst DECIMAL(10,3),
                date_min_inst TIMESTAMP,
                volume_total_hm3 DECIMAL(10,2),
                lame_ecoulee_mm DECIMAL(8,2),
                dc1 DECIMAL(10,3),
                dc3 DECIMAL(10,3),
                dc6 DECIMAL(10,3),
                dc9 DECIMAL(10,3),
                dc11 DECIMAL(10,3),
                dce DECIMAL(10,3),
                dcc DECIMAL(10,3),
                q10 DECIMAL(10,3),
                q50 DECIMAL(10,3),
                q90 DECIMAL(10,3),
                q95 DECIMAL(10,3),
                nb_jours_presents INTEGER,
                taux_remplissage DECIMAL(5,2),
                source VARCHAR(10),
                date_calcul TIMESTAMP DEFAULT NOW(),
                UNIQUE(code_station, annee)
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crues (
                id SERIAL PRIMARY KEY,
                code_station VARCHAR(50),
                annee INTEGER,
                date_debut TIMESTAMP,
                date_fin TIMESTAMP,
                temps_base_min INTEGER,
                temps_montee_min INTEGER,
                debit_debut DECIMAL(10,3),
                debit_fin DECIMAL(10,3),
                debit_max_m3s DECIMAL(10,3),
                volume_ecoule_hm3 DECIMAL(10,4),
                volume_ruiss_hm3 DECIMAL(10,4),
                lame_ecoulee_mm DECIMAL(8,3),
                lame_ruiss_mm DECIMAL(8,3),
                date_calcul TIMESTAMP DEFAULT NOW()
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS debits_journaliers (
                id SERIAL PRIMARY KEY,
                code_station VARCHAR(50),
                jour DATE,
                debit_moyen DECIMAL(10,3),
                debit_max DECIMAL(10,3),
                debit_min DECIMAL(10,3),
                debit_instantane_max DECIMAL(10,3),
                date_heure_max TIMESTAMP,
                debit_instantane_min DECIMAL(10,3),
                date_heure_min TIMESTAMP,
                nb_mesures INTEGER,
                source VARCHAR(10),
                annee INTEGER,
                date_calcul TIMESTAMP DEFAULT NOW(),
                UNIQUE(code_station, jour)
            );
        """)

        cursor.execute("""
            ALTER TABLE debits_journaliers
            ADD COLUMN IF NOT EXISTS debit_instantane_min DECIMAL(10,3);
        """)

        cursor.execute("""
            ALTER TABLE debits_journaliers
            ADD COLUMN IF NOT EXISTS date_heure_min TIMESTAMP;
        """)

        cursor.execute("""
            ALTER TABLE debits_journaliers
            ADD COLUMN IF NOT EXISTS annee INTEGER;
        """)

        cursor.execute("""
            ALTER TABLE statistiques_annuelles
            ADD COLUMN IF NOT EXISTS source VARCHAR(10);
        """)

        cursor.execute("""
            ALTER TABLE debits_journaliers
            DROP CONSTRAINT IF EXISTS debits_journaliers_code_station_fkey;
        """)

        cursor.execute("""
            ALTER TABLE statistiques_annuelles
            DROP CONSTRAINT IF EXISTS statistiques_annuelles_code_station_fkey;
        """)

        cursor.execute("""
            ALTER TABLE crues
            DROP CONSTRAINT IF EXISTS crues_code_station_fkey;
        """)

        cursor.execute("""
            ALTER TABLE hauteurs_brutes
            DROP CONSTRAINT IF EXISTS hauteurs_brutes_code_station_fkey;
        """)

        cursor.execute("""
            ALTER TABLE debits_journaliers_bruts
            DROP CONSTRAINT IF EXISTS debits_journaliers_bruts_code_station_fkey;
        """)

        cursor.execute("""
            ALTER TABLE courbes_tarage
            DROP CONSTRAINT IF EXISTS courbes_tarage_code_station_fkey;
        """)

        cursor.execute("""
            ALTER TABLE debits_instantanés
            DROP CONSTRAINT IF EXISTS debits_instantanés_code_station_fkey;
        """)

        cursor.execute("""
            ALTER TABLE anomalies
            DROP CONSTRAINT IF EXISTS anomalies_code_station_fkey;
        """)
        
        self.conn.commit()
        cursor.close()
        print("✅ Tables créées/vérifiées")
    
    def get_station_info(self, id_station):
        query = """
            SELECT 
                s."Id_Station" as code_station,
                s."Nom" as nom_station,
                s."Type_Station" as type_station,
                s."Pays" as pays,
                s."Zone" as zone,
                s."SousZone" as sous_zone,
                s."GrandBassin" as grand_bassin,
                s."Bassin" as bassin,
                NULL::numeric as superficie,
                NULL::numeric as x_utm,
                NULL::numeric as y_utm,
                NULL::numeric as altitude,
                NULL::date as date_mise_service
            FROM stations_base s
            WHERE s."Id_Station" = %s
        """
        return pd.read_sql(query, self.engine, params=(id_station,))
    
    def get_debits_station(self, id_station, annee):
        query = """
            SELECT 
                "Date",
                "Valeur" as debit_m3s,
                "Capteur",
                "Origine",
                "Qualite"
            FROM debits
            WHERE "Id_Station" = %s
              AND EXTRACT(YEAR FROM "Date") = %s
            ORDER BY "Date"
        """
        return pd.read_sql(query, self.engine, params=(id_station, annee))
    
    def has_j1_data(self, df):
        if 'capteur' not in df.columns:
            return False
        return 'J1' in df['capteur'].values
    
    def get_j1_data(self, df):
        if 'capteur' not in df.columns:
            return pd.DataFrame()
        
        df_j1 = df[df['capteur'].str.upper() == 'J1']
        
        if df_j1.empty:
            return pd.DataFrame()
        
        df_j1['jour'] = df_j1['Date'].dt.date
        df_j1.rename(columns={'debit_m3s': 'debit_moyen'}, inplace=True)
        
        df_j1['debit_max'] = df_j1['debit_moyen']
        df_j1['debit_min'] = df_j1['debit_moyen']
        df_j1['debit_instantane_max'] = df_j1['debit_moyen']
        df_j1['date_heure_max'] = df_j1['Date']
        df_j1['debit_instantane_min'] = df_j1['debit_moyen']
        df_j1['date_heure_min'] = df_j1['Date']
        df_j1['nb_mesures'] = 1
        df_j1['source'] = 'J1'
        
        return df_j1
    
    def agreger_i1_to_journalier(self, df):
        if df.empty:
            return pd.DataFrame()
        
        df_i1 = df[df['capteur'].str.upper() == 'I1'] if 'capteur' in df.columns else df
        
        if df_i1.empty:
            return pd.DataFrame()
        
        df_i1['jour'] = df_i1['Date'].dt.date
        
        journalier = df_i1.groupby('jour').agg({
            'debit_m3s': ['mean', 'max', 'min', 'count']
        }).reset_index()
        
        journalier.columns = ['jour', 'debit_moyen', 'debit_max', 'debit_min', 'nb_mesures']
        
        idx_max = df_i1['debit_m3s'].idxmax()
        if idx_max is not None:
            journalier['debit_instantane_max'] = df_i1.loc[idx_max, 'debit_m3s']
            journalier['date_heure_max'] = df_i1.loc[idx_max, 'Date']
        else:
            journalier['debit_instantane_max'] = None
            journalier['date_heure_max'] = None
        
        idx_min = df_i1['debit_m3s'].idxmin()
        if idx_min is not None:
            journalier['debit_instantane_min'] = df_i1.loc[idx_min, 'debit_m3s']
            journalier['date_heure_min'] = df_i1.loc[idx_min, 'Date']
        else:
            journalier['debit_instantane_min'] = None
            journalier['date_heure_min'] = None
        
        journalier['source'] = 'I1'
        
        return journalier
    
    def get_debits_journaliers(self, id_station, annee):
        df = self.get_debits_station(id_station, annee)
        
        if df.empty:
            return pd.DataFrame()
        
        if self.has_j1_data(df):
            return self.get_j1_data(df)
        else:
            return self.agreger_i1_to_journalier(df)
    
    def sauvegarder_debits_journaliers(self, id_station, annee, df_journalier):
        if df_journalier.empty:
            return
        
        cursor = self.conn.cursor()
        
        for _, row in df_journalier.iterrows():
            jour = row['jour']
            debit_moyen = row.get('debit_moyen', None)
            debit_max = row.get('debit_max', None)
            debit_min = row.get('debit_min', None)
            debit_instantane_max = row.get('debit_instantane_max', None)
            date_heure_max = row.get('date_heure_max', None)
            debit_instantane_min = row.get('debit_instantane_min', None)
            date_heure_min = row.get('date_heure_min', None)
            nb_mesures = row.get('nb_mesures', 96)
            source = row.get('source', 'I1')
            
            cursor.execute("""
                SELECT id FROM debits_journaliers 
                WHERE code_station = %s AND jour = %s
            """, (id_station, jour))
            
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("""
                    UPDATE debits_journaliers SET
                        debit_moyen = %s,
                        debit_max = %s,
                        debit_min = %s,
                        debit_instantane_max = %s,
                        date_heure_max = %s,
                        debit_instantane_min = %s,
                        date_heure_min = %s,
                        nb_mesures = %s,
                        source = %s,
                        annee = %s,
                        date_calcul = NOW()
                    WHERE code_station = %s AND jour = %s
                """, (
                    debit_moyen, debit_max, debit_min,
                    debit_instantane_max, date_heure_max,
                    debit_instantane_min, date_heure_min,
                    nb_mesures, source, annee,
                    id_station, jour
                ))
            else:
                cursor.execute("""
                    INSERT INTO debits_journaliers (
                        code_station, jour,
                        debit_moyen, debit_max, debit_min,
                        debit_instantane_max, date_heure_max,
                        debit_instantane_min, date_heure_min,
                        nb_mesures, source, annee
                    ) VALUES (
                        %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s
                    )
                """, (
                    id_station, jour,
                    debit_moyen, debit_max, debit_min,
                    debit_instantane_max, date_heure_max,
                    debit_instantane_min, date_heure_min,
                    nb_mesures, source, annee
                ))
        
        self.conn.commit()
        cursor.close()
        print(f"   ✅ {len(df_journalier)} jours sauvegardés dans debits_journaliers")
    
    def calculer_statistiques_annuelles(self, id_station, annee):
        print(f"\n📊 Calcul des statistiques pour {id_station} ({annee})")
        
        station = self.get_station_info(id_station)
        if station.empty:
            print(f"   ⚠️  Station {id_station} non trouvée")
            return None
        
        df = self.get_debits_journaliers(id_station, annee)
        
        if df.empty:
            print(f"   ⚠️  Aucun débit pour {id_station} en {annee}")
            return None
        
        debits = df['debit_moyen'].values
        
        if len(debits) == 0:
            return None
        
        stats = {
            'code_station': id_station,
            'annee': annee,
            'debit_moyen': np.mean(debits),
            'debit_max_jour': np.max(debits),
            'date_max_jour': df.loc[df['debit_moyen'].idxmax(), 'jour'],
            'debit_min_jour': np.min(debits),
            'date_min_jour': df.loc[df['debit_moyen'].idxmin(), 'jour'],
            'nb_jours_presents': len(debits)
        }
        
        if 'debit_instantane_max' in df.columns and not df['debit_instantane_max'].isna().all():
            stats['debit_max_inst'] = df['debit_instantane_max'].iloc[0]
            stats['date_max_inst'] = df['date_heure_max'].iloc[0]
        else:
            stats['debit_max_inst'] = np.max(debits)
            stats['date_max_inst'] = df.loc[df['debit_moyen'].idxmax(), 'jour']
        
        if 'debit_instantane_min' in df.columns and not df['debit_instantane_min'].isna().all():
            stats['debit_min_inst'] = df['debit_instantane_min'].iloc[0]
            stats['date_min_inst'] = df['date_heure_min'].iloc[0]
        else:
            stats['debit_min_inst'] = np.min(debits)
            stats['date_min_inst'] = df.loc[df['debit_moyen'].idxmin(), 'jour']
        
        stats['volume_total_hm3'] = np.sum(debits) * 86400 / 1e6
        
        if not station.empty and 'superficie' in station.columns:
            superficie = station['superficie'].iloc[0]
            if superficie and superficie > 0:
                stats['lame_ecoulee_mm'] = stats['volume_total_hm3'] / superficie * 1000
            else:
                stats['lame_ecoulee_mm'] = None
        else:
            stats['lame_ecoulee_mm'] = None
        
        debits_tries = sorted(debits, reverse=True)
        n = len(debits_tries)
        
        stats['dc1'] = debits_tries[0] if n > 0 else None
        stats['dc3'] = debits_tries[2] if n > 2 else None
        stats['dc6'] = debits_tries[5] if n > 5 else None
        stats['dc9'] = debits_tries[8] if n > 8 else None
        stats['dc11'] = debits_tries[10] if n > 10 else None
        stats['dce'] = debits_tries[int(0.97 * n)] if n > 0 else None
        stats['dcc'] = debits_tries[9] if n > 9 else None
        
        stats['q10'] = np.percentile(debits, 10)
        stats['q50'] = np.percentile(debits, 50)
        stats['q90'] = np.percentile(debits, 90)
        stats['q95'] = np.percentile(debits, 95)
        
        jours_attendus = 366 if (annee % 4 == 0 and (annee % 100 != 0 or annee % 400 == 0)) else 365
        stats['taux_remplissage'] = (stats['nb_jours_presents'] / jours_attendus) * 100
        stats['source'] = 'J1' if self.has_j1_data(df) else 'I1'
        
        return stats
    
    def sauvegarder_statistiques(self, stats):
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT id FROM statistiques_annuelles 
            WHERE code_station = %s AND annee = %s
        """, (stats['code_station'], stats['annee']))
        
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE statistiques_annuelles SET
                    debit_moyen = %s,
                    debit_max_jour = %s,
                    date_max_jour = %s,
                    debit_min_jour = %s,
                    date_min_jour = %s,
                    debit_max_inst = %s,
                    date_max_inst = %s,
                    debit_min_inst = %s,
                    date_min_inst = %s,
                    volume_total_hm3 = %s,
                    lame_ecoulee_mm = %s,
                    dc1 = %s, dc3 = %s, dc6 = %s, dc9 = %s, dc11 = %s, dce = %s, dcc = %s,
                    q10 = %s, q50 = %s, q90 = %s, q95 = %s,
                    nb_jours_presents = %s,
                    taux_remplissage = %s,
                    source = %s,
                    date_calcul = NOW()
                WHERE code_station = %s AND annee = %s
            """, (
                stats['debit_moyen'],
                stats['debit_max_jour'],
                stats['date_max_jour'],
                stats['debit_min_jour'],
                stats['date_min_jour'],
                stats['debit_max_inst'],
                stats['date_max_inst'],
                stats['debit_min_inst'],
                stats['date_min_inst'],
                stats['volume_total_hm3'],
                stats['lame_ecoulee_mm'],
                stats['dc1'], stats['dc3'], stats['dc6'], stats['dc9'], stats['dc11'], stats['dce'], stats['dcc'],
                stats['q10'], stats['q50'], stats['q90'], stats['q95'],
                stats['nb_jours_presents'],
                stats['taux_remplissage'],
                stats['source'],
                stats['code_station'],
                stats['annee']
            ))
            print(f"   ✅ Statistiques mises à jour pour {stats['code_station']} ({stats['annee']})")
        else:
            cursor.execute("""
                INSERT INTO statistiques_annuelles (
                    code_station, annee,
                    debit_moyen, debit_max_jour, date_max_jour, debit_min_jour, date_min_jour,
                    debit_max_inst, date_max_inst, debit_min_inst, date_min_inst,
                    volume_total_hm3, lame_ecoulee_mm,
                    dc1, dc3, dc6, dc9, dc11, dce, dcc,
                    q10, q50, q90, q95,
                    nb_jours_presents, taux_remplissage, source
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
            """, (
                stats['code_station'], stats['annee'],
                stats['debit_moyen'], stats['debit_max_jour'], stats['date_max_jour'],
                stats['debit_min_jour'], stats['date_min_jour'],
                stats['debit_max_inst'], stats['date_max_inst'],
                stats['debit_min_inst'], stats['date_min_inst'],
                stats['volume_total_hm3'], stats['lame_ecoulee_mm'],
                stats['dc1'], stats['dc3'], stats['dc6'], stats['dc9'], stats['dc11'], stats['dce'], stats['dcc'],
                stats['q10'], stats['q50'], stats['q90'], stats['q95'],
                stats['nb_jours_presents'], stats['taux_remplissage'], stats['source']
            ))
            print(f"   ✅ Statistiques insérées pour {stats['code_station']} ({stats['annee']})")
        
        self.conn.commit()
        cursor.close()
    
    def traiter_station(self, id_station, annee, seuil_crue=None):
        print(f"\n" + "="*60)
        print(f"📊 Traitement de {id_station} ({annee})")
        print("="*60)
        
        df_journalier = self.get_debits_journaliers(id_station, annee)
        if not df_journalier.empty:
            self.sauvegarder_debits_journaliers(id_station, annee, df_journalier)
        
        stats = self.calculer_statistiques_annuelles(id_station, annee)
        if stats:
            print(f"\n   📈 Résultats :")
            print(f"      Débit moyen : {stats['debit_moyen']:.3f} m³/s")
            print(f"      Débit max : {stats['debit_max_jour']:.3f} m³/s ({stats['date_max_jour']})")
            print(f"      Volume total : {stats['volume_total_hm3']:.2f} Hm³")
            print(f"      Taux remplissage : {stats['taux_remplissage']:.1f}%")
            print(f"      DC1 : {stats['dc1']:.3f} m³/s")
            print(f"      Source : {stats['source']}")
            self.sauvegarder_statistiques(stats)
        
        return stats
    
    def traiter_annee(self, annee, seuil_crue=None):
        print("\n" + "="*60)
        print(f"📊 TRAITEMENT DE L'ANNÉE {annee}")
        print("="*60)
        
        self.create_tables()
        
        cursor = self.conn.cursor()
        cursor.execute('SELECT DISTINCT "Id_Station" FROM debits ORDER BY "Id_Station"')
        stations = [row[0] for row in cursor.fetchall()]
        cursor.close()
        
        print(f"\n🏛️ {len(stations)} stations trouvées")
        
        results = []
        for id_station in stations:
            stats = self.traiter_station(id_station, annee, seuil_crue)
            if stats:
                results.append(stats)
        
        print("\n" + "="*60)
        print("📊 RÉSUMÉ DU TRAITEMENT")
        print("="*60)
        print(f"   Stations traitées : {len(results)}")
        
        if results:
            df_results = pd.DataFrame(results)
            print(f"   Débit moyen global : {df_results['debit_moyen'].mean():.3f} m³/s")
            print(f"   Volume total global : {df_results['volume_total_hm3'].sum():.2f} Hm³")
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM debits_journaliers WHERE annee = %s", (annee,))
        nb_jours = cursor.fetchone()[0]
        cursor.close()
        print(f"   Débits journaliers sauvegardés : {nb_jours} jours")
        
        return results

if __name__ == "__main__":
    print("\n" + "🔥"*30)
    print("AGENT CALCUL - TRAITEMENT HYDROMÉTRIQUE")
    print("🔥"*30)
    
    agent = AgentCalcul()
    
    try:
        results = agent.traiter_annee(2019)
        if results:
            pd.DataFrame(results).to_csv("output/stats_2019.csv", index=False)
            print(f"\n✅ Résultats sauvegardés dans output/stats_2019.csv")
    finally:
        agent.close()