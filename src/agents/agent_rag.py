"""
src/agents/agent_rag.py
Agent RAG - Version corrigée avec paramètres positionnels
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import pandas as pd
import re
from datetime import datetime

try:
    from agents.agent_llm import AgentLLM
except ImportError:
    print("⚠️ AgentLLM non disponible")
    AgentLLM = None


class AgentRAG:
    """Agent RAG - Récupération des données"""
    
    def __init__(self, db_config=None):
        self.db_host = db_config.get('host', 'localhost') if db_config else 'localhost'
        self.db_port = db_config.get('port', 5432) if db_config else 5432
        self.db_name = db_config.get('database', 'hydrometry') if db_config else 'hydrometry'
        self.db_user = db_config.get('user', 'postgres') if db_config else 'postgres'
        self.db_password = db_config.get('password', 'postgres') if db_config else 'postgres'
        
        db_url = URL.create(
            "postgresql+psycopg2",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
        self.engine = create_engine(db_url, connect_args={"client_encoding": "utf8"})
        print(f"✅ AgentRAG connecté")
        
        self._cache = {}
    
    def close(self):
        if self.engine:
            self.engine.dispose()
    
    def _execute_query(self, query, params=None):
        try:
            cache_key = f"{query}_{str(params)}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            if params:
                df = pd.read_sql(query, self.engine, params=params)
            else:
                df = pd.read_sql(query, self.engine)
                
            result = df.to_dict('records') if not df.empty else []
            self._cache[cache_key] = result
            return result
        except Exception as e:
            print(f"❌ Erreur RAG: {e}")
            return []
    
    def get_stations_info(self, station_name=None, gouvernorat=None):
        query = """
            SELECT 
                code_station,
                nom,
                cours_eau,
                x_utm,
                y_utm,
                altitude,
                superficie_km2,
                bassin,
                region,
                gouvernorat
            FROM station
            WHERE 1=1
        """
        params = []
        if station_name:
            query += " AND LOWER(nom) LIKE LOWER(%s)"
            params.append(f"%{station_name}%")
        if gouvernorat:
            query += " AND LOWER(gouvernorat) LIKE LOWER(%s)"
            params.append(f"%{gouvernorat}%")
        query += " ORDER BY nom"
        return self._execute_query(query, tuple(params) if params else None)
    
    def get_gouvernorats_list(self):
        query = """
            SELECT DISTINCT gouvernorat
            FROM station
            WHERE gouvernorat IS NOT NULL AND gouvernorat != ''
            ORDER BY gouvernorat
        """
        return self._execute_query(query)
    
    def get_statistiques_annuelles(self, code_station=None, annee=None, gouvernorat=None):
        query = """
            SELECT 
                s.nom,
                s.gouvernorat,
                st.annee,
                st.debit_moyen,
                st.debit_max_jour,
                st.date_max_jour,
                st.debit_min_jour,
                st.date_min_jour,
                st.debit_max_inst,
                st.date_max_inst,
                st.debit_min_inst,
                st.date_min_inst,
                st.volume_total_hm3,
                st.lame_ecoulee_mm,
                st.dc1, st.dc3, st.dc6, st.dc9, st.dc11,
                st.q10, st.q50, st.q90, st.q95,
                st.nb_jours_presents,
                st.taux_remplissage
            FROM statistiques_annuelles st
            JOIN station s ON st.code_station = s.code_station
            WHERE 1=1
        """
        params = []
        if code_station:
            query += " AND st.code_station = %s"
            params.append(code_station)
        if annee:
            query += " AND st.annee = %s"
            params.append(annee)
        if gouvernorat:
            query += " AND LOWER(s.gouvernorat) LIKE LOWER(%s)"
            params.append(f"%{gouvernorat}%")
        query += " ORDER BY st.annee DESC, st.debit_moyen DESC"
        return self._execute_query(query, tuple(params) if params else None)
    
    def get_global_stats(self):
        query = """
            SELECT 
                COUNT(DISTINCT s.code_station) as nb_stations,
                COUNT(DISTINCT s.gouvernorat) as nb_gouvernorats,
                AVG(st.debit_moyen) as debit_moyen_global,
                MAX(st.debit_max_jour) as debit_max_global,
                SUM(st.volume_total_hm3) as volume_total_global,
                AVG(st.taux_remplissage) as taux_remplissage_moyen,
                MIN(st.annee) as annee_min,
                MAX(st.annee) as annee_max
            FROM station s
            JOIN statistiques_annuelles st ON s.code_station = st.code_station
        """
        return self._execute_query(query)
    
    def get_best_stations(self, critere="debit_moyen", limit=10):
        query = f"""
            SELECT 
                s.nom,
                s.gouvernorat,
                st.annee,
                st.debit_moyen,
                st.debit_max_jour,
                st.volume_total_hm3
            FROM statistiques_annuelles st
            JOIN station s ON st.code_station = s.code_station
            WHERE st.annee = (SELECT MAX(annee) FROM statistiques_annuelles)
            ORDER BY st.{critere} DESC
            LIMIT %s
        """
        return self._execute_query(query, (limit,))
    
    def get_crues(self, station_name=None, gouvernorat=None, annee=None, limit=20):
        query = """
            SELECT 
                s.nom as station,
                s.gouvernorat,
                c.annee,
                c.date_debut,
                c.date_fin,
                c.temps_base_min,
                c.temps_montee_min,
                c.debit_debut,
                c.debit_fin,
                c.debit_max_m3s,
                c.volume_ecoule_hm3,
                c.volume_ruiss_hm3,
                c.lame_ecoulee_mm,
                c.lame_ruiss_mm,
                EXTRACT(EPOCH FROM (c.date_fin - c.date_debut))/3600 as duree_heures
            FROM crues c
            JOIN station s ON c.code_station = s.code_station
            WHERE 1=1
        """
        params = []
        if station_name:
            query += " AND LOWER(s.nom) LIKE LOWER(%s)"
            params.append(f"%{station_name}%")
        if gouvernorat:
            query += " AND LOWER(s.gouvernorat) LIKE LOWER(%s)"
            params.append(f"%{gouvernorat}%")
        if annee:
            query += " AND c.annee = %s"
            params.append(annee)
        query += " ORDER BY c.debit_max_m3s DESC LIMIT %s"
        params.append(limit)
        return self._execute_query(query, tuple(params) if params else None)
    
    def get_crues_summary(self, gouvernorat=None, annee=None):
        query = """
            SELECT 
                s.gouvernorat,
                COUNT(c.id) as nb_crues,
                MAX(c.debit_max_m3s) as debit_max,
                AVG(c.debit_max_m3s) as debit_moyen_crues,
                SUM(c.volume_ecoule_hm3) as volume_total_crues
            FROM crues c
            JOIN station s ON c.code_station = s.code_station
            WHERE 1=1
        """
        params = []
        if gouvernorat:
            query += " AND LOWER(s.gouvernorat) LIKE LOWER(%s)"
            params.append(f"%{gouvernorat}%")
        if annee:
            query += " AND c.annee = %s"
            params.append(annee)
        query += " GROUP BY s.gouvernorat ORDER BY debit_max DESC"
        return self._execute_query(query, tuple(params) if params else None)
    
    def get_anomalies(self, code_station=None, gouvernorat=None, gravite=None, limit=100):
        query = """
            SELECT 
                a.*,
                s.nom as station,
                s.gouvernorat
            FROM anomalies a
            JOIN station s ON a.code_station = s.code_station
            WHERE 1=1
        """
        params = []
        if code_station:
            query += " AND a.code_station = %s"
            params.append(code_station)
        if gouvernorat:
            query += " AND LOWER(s.gouvernorat) LIKE LOWER(%s)"
            params.append(f"%{gouvernorat}%")
        if gravite:
            query += " AND a.gravite = %s"
            params.append(gravite)
        query += " ORDER BY a.date_detection DESC LIMIT %s"
        params.append(limit)
        return self._execute_query(query, tuple(params) if params else None)


class AgentRAGOrchestrator:
    """Orchestrateur RAG"""
    
    def __init__(self, db_config=None, use_llm=True):
        self.rag = AgentRAG(db_config)
        self.use_llm = use_llm
        self.llm = None
        self._current_gouvernorat = None
        self._current_annee = None
        self._current_station = None
        
        if use_llm and AgentLLM:
            try:
                self.llm = AgentLLM(model="tinyllama")
                if not self.llm.available or not self.llm.model_loaded:
                    self.use_llm = False
            except Exception:
                self.use_llm = False
    
    def close(self):
        self.rag.close()
    
    def answer(self, question):
        self._extract_entities(question)
        intent = self._detect_intent(question)
        data = self._get_data(intent, question)
        
        if self.use_llm and self.llm:
            return self.llm.enrich_response(question, data, intent)
        else:
            return self._format_response(intent, data)
    
    def _extract_entities(self, question):
        q = question.lower()
        
        gouv_match = re.search(r'gouvernorat\s+de\s+([a-zA-Z\s\-]+)', q)
        if gouv_match:
            self._current_gouvernorat = gouv_match.group(1).strip()
        else:
            gouv_list = self.rag.get_gouvernorats_list()
            for g in gouv_list:
                if g['gouvernorat'].lower() in q:
                    self._current_gouvernorat = g['gouvernorat']
                    break
            else:
                self._current_gouvernorat = None
        
        year_match = re.search(r'(20\d{2})', q)
        self._current_annee = int(year_match.group(1)) if year_match else None
        
        station_match = re.search(r'station\s+([a-zA-Z\s\-]+)', q)
        self._current_station = station_match.group(1).strip() if station_match else None
    
    def _detect_intent(self, question):
        q = question.lower()
        if "statistique" in q or "général" in q:
            return "global_stats"
        if "débit" in q or "debit" in q:
            if "max" in q or "maximum" in q:
                return "debit_max"
            if "moyen" in q:
                return "debit_moyen"
            return "debit_info"
        if "crue" in q or "crues" in q:
            return "crues"
        if "volume" in q:
            return "volume_total"
        if "station" in q:
            return "station_info"
        if "anomalie" in q:
            return "anomalies"
        return "global_stats"
    
    def _get_data(self, intent, question):
        if intent == "global_stats":
            return self.rag.get_global_stats()
        elif intent == "debit_max":
            return self.rag.get_best_stations(critere="debit_max_jour", limit=10)
        elif intent == "debit_moyen":
            return self.rag.get_best_stations(critere="debit_moyen", limit=10)
        elif intent == "crues":
            return self.rag.get_crues(
                station_name=self._current_station,
                gouvernorat=self._current_gouvernorat,
                annee=self._current_annee
            )
        elif intent == "station_info":
            return self.rag.get_stations_info(
                station_name=self._current_station,
                gouvernorat=self._current_gouvernorat
            )
        elif intent == "volume_total":
            return self.rag.get_statistiques_annuelles(
                gouvernorat=self._current_gouvernorat,
                annee=self._current_annee
            )
        elif intent == "anomalies":
            return self.rag.get_anomalies(
                code_station=self._current_station,
                gouvernorat=self._current_gouvernorat
            )
        else:
            return self.rag.get_global_stats()
    
    def _format_response(self, intent, data):
        if not data:
            return "Aucune donnée trouvée."
        
        if intent == "global_stats":
            row = data[0]
            return f"""📈 **Statistiques générales :**
  • {int(row.get('nb_stations', 0))} stations
  • {int(row.get('nb_gouvernorats', 0))} gouvernorats
  • Débit moyen : {row.get('debit_moyen_global', 0):.2f} m³/s
  • Volume total : {row.get('volume_total_global', 0):.2f} Hm³
  • Débit max : {row.get('debit_max_global', 0):.2f} m³/s"""
        
        elif intent == "debit_max" or intent == "debit_moyen":
            lines = [f"📊 **Résultats :**"]
            for row in data[:10]:
                station = row.get('nom', 'Inconnue')
                gouv = row.get('gouvernorat', 'Inconnu')
                debit = row.get('debit_max_jour' if intent == "debit_max" else 'debit_moyen', 0)
                lines.append(f"  • {station} ({gouv}) : {debit:.2f} m³/s")
            return "\n".join(lines)
        
        elif intent == "crues":
            lines = ["🌊 **Crues :**"]
            for row in data[:10]:
                station = row.get('station', 'Inconnue')
                gouv = row.get('gouvernorat', 'Inconnu')
                debit = row.get('debit_max_m3s', 0)
                date_debut = row.get('date_debut', '')
                if date_debut:
                    date_debut = pd.to_datetime(date_debut).strftime('%d/%m/%Y')
                lines.append(f"  • {station} ({gouv}) : {debit:.2f} m³/s ({date_debut})")
            return "\n".join(lines)
        
        elif intent == "station_info":
            lines = ["📍 **Stations :**"]
            for row in data:
                lines.append(f"  • {row.get('nom', 'Inconnue')} ({row.get('code_station', '')})")
                lines.append(f"    Cours d'eau: {row.get('cours_eau', 'N/A')}")
                lines.append(f"    Gouvernorat: {row.get('gouvernorat', 'N/A')}")
            return "\n".join(lines)
        
        elif intent == "anomalies":
            lines = ["⚠️ **Anomalies :**"]
            for row in data[:10]:
                station = row.get('station', 'Inconnue')
                type_a = row.get('type_anomalie', 'Inconnu')
                date = row.get('date', '')
                if date:
                    date = pd.to_datetime(date).strftime('%d/%m/%Y')
                lines.append(f"  • {station}: {type_a} ({date})")
            return "\n".join(lines)
        
        return f"📊 {len(data)} résultat(s)"