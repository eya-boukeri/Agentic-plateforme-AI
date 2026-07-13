"""
src/agents/agent_rag.py
Agent RAG intelligent - Utilise le LLM pour comprendre toute question
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import pandas as pd
import re
import json
from datetime import datetime

try:
    from agents.agent_llm import AgentLLM
except ImportError:
    print("⚠️ AgentLLM non disponible")
    AgentLLM = None


class AgentRAG:
    """Agent RAG - Récupération des données avec compréhension intelligente"""
    
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
        self._station_cols = self._resolve_station_columns()
        self._schema_info = None
        self._tables_info = None
        
        # Initialiser le LLM pour comprendre les questions
        self.llm = None
        if AgentLLM:
            try:
                self.llm = AgentLLM(model="tinyllama")
                if not self.llm.available or not self.llm.model_loaded:
                    self.llm = None
                    print("ℹ️ Mode dégradé: compréhension par mots-clés uniquement")
            except Exception:
                self.llm = None
                print("ℹ️ Mode dégradé: compréhension par mots-clés uniquement")

    def _resolve_station_columns(self):
        """Découvre dynamiquement les colonnes de la table station"""
        candidats = {
            "table": ["station", "stations_base", "stations"],
            "code": ["code_station", "Id_Station", "id_station"],
            "nom": ["nom", "Nom", "station"],
            "cours_eau": ["cours_eau", "Cours d'eau", "CoursEau"],
            "x_utm": ["x_utm", "X_UTM"],
            "y_utm": ["y_utm", "Y_UTM"],
            "altitude": ["altitude", "Altitude"],
            "superficie": ["superficie_km2", "Superficie", "Superficie_Bassin", "superficie"],
            "gouvernorat": ["gouvernorat", "Gouvernorat", "Gouv", "Zone", "Secteur", "region"],
        }

        resolved = {"table": None}
        try:
            from sqlalchemy import inspect
            insp = inspect(self.engine)
            existing_tables = {t.lower(): t for t in insp.get_table_names()}
            table_reel = None
            for candidate in candidats["table"]:
                if candidate.lower() in existing_tables:
                    table_reel = existing_tables[candidate.lower()]
                    break
            if table_reel is None:
                print("⚠️ Aucune table de stations trouvée")
                return resolved

            resolved["table"] = table_reel
            colonnes_reelles = {c["name"].lower(): c["name"] for c in insp.get_columns(table_reel)}

            for alias, options in candidats.items():
                if alias == "table":
                    continue
                trouve = None
                for option in options:
                    if option.lower() in colonnes_reelles:
                        trouve = colonnes_reelles[option.lower()]
                        break
                resolved[alias] = trouve

        except Exception as e:
            print(f"⚠️ Impossible d'inspecter le schema : {e}")

        return resolved

    def _get_detailed_schema(self):
        """Retourne un schéma détaillé de la base pour le prompt"""
        return """
Tables disponibles :

1. station
   - code_station : identifiant unique
   - nom : nom de la station
   - gouvernorat : gouvernorat (attention: PAS "gouvernoraat")
   - cours_eau : cours d'eau
   - superficie_km2 : superficie du bassin versant
   - x_utm, y_utm : coordonnées UTM
   - altitude : altitude

2. statistiques_annuelles (ATTENTION: le nom est au pluriel)
   - code_station : référence vers station
   - annee : année hydrologique
   - debit_moyen : débit moyen annuel (m³/s)
   - debit_max_jour : débit maximum journalier
   - debit_min_jour : débit minimum journalier
   - debit_max_inst : débit maximum instantané
   - debit_min_inst : débit minimum instantané
   - volume_total_hm3 : volume total écoulé (Hm³)

3. crues
   - code_station : référence vers station
   - annee : année
   - date_debut : début de la crue
   - date_fin : fin de la crue
   - debit_max_m3s : débit maximum de la crue

4. debits_journaliers
   - code_station : référence vers station
   - jour : date
   - debit_moyen : débit moyen journalier
   - debit_max : débit maximum journalier
   - debit_min : débit minimum journalier

Exemples de requêtes SQL :
- "Quel gouvernorat a le plus de stations ?"
  SELECT gouvernorat, COUNT(*) as nb_stations
  FROM station
  WHERE gouvernorat IS NOT NULL
  GROUP BY gouvernorat
  ORDER BY nb_stations DESC LIMIT 1

- "Quelle est la station avec le plus grand débit ?"
  SELECT s.nom, s.gouvernorat, st.debit_max_jour
  FROM statistiques_annuelles st
  JOIN station s ON st.code_station = s.code_station
  ORDER BY st.debit_max_jour DESC LIMIT 1
"""

    def _get_schema_info(self):
        """Récupère les informations sur toutes les tables"""
        if self._schema_info:
            return self._schema_info
        
        try:
            query = """
                SELECT 
                    table_name,
                    column_name,
                    data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
            """
            df = pd.read_sql(query, self.engine)
            self._schema_info = df
            return df
        except Exception as e:
            print(f"⚠️ Erreur récupération schéma: {e}")
            return pd.DataFrame()

    def _get_tables_info(self):
        """Récupère les informations sur les tables principales"""
        if self._tables_info:
            return self._tables_info
        
        try:
            tables_query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """
            tables_df = pd.read_sql(tables_query, self.engine)
            
            info = {}
            for table in tables_df['table_name']:
                cols_query = f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = '{table}'
                    AND table_schema = 'public'
                    ORDER BY ordinal_position
                """
                cols_df = pd.read_sql(cols_query, self.engine)
                info[table] = {
                    'columns': cols_df.to_dict('records'),
                    'sample': self._get_sample_data(table, 2)
                }
            
            self._tables_info = info
            return info
        except Exception as e:
            print(f"⚠️ Erreur récupération tables: {e}")
            return {}

    def _get_sample_data(self, table_name, limit=3):
        """Récupère un échantillon des données d'une table"""
        try:
            query = f'SELECT * FROM "{table_name}" LIMIT {limit}'
            df = pd.read_sql(query, self.engine)
            return df.to_dict('records') if not df.empty else []
        except:
            return []

    def _station_select_sql(self):
        """Construit le SELECT pour la table station"""
        cols = self._station_cols
        table = cols.get("table")
        if not table:
            return None, None

        def sql_col(alias, output_name, default_expr="NULL"):
            real = cols.get(alias)
            if real is None:
                return f'{default_expr} AS {output_name}'
            return f'"{real}" AS {output_name}'

        select_parts = [
            sql_col("code", "code_station"),
            sql_col("nom", "nom"),
            sql_col("cours_eau", "cours_eau"),
            sql_col("x_utm", "x_utm"),
            sql_col("y_utm", "y_utm"),
            sql_col("altitude", "altitude"),
            sql_col("superficie", "superficie_km2"),
            sql_col("gouvernorat", "gouvernorat"),
        ]
        return f'SELECT {", ".join(select_parts)} FROM "{table}"', cols.get("code")
    
    def close(self):
        if self.engine:
            self.engine.dispose()

    def clear_cache(self):
        self._cache = {}
    
    def _execute_query(self, query, params=None):
        """Exécute une requête SQL et retourne les résultats"""
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
            print(f"❌ Erreur SQL: {e}")
            return []

    def _understand_with_llm(self, question):
        """Comprend la question avec le LLM + validation"""
        if not self.llm:
            return None
        
        q = question.lower()
        
        # --- QUESTIONS COURANTES DÉTECTÉES PAR MOTS-CLÉS (PAS BESOIN DU LLM) ---
        
        # 1. Nombre de stations par gouvernorat
        if ("gouvernorat" in q or "gouv" in q) and ("plus" in q or "max" in q or "le plus" in q) and "station" in q:
            if "nombre" in q or "nb" in q or "stations" in q:
                return """
                    SELECT gouvernorat, COUNT(*) as nb_stations
                    FROM station
                    WHERE gouvernorat IS NOT NULL AND gouvernorat != ''
                    GROUP BY gouvernorat
                    ORDER BY nb_stations DESC
                    LIMIT 1
                """
        
        # 2. Station avec le plus grand débit
        if "station" in q and "débit" in q and ("plus grand" in q or "max" in q or "maximum" in q):
            return """
                SELECT s.nom, s.gouvernorat, st.debit_max_jour
                FROM statistiques_annuelles st
                JOIN station s ON st.code_station = s.code_station
                ORDER BY st.debit_max_jour DESC
                LIMIT 1
            """
        
        # 3. Nombre total de stations
        if ("combien" in q or "nombre" in q) and "station" in q and "total" in q:
            return "SELECT COUNT(*) as total_stations FROM station"
        
        # 4. Liste des cours d'eau
        if "cours d'eau" in q or "coupe d'eau" in q:
            if "liste" in q or "tous" in q:
                return "SELECT DISTINCT cours_eau FROM station WHERE cours_eau IS NOT NULL AND cours_eau != '' ORDER BY cours_eau"
        
        # --- QUESTIONS COMPLEXES : UTILISER LE LLM ---
        
        schema = self._get_detailed_schema()
        prompt = f"""
Tu es un expert SQL PostgreSQL.

Voici le schéma de la base de données :
{schema}

Question de l'utilisateur : "{question}"

Génère une requête SQL PostgreSQL qui répond à cette question.
Utilise EXACTEMENT les noms de tables et colonnes indiqués.
Retourne UNIQUEMENT la requête SQL, sans commentaires ni explications.

Requête SQL :
"""
        response = self.llm.generate(prompt, max_tokens=300)
        sql = self._extract_sql(response)
        
        # --- CORRECTIONS AUTOMATIQUES ---
        if sql:
            # Dictionnaire des corrections (erreurs typiques du LLM)
            corrections = {
                # Tables
                'statistiques_annuelle': 'statistiques_annuelles',
                'statistiques_annuel': 'statistiques_annuelles',
                
                # Colonnes gouvernorat (orthographe)
                'gouvernoraat': 'gouvernorat',
                'gouvernerat': 'gouvernorat',
                'gouvernement': 'gouvernorat',
                'gouvenerat': 'gouvernorat',
                'gouvenorat': 'gouvernorat',
                
                # Colonnes débit
                'debit_instantanee_max': 'debit_max_inst',
                'debit_instantanee_min': 'debit_min_inst',
                'debit_max_jouir': 'debit_max_jour',
                'debit_min_jouir': 'debit_min_jour',
                'debit_max_journalier': 'debit_max_jour',
                'debit_min_journalier': 'debit_min_jour',
                
                # Colonnes station
                'id_station': 'code_station',
                'station_id': 'code_station',
            }
            
            for wrong, correct in corrections.items():
                if wrong in sql:
                    sql = sql.replace(wrong, correct)
            
            # Vérification spéciale pour gouvernorat
            if 'gouvernorat' not in sql and ('gouvernoraat' in sql or 'gouvernerat' in sql):
                sql = re.sub(r'gouv\w+rat', 'gouvernorat', sql)
            
            return sql
        
        return None

    def _extract_sql(self, text):
        """Extrait la requête SQL du texte généré"""
        if not text:
            return None
        # Chercher SELECT ... ; ou SELECT ...
        pattern = r'SELECT\s+.*?(?:;|$)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(0).strip()
            if sql.endswith(';'):
                sql = sql[:-1]
            return sql
        return None

    def _understand_with_keywords(self, question):
        """Comprend la question avec des mots-clés (fallback)"""
        q = question.lower()
        
        # --- NOMBRE DE STATIONS ---
        if "nombre" in q and "station" in q:
            if "gouvernorat" in q or "gouv" in q:
                return """
                    SELECT gouvernorat, COUNT(*) as nb_stations
                    FROM station
                    WHERE gouvernorat IS NOT NULL
                    GROUP BY gouvernorat
                    ORDER BY nb_stations DESC
                """
            return "SELECT COUNT(*) as total_stations FROM station"
        
        # --- PLUS GRAND / MAXIMUM ---
        if "plus grand" in q or "maximum" in q or "le plus" in q:
            if "station" in q and ("nombre" in q or "nb" in q):
                return """
                    SELECT gouvernorat, COUNT(*) as nb_stations
                    FROM station
                    WHERE gouvernorat IS NOT NULL
                    GROUP BY gouvernorat
                    ORDER BY nb_stations DESC
                    LIMIT 1
                """
            if "débit" in q or "debit" in q:
                return """
                    SELECT s.nom, s.gouvernorat, st.debit_max_jour
                    FROM statistiques_annuelles st
                    JOIN station s ON st.code_station = s.code_station
                    ORDER BY st.debit_max_jour DESC
                    LIMIT 1
                """
            if "surface" in q or "superficie" in q:
                return """
                    SELECT nom, gouvernorat, superficie_km2
                    FROM station
                    ORDER BY superficie_km2 DESC NULLS LAST
                    LIMIT 1
                """
        
        # --- COURS D'EAU ---
        if "cours d'eau" in q or "coupe d'eau" in q:
            if "liste" in q or "tous" in q:
                return "SELECT DISTINCT cours_eau FROM station WHERE cours_eau IS NOT NULL AND cours_eau != '' ORDER BY cours_eau"
            if "station" in q:
                return "SELECT nom, cours_eau FROM station WHERE cours_eau IS NOT NULL AND cours_eau != '' ORDER BY cours_eau"
        
        # --- STATION SPÉCIFIQUE ---
        if "station" in q:
            match = re.search(r'station\s+([a-zA-Z\s\-]+)', q)
            if match:
                name = match.group(1).strip()
                return f"SELECT * FROM station WHERE LOWER(nom) LIKE LOWER('%{name}%')"
        
        # --- STATISTIQUES GÉNÉRALES ---
        if "statistique" in q or "général" in q:
            return """
                SELECT 
                    COUNT(*) as total_stations,
                    COUNT(DISTINCT gouvernorat) as nb_gouvernorats,
                    COUNT(DISTINCT cours_eau) as nb_cours_eau
                FROM station
            """
        
        # --- DÉBITS ---
        if "débit" in q or "debit" in q:
            if "moyen" in q:
                return """
                    SELECT s.nom, s.gouvernorat, st.debit_moyen
                    FROM statistiques_annuelles st
                    JOIN station s ON st.code_station = s.code_station
                    ORDER BY st.debit_moyen DESC
                    LIMIT 10
                """
            return """
                SELECT s.nom, s.gouvernorat, st.debit_max_jour
                FROM statistiques_annuelles st
                JOIN station s ON st.code_station = s.code_station
                ORDER BY st.debit_max_jour DESC
                LIMIT 10
            """
        
        # --- CRUES ---
        if "crue" in q or "crues" in q:
            return """
                SELECT s.nom, s.gouvernorat, c.debit_max_m3s, c.date_debut
                FROM crues c
                JOIN station s ON c.code_station = s.code_station
                ORDER BY c.debit_max_m3s DESC
                LIMIT 10
            """
        
        # Requête par défaut - retourner quelques stations
        return "SELECT * FROM station LIMIT 10"

    def understand_question(self, question):
        """Comprend la question et génère une requête SQL"""
        # 1. Essayer avec le LLM
        sql = self._understand_with_llm(question)
        if sql:
            print(f"🤖 LLM a généré: {sql[:100]}...")
            return sql
        
        # 2. Fallback: mots-clés
        print("🔍 Utilisation de la méthode par mots-clés")
        return self._understand_with_keywords(question)

    def get_stations_info(self, station_name=None, gouvernorat=None):
        base_select, _ = self._station_select_sql()
        if base_select is None:
            return []

        query = f"SELECT * FROM ({base_select}) s WHERE 1=1"
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
        base_select, _ = self._station_select_sql()
        if base_select is None:
            return []

        query = f"""
            SELECT DISTINCT gouvernorat
            FROM ({base_select}) s
            WHERE gouvernorat IS NOT NULL AND gouvernorat != ''
            ORDER BY gouvernorat
        """
        return self._execute_query(query)
    
    def get_statistiques_annuelles(self, code_station=None, annee=None, gouvernorat=None):
        base_select, _ = self._station_select_sql()
        if base_select is None:
            return []

        query = f"""
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
            JOIN ({base_select}) s ON st.code_station = s.code_station
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
        base_select, _ = self._station_select_sql()
        if base_select is None:
            return []

        query = f"""
            SELECT 
                COUNT(DISTINCT s.code_station) as nb_stations,
                COUNT(DISTINCT s.gouvernorat) as nb_gouvernorats,
                AVG(st.debit_moyen) as debit_moyen_global,
                MAX(st.debit_max_jour) as debit_max_global,
                SUM(st.volume_total_hm3) as volume_total_global,
                AVG(st.taux_remplissage) as taux_remplissage_moyen,
                MIN(st.annee) as annee_min,
                MAX(st.annee) as annee_max
            FROM ({base_select}) s
            JOIN statistiques_annuelles st ON s.code_station = st.code_station
        """
        return self._execute_query(query)
    
    def get_best_stations(self, critere="debit_moyen", limit=10):
        colonnes_autorisees = {"debit_moyen", "debit_max_jour", "volume_total_hm3"}
        if critere not in colonnes_autorisees:
            critere = "debit_moyen"

        base_select, _ = self._station_select_sql()
        if base_select is None:
            return []

        query = f"""
            SELECT 
                s.nom,
                s.gouvernorat,
                st.annee,
                st.debit_moyen,
                st.debit_max_jour,
                st.volume_total_hm3
            FROM statistiques_annuelles st
            JOIN ({base_select}) s ON st.code_station = s.code_station
            WHERE st.annee = (SELECT MAX(annee) FROM statistiques_annuelles)
            ORDER BY st.{critere} DESC
            LIMIT %s
        """
        return self._execute_query(query, (limit,))
    
    def get_crues(self, station_name=None, gouvernorat=None, annee=None, limit=20):
        base_select, _ = self._station_select_sql()
        if base_select is None:
            return []

        query = f"""
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
            JOIN ({base_select}) s ON c.code_station = s.code_station
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
    
    def get_anomalies(self, code_station=None, gouvernorat=None, gravite=None, limit=100):
        base_select, _ = self._station_select_sql()
        if base_select is None:
            return []

        query = f"""
            SELECT 
                a.*,
                s.nom as station,
                s.gouvernorat
            FROM anomalies a
            JOIN ({base_select}) s ON a.code_station = s.code_station
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
    """
    Orchestrateur RAG intelligent
    - Utilise le LLM pour comprendre les questions
    - Exécute les requêtes SQL
    - Formate les réponses
    """
    
    def __init__(self, db_config=None, use_llm=True):
        self.rag = AgentRAG(db_config)
        self.use_llm = use_llm
        self._current_gouvernorat = None
        self._current_annee = None
        self._current_station = None
        
        # Le LLM est déjà initialisé dans AgentRAG
        self.llm = self.rag.llm
        
        print("✅ AgentRAGOrchestrateur intelligent initialisé")
    
    def close(self):
        self.rag.close()
    
    def answer(self, question):
        """
        Répond à n'importe quelle question
        1. Comprend la question avec le LLM (ou mots-clés)
        2. Exécute la requête SQL
        3. Formate la réponse
        """
        print(f"🔍 Question: {question}")
        
        # 1. Comprendre la question et générer SQL
        sql = self.rag.understand_question(question)
        print(f"📝 SQL généré: {sql}")
        
        # 2. Exécuter la requête
        data = self.rag._execute_query(sql)
        
        # 3. Formater la réponse
        return self._format_answer(question, data, sql)
    
    def _format_answer(self, question, data, sql):
        """Formate la réponse de manière naturelle"""
        if not data:
            return "Aucune donnée trouvée pour votre question."
        
        # Si le LLM est disponible, l'utiliser pour enrichir la réponse
        if self.use_llm and self.llm:
            try:
                intent = "smart_query"
                response = self.llm.enrich_response(question, data, intent)
                if response:
                    return response
            except Exception as e:
                print(f"⚠️ Erreur enrichissement LLM: {e}")
        
        # Formatage basique
        if len(data) == 1:
            row = data[0]
            parts = []
            for key, value in row.items():
                if value is not None and key not in ['id', 'code_station']:
                    if isinstance(value, float):
                        parts.append(f"{key}: {value:.2f}")
                    else:
                        parts.append(f"{key}: {value}")
            if parts:
                return "📊 " + ", ".join(parts)
        
        # Si plusieurs résultats
        if len(data) > 1:
            if data:
                keys = list(data[0].keys())
                lines = [f"📊 {len(data)} résultat(s):"]
                for i, row in enumerate(data[:10], 1):
                    display_parts = []
                    for key in keys[:4]:
                        if key not in ['id', 'code_station']:
                            value = row.get(key)
                            if value is not None:
                                if isinstance(value, float):
                                    display_parts.append(f"{value:.2f}")
                                else:
                                    display_parts.append(str(value))
                    if display_parts:
                        lines.append(f"  {i}. " + " | ".join(display_parts))
                return "\n".join(lines)
        
        return f"📊 {len(data)} résultat(s) trouvé(s)"


if __name__ == "__main__":
    print("="*60)
    print("🧠 TEST SMART RAG")
    print("="*60)
    
    rag = AgentRAGOrchestrator()
    try:
        questions = [
            "Quel gouvernorat a le plus grand nombre de stations ?",
            "Quelle est la station avec le plus grand débit ?",
            "Donne-moi la liste des cours d'eau",
            "Quelles sont les stations du gouvernorat de Jendouba ?",
            "Combien y a-t-il de stations en tout ?"
        ]
        for q in questions:
            print("\n" + "-"*60)
            print(f"❓ {q}")
            print("-"*60)
            print(rag.answer(q))
    finally:
        rag.close()