"""
src/agents/agent_rag.py
Agent RAG intelligent - Utilise le LLM pour comprendre toute question
"""

import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
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

try:
    import zvec
except ImportError:
    print("⚠️ Bibliothèque zvec non disponible (installez-la via 'pip install zvec')")
    zvec = None


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
                self.llm = AgentLLM()  # lit LLM_MODEL / LLM_HOST depuis .env (mistral par défaut)
                if not self.llm.available or not self.llm.model_loaded:
                    self.llm = None
                    print("ℹ️ Mode dégradé: compréhension par mots-clés uniquement")
            except Exception:
                self.llm = None
                print("ℹ️ Mode dégradé: compréhension par mots-clés uniquement")
        
        # Initialiser Zvec si disponible
        self.zvec_db = None
        if zvec:
            try:
                parent_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
                os.makedirs(parent_dir, exist_ok=True)
                db_dir = os.path.join(parent_dir, "zvec_store")
                
                # Définir le schéma Zvec
                schema = zvec.CollectionSchema(
                    name="stations_semantic",
                    fields=[
                        zvec.FieldSchema(name="nom", data_type=zvec.DataType.STRING),
                        zvec.FieldSchema(name="gouvernorat", data_type=zvec.DataType.STRING),
                        zvec.FieldSchema(name="cours_eau", data_type=zvec.DataType.STRING),
                    ],
                    vectors=[
                        zvec.VectorSchema(
                            name="embedding",
                            data_type=zvec.DataType.VECTOR_FP32,
                            dimension=768, # Nomic embed dimension
                            index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE)
                        )
                    ]
                )
                
                # Charger la collection existante ou la créer
                if os.path.exists(db_dir) and os.path.isdir(db_dir) and len(os.listdir(db_dir)) > 0:
                    try:
                        self.zvec_db = zvec.open(path=db_dir)
                        print(f"✅ Zvec connecté (ouvert) dans {db_dir}")
                    except Exception as e_open:
                        print(f"ℹ️ Impossible d'ouvrir Zvec : {e_open}. Tentative de re-création...")
                        self.zvec_db = zvec.create_and_open(path=db_dir, schema=schema)
                        print(f"✅ Zvec connecté (créé) dans {db_dir}")
                else:
                    if os.path.exists(db_dir):
                        try:
                            if os.path.isdir(db_dir):
                                os.rmdir(db_dir)
                            else:
                                os.remove(db_dir)
                        except:
                            pass
                    self.zvec_db = zvec.create_and_open(path=db_dir, schema=schema)
                    print(f"✅ Zvec connecté (créé) dans {db_dir}")
            except Exception as e:
                self.zvec_db = None
                print(f"⚠️ Erreur lors de l'initialisation de Zvec : {e}")


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
        """Retourne un schéma détaillé de la base généré dynamiquement pour le prompt"""
        tables_info = self._get_tables_info()
        if not tables_info:
            return "Aucune table disponible."
        
        schema_desc = "Tables disponibles dans la base de données :\n\n"
        for table_name, info in tables_info.items():
            schema_desc += f"- Table: {table_name}\n"
            schema_desc += "  Colonnes :\n"
            for col in info.get('columns', []):
                name = col.get('column_name')
                dtype = col.get('data_type')
                schema_desc += f"    * {name} ({dtype})\n"
            
            # Ajouter un échantillon de données pour aider le LLM à comprendre
            sample = info.get('sample', [])
            if sample:
                schema_desc += "  Exemple de ligne :\n"
                for row in sample[:1]:
                    clean_row = {}
                    for k, v in row.items():
                        if isinstance(v, (datetime, pd.Timestamp)):
                            clean_row[k] = v.isoformat()
                        else:
                            clean_row[k] = str(v) if v is not None else None
                    schema_desc += f"    {json.dumps(clean_row, ensure_ascii=False)}\n"
            schema_desc += "\n"
        
        # Conserver les exemples de requêtes SQL utiles pour guider le LLM
        schema_desc += """Exemples de requêtes SQL de référence :
- "Quel gouvernorat a le plus de stations ?"
  SELECT gouvernorat, COUNT(*) as nb_stations
  FROM station
  WHERE gouvernorat IS NOT NULL AND gouvernorat != ''
  GROUP BY gouvernorat
  ORDER BY nb_stations DESC LIMIT 1

- "Quelle est la station avec le plus grand débit ?"
  SELECT s.nom, s.gouvernorat, st.debit_max_jour
  FROM statistiques_annuelles st
  JOIN station s ON st.code_station = s.code_station
  ORDER BY st.debit_max_jour DESC LIMIT 1
"""
        return schema_desc

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
            with self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn)
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
            with self.engine.connect() as conn:
                tables_df = pd.read_sql(text(tables_query), conn)
            
            info = {}
            for table in tables_df['table_name']:
                cols_query = f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = '{table}'
                    AND table_schema = 'public'
                    ORDER BY ordinal_position
                """
                with self.engine.connect() as conn:
                    cols_df = pd.read_sql(text(cols_query), conn)
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
            with self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn)
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
            return self._execute_query_raising(query, params)
        except Exception as e:
            print(f"❌ Erreur SQL: {e}")
            return []

    def _execute_query_raising(self, query, params=None):
        """
        Comme _execute_query mais propage les erreurs SQL au lieu de les
        avaler. Utilisé quand l'appelant a besoin de savoir si la requête
        (notamment celle générée par le LLM) est réellement valide, pour
        pouvoir se rabattre sur une autre stratégie en cas d'échec.
        """
        cache_key = f"{query}_{str(params)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        with self.engine.connect() as conn:
            if params:
                if isinstance(params, (list, tuple)):
                    cursor_res = conn.exec_driver_sql(query, tuple(params))
                elif isinstance(params, dict):
                    cursor_res = conn.execute(text(query), params)
                else:
                    cursor_res = conn.exec_driver_sql(query, (params,))
            else:
                try:
                    cursor_res = conn.execute(text(query))
                except Exception:
                    cursor_res = conn.exec_driver_sql(query)

            rows = cursor_res.mappings().all()
            result = [dict(r) for r in rows]

        self._cache[cache_key] = result
        return result

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
                WHERE st.debit_max_jour::text <> 'NaN'
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

        # Les modèles renvoient souvent le SQL dans un bloc ```sql ... ``` :
        # on le déballe avant de chercher le SELECT, sinon la regex peut
        # capturer les ``` de fermeture ou du texte après le bloc.
        fence_match = re.search(r'```(?:sql)?\s*(.*?)```', text, re.IGNORECASE | re.DOTALL)
        if fence_match:
            text = fence_match.group(1)

        # Chercher SELECT ... ; ou SELECT ...
        pattern = r'SELECT\s+.*?(?:;|$)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            return None

        sql = match.group(0).strip()
        if sql.endswith(';'):
            sql = sql[:-1]

        if not self._is_safe_select(sql):
            print(f"⚠️ SQL généré par le LLM rejeté (non conforme) : {sql[:120]}...")
            return None

        return sql

    def _is_safe_select(self, sql):
        """
        Garde-fou : le SQL généré par le LLM ne doit être qu'une unique
        requête SELECT en lecture seule. On rejette tout ce qui contient
        des mots-clés de modification/DDL ou plusieurs instructions,
        pour éviter qu'une réponse mal formée (ou halluciné) du LLM
        n'exécute autre chose qu'une lecture sur la base.
        """
        if not sql:
            return False

        normalized = sql.strip().rstrip(';').strip()
        if not re.match(r'(?is)^\s*SELECT\b', normalized):
            return False

        # Une seule instruction : pas de point-virgule au milieu
        if ';' in normalized:
            return False

        forbidden = [
            'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE',
            'CREATE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE', 'ATTACH',
            'COPY', 'CALL', 'MERGE', '--', '/*'
        ]
        upper_sql = normalized.upper()
        for kw in forbidden:
            if kw in upper_sql:
                return False

        return True

    def _extraire_entites(self, question):
        """Extrait l'année, la date exacte, le gouvernorat et les stations d'une question en langage naturel."""
        q = question.lower().replace('é', 'e').replace('è', 'e').replace('ê', 'e')
        
        # 1. Date exacte ou année
        date_iso = None
        date_fr = None
        annee = None

        # Format DD/MM/YYYY ou DD-MM-YYYY
        m1 = re.search(r'\b(0?[1-9]|[12]\d|3[01])[/\-](0?[1-9]|1[0-2])[/\-](19\d{2}|20\d{2})\b', q)
        if m1:
            jour = m1.group(1).zfill(2)
            mois = m1.group(2).zfill(2)
            annee_str = m1.group(3)
            date_iso = f"{annee_str}-{mois}-{jour}"
            date_fr = f"{jour}/{mois}/{annee_str}"
            annee = int(annee_str)
        else:
            # Format YYYY-MM-DD
            m2 = re.search(r'\b(19\d{2}|20\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b', q)
            if m2:
                annee_str = m2.group(1)
                mois = m2.group(2).zfill(2)
                jour = m2.group(3).zfill(2)
                date_iso = f"{annee_str}-{mois}-{jour}"
                date_fr = f"{jour}/{mois}/{annee_str}"
                annee = int(annee_str)
            else:
                # Format textuel : 15 mai 2024 / 1er mai 2024
                mois_map = {
                    'janvier': '01', 'fevrier': '02', 'février': '02', 'mars': '03', 'avril': '04',
                    'mai': '05', 'juin': '06', 'juillet': '07', 'aout': '08', 'août': '08',
                    'septembre': '09', 'octobre': '10', 'novembre': '11', 'decembre': '12', 'décembre': '12'
                }
                pattern_text = r'\b(0?[1-9]|[12]\d|3[01]|1er)\s+(' + '|'.join(mois_map.keys()) + r')\s+(19\d{2}|20\d{2})\b'
                m3 = re.search(pattern_text, q)
                if m3:
                    jour_raw = m3.group(1).replace('1er', '01')
                    jour = jour_raw.zfill(2)
                    mois = mois_map[m3.group(2)]
                    annee_str = m3.group(3)
                    date_iso = f"{annee_str}-{mois}-{jour}"
                    date_fr = f"{jour}/{mois}/{annee_str}"
                    annee = int(annee_str)
                else:
                    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', q)
                    annee = int(year_match.group(1)) if year_match else None
        
        # 2. Gouvernorats tunisiens (avec gestion des variantes)
        GOUVS = [
            'ariana', 'beja', 'ben arous', 'bizerte', 'gabes', 'gafsa',
            'jendouba', 'kairouan', 'kasserine', 'kebili', 'le kef', 'kef',
            'mahdia', 'manouba', 'la manouba', 'medenine', 'monastir', 'nabeul',
            'sfax', 'sidi bouzid', 'siliana', 'sousse', 'tataouine', 'tozeur',
            'tunis', 'zaghouan'
        ]
        gouvernorat = None
        for g in GOUVS:
            if re.search(rf'\b{g}\b', q):
                if g in ('le kef', 'kef'):
                    gouvernorat = 'KEF'
                elif g in ('la manouba', 'manouba'):
                    gouvernorat = 'MANOUBA'
                else:
                    gouvernorat = g.upper()
                break
                
        # 3. Stations hydrométriques connues et alias
        stations = []
        aliases_stations = {
            'sidi salem': ['1485400180', '1485900129'],
            'bou salem': ['1485400180'],
            'medjez el bab': ['1485900139', '1485900140'],
            'medjez': ['1485900139', '1485900140'],
            'mejez el bab': ['1485900139', '1485900140'],
            'mejez': ['1485900139', '1485900140'],
            'pont el mouradi': ['1485900140'],
            'mellegue k13': ['1485101210'],
            'mellegue': ['1485101210', '1485101211'],
            'k13': ['1485101210'],
            'jendouba': ['1485400160'],
            'ghardimaou': ['1485400110', '1485400111'],
            'slouguia': ['1485900130'],
            'jedeida': ['1485900170'],
            'chemtou': ['1485400130'],
            'siliana': ['1485501610', '1485501635'],
            'khenguette zazia': ['1486300140'],
            'khenguette': ['1486300140'],
            'el herri': ['1485900141'],
            'oued beja': ['1485602240'],
            'tine': ['1483602050', '1483602040'],
            'joumine': ['1483600130'],
            'mateur': ['1483600130'],
            'la madelaine': ['1484100180'],
            'ain saboun': ['1486200110'],
        }
        for alias, codes in sorted(aliases_stations.items(), key=lambda x: -len(x[0])):
            if re.search(r'\b' + re.escape(alias) + r'\b', q):
                for c in codes:
                    if c not in stations:
                        stations.append(c)

        # 4. Station explicite nommée (ex: "station Atlantis", "station Oued El Kébir")
        station_nom_libre = None
        mots_superlatifs_ou_generiques = [
            'plus grand', 'plus petit', 'plus fort', 'plus faible', 'plus haut',
            'maximum', 'maximal', 'max', 'minimum', 'minimal', 'min',
            'record', 'moyen', 'moyenne', 'combien', 'nombre', 'liste', 'toutes',
            'tout', 'tous', 'total', 'avec le', 'avec la', 'ayant', 'qui a',
            'importante', 'important', 'principale', 'principales', 'oued', 'cours d\'eau'
        ]
        if 'station' in q and not stations and not any(w in q for w in mots_superlatifs_ou_generiques):
            m_st = re.search(r'station\s+(?:de\s+|du\s+|d\')?([a-zA-Z0-9\s\-]+)', q)
            if m_st:
                nom_pot = m_st.group(1).strip()
                nom_pot = re.sub(r'\b(en|dans|de|du|pour|l\'annee|annee|\d{4})\b.*', '', nom_pot).strip()
                if nom_pot and len(nom_pot) >= 3 and nom_pot not in ('tout', 'toutes', 'reseau', 'tunisie', 'mesure'):
                    station_nom_libre = nom_pot

        return annee, gouvernorat, stations, date_iso, date_fr, station_nom_libre

    def _understand_with_keywords(self, question, fallback_default=False):
        """Comprend la question avec extraction d'entités (date, année, gouvernorat, stations) et mots-clés"""
        q = question.lower()
        annee, gouvernorat, stations, date_iso, date_fr, station_nom_libre = self._extraire_entites(question)
        
        # --- DÉBITS JOURNALIERS À DATE SPÉCIFIQUE ---
        if date_iso:
            where_clauses = [f"d.jour = '{date_iso}'"]
            if stations:
                st_in = "'" + "','".join(stations) + "'"
                where_clauses.append(f"s.code_station IN ({st_in})")
            elif station_nom_libre:
                where_clauses.append(f"LOWER(s.nom) LIKE LOWER('%{station_nom_libre}%')")
            elif gouvernorat:
                where_clauses.append(f"UPPER(s.gouvernorat) LIKE '%{gouvernorat}%'")
            return f"""
                SELECT s.nom as station, s.gouvernorat, d.jour, d.debit_moyen, d.debit_max
                FROM debits_journaliers d
                JOIN station s ON d.code_station = s.code_station
                WHERE {" AND ".join(where_clauses)}
                ORDER BY d.debit_moyen DESC
            """

        # --- CRUES (avec fautes d'orthographe courantes : crus, crue, crues, inondation...) ---
        if any(w in q for w in ['crue', 'crues', 'crus', 'cru', 'inondation', 'inondations', 'pic']):
            where_clauses = ["1=1"]
            if stations:
                st_in = "'" + "','".join(stations) + "'"
                where_clauses.append(f"s.code_station IN ({st_in})")
            elif station_nom_libre:
                where_clauses.append(f"LOWER(s.nom) LIKE LOWER('%{station_nom_libre}%')")
            elif gouvernorat:
                where_clauses.append(f"UPPER(s.gouvernorat) LIKE '%{gouvernorat}%'")
            if annee:
                where_clauses.append(f"c.annee = {annee}")
            return f"""
                SELECT s.nom as station, s.gouvernorat, c.annee, c.debit_max_m3s, c.date_debut, c.volume_ecoule_hm3
                FROM crues c
                JOIN station s ON c.code_station = s.code_station
                WHERE {" AND ".join(where_clauses)}
                ORDER BY c.debit_max_m3s DESC
                LIMIT 10
            """
        # --- 1. GOUVERNORAT AVEC LE PLUS GRAND DÉBIT (MAXIMUM / RECORD) ---
        # (ex: "Quel gouvernorat a le plus grand débit ?", "gouvernorat au débit maximal")
        if ('gouvernorat' in q or 'gouv' in q) and any(w in q for w in ['plus grand', 'max', 'maximum', 'record', 'plus fort', 'plus eleve', 'plus élevé', 'superieur', 'fort', 'haut']) and any(w in q for w in ['débit', 'debit']):
            annee_clause1 = f"AND st.annee = {annee}" if annee else ""
            annee_clause2 = f"AND st2.annee = {annee}" if annee else ""
            return f"""
                SELECT s.gouvernorat, MAX(st.debit_max_jour) as max_debit,
                       (SELECT s2.nom FROM statistiques_annuelles st2 JOIN station s2 ON st2.code_station = s2.code_station WHERE s2.gouvernorat = s.gouvernorat AND st2.debit_max_jour::text <> 'NaN' {annee_clause2} ORDER BY st2.debit_max_jour DESC NULLS LAST LIMIT 1) as station_max,
                       (SELECT st2.annee FROM statistiques_annuelles st2 JOIN station s2 ON st2.code_station = s2.code_station WHERE s2.gouvernorat = s.gouvernorat AND st2.debit_max_jour::text <> 'NaN' {annee_clause2} ORDER BY st2.debit_max_jour DESC NULLS LAST LIMIT 1) as annee_max
                FROM statistiques_annuelles st
                JOIN station s ON st.code_station = s.code_station
                WHERE s.gouvernorat IS NOT NULL AND s.gouvernorat != '' AND st.debit_max_jour::text <> 'NaN' {annee_clause1}
                GROUP BY s.gouvernorat
                ORDER BY max_debit DESC
            """

        # --- 2. GOUVERNORAT AVEC LE PLUS GRAND VOLUME D'EAU (MAXIMUM / RECORD) ---
        # (ex: "Quel gouvernorat a le plus grand volume ?", "gouvernorat avec le plus de volume d'eau")
        if ('gouvernorat' in q or 'gouv' in q) and any(w in q for w in ['plus grand', 'max', 'maximum', 'record', 'plus fort', 'plus eleve', 'plus élevé', 'plus haut', 'haut']) and any(w in q for w in ['volume', 'hm3']):
            annee_clause1 = f"AND st.annee = {annee}" if annee else ""
            annee_clause2 = f"AND st2.annee = {annee}" if annee else ""
            return f"""
                SELECT s.gouvernorat, MAX(st.volume_total_hm3) as max_volume,
                       (SELECT s2.nom FROM statistiques_annuelles st2 JOIN station s2 ON st2.code_station = s2.code_station WHERE s2.gouvernorat = s.gouvernorat AND st2.volume_total_hm3::text <> 'NaN' {annee_clause2} ORDER BY st2.volume_total_hm3 DESC NULLS LAST LIMIT 1) as station_max,
                       (SELECT st2.annee FROM statistiques_annuelles st2 JOIN station s2 ON st2.code_station = s2.code_station WHERE s2.gouvernorat = s.gouvernorat AND st2.volume_total_hm3::text <> 'NaN' {annee_clause2} ORDER BY st2.volume_total_hm3 DESC NULLS LAST LIMIT 1) as annee_max
                FROM statistiques_annuelles st
                JOIN station s ON st.code_station = s.code_station
                WHERE s.gouvernorat IS NOT NULL AND s.gouvernorat != '' AND st.volume_total_hm3::text <> 'NaN' {annee_clause1}
                GROUP BY s.gouvernorat
                ORDER BY max_volume DESC
            """

        # --- 3. GOUVERNORAT AVEC LE PLUS DE STATIONS / NOMBRE DE STATIONS PAR GOUVERNORAT ---
        # (ex: "Quel gouvernorat a le plus grand nombre de stations ?", "quel gouvernorat a le plus de stations ?")
        if ('gouvernorat' in q or 'gouv' in q) and any(w in q for w in ['plus', 'max', 'maximum', 'nombre', 'combien', 'nb']) and any(w in q for w in ['station', 'stations']):
            return """
                SELECT gouvernorat, COUNT(*) as nb_stations
                FROM station
                WHERE gouvernorat IS NOT NULL AND gouvernorat != ''
                GROUP BY gouvernorat
                ORDER BY nb_stations DESC
            """

        # --- 4. STATION AVEC LE PLUS GRAND DÉBIT (MAXIMUM / RECORD) ---
        # (ex: "Quelle est la station avec le plus grand débit ?", "station au débit maximal", "quel est le plus grand débit ?")
        if any(w in q for w in ['plus grand', 'max', 'maximum', 'record', 'plus fort', 'plus eleve', 'plus élevé']) and any(w in q for w in ['débit', 'debit']) and not ('gouvernorat' in q or 'gouv' in q):
            annee_clause = f"AND st.annee = {annee}" if annee else ""
            return f"""
                SELECT s.nom as station, s.gouvernorat, s.cours_eau, st.annee, st.debit_max_jour
                FROM statistiques_annuelles st
                JOIN station s ON st.code_station = s.code_station
                WHERE st.debit_max_jour::text <> 'NaN' {annee_clause}
                ORDER BY st.debit_max_jour DESC
                LIMIT 5
            """

        # --- 5. STATION AVEC LE PLUS GRAND VOLUME (MAXIMUM / RECORD) ---
        # (ex: "Quelle est la station avec le plus grand volume ?")
        if any(w in q for w in ['plus grand', 'max', 'maximum', 'record', 'plus fort', 'plus eleve', 'plus élevé']) and any(w in q for w in ['volume', 'hm3']) and not ('gouvernorat' in q or 'gouv' in q):
            annee_clause = f"AND st.annee = {annee}" if annee else ""
            return f"""
                SELECT s.nom as station, s.gouvernorat, s.cours_eau, st.annee, st.volume_total_hm3
                FROM statistiques_annuelles st
                JOIN station s ON st.code_station = s.code_station
                WHERE st.volume_total_hm3::text <> 'NaN' {annee_clause}
                ORDER BY st.volume_total_hm3 DESC
                LIMIT 5
            """

        # --- 6. NOMBRE TOTAL DE STATIONS ---
        # (ex: "Combien y a-t-il de stations en tout ?", "nombre total de stations")
        if any(w in q for w in ['combien', 'total', 'nombre total']) and any(w in q for w in ['station', 'stations']) and not ('gouvernorat' in q or 'gouv' in q):
            return "SELECT COUNT(*) as total_stations FROM station"

        # --- DÉBITS ET VOLUMES GÉNÉRAUX ---
        if any(w in q for w in ['débit', 'debit', 'volume', 'hm3', 'm3/s', 'ecoulement', 'écoulement', 'maximal', 'moyen']):
            if "volume" in q or "hm3" in q:
                where_clauses = ["st.volume_total_hm3::text <> 'NaN'"]
                if stations:
                    st_in = "'" + "','".join(stations) + "'"
                    where_clauses.append(f"s.code_station IN ({st_in})")
                elif station_nom_libre:
                    where_clauses.append(f"LOWER(s.nom) LIKE LOWER('%{station_nom_libre}%')")
                elif gouvernorat:
                    where_clauses.append(f"UPPER(s.gouvernorat) LIKE '%{gouvernorat}%'")
                if annee:
                    where_clauses.append(f"st.annee = {annee}")
                return f"""
                    SELECT s.nom as station, s.gouvernorat, st.annee, st.volume_total_hm3
                    FROM statistiques_annuelles st
                    JOIN station s ON st.code_station = s.code_station
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY st.volume_total_hm3 DESC
                    LIMIT 10
                """
            elif "moyen" in q or "moyenne" in q:
                where_clauses = ["st.debit_moyen::text <> 'NaN'"]
                if stations:
                    st_in = "'" + "','".join(stations) + "'"
                    where_clauses.append(f"s.code_station IN ({st_in})")
                elif station_nom_libre:
                    where_clauses.append(f"LOWER(s.nom) LIKE LOWER('%{station_nom_libre}%')")
                elif gouvernorat:
                    where_clauses.append(f"UPPER(s.gouvernorat) LIKE '%{gouvernorat}%'")
                if annee:
                    where_clauses.append(f"st.annee = {annee}")
                return f"""
                    SELECT s.nom as station, s.gouvernorat, st.annee, st.debit_moyen
                    FROM statistiques_annuelles st
                    JOIN station s ON st.code_station = s.code_station
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY st.debit_moyen DESC
                    LIMIT 10
                """
            else:
                where_clauses = ["st.debit_max_jour::text <> 'NaN'"]
                if stations:
                    st_in = "'" + "','".join(stations) + "'"
                    where_clauses.append(f"s.code_station IN ({st_in})")
                elif station_nom_libre:
                    where_clauses.append(f"LOWER(s.nom) LIKE LOWER('%{station_nom_libre}%')")
                elif gouvernorat:
                    where_clauses.append(f"UPPER(s.gouvernorat) LIKE '%{gouvernorat}%'")
                if annee:
                    where_clauses.append(f"st.annee = {annee}")
                return f"""
                    SELECT s.nom as station, s.gouvernorat, st.annee, st.debit_max_jour
                    FROM statistiques_annuelles st
                    JOIN station s ON st.code_station = s.code_station
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY st.debit_max_jour DESC
                    LIMIT 10
                """

        # --- DONNÉES / MESURES POUR UNE ANNÉE OU UNE STATION ---
        if annee or any(w in q for w in ['donnée', 'données', 'donnee', 'donnees', 'mesure', 'mesures']):
            where_clauses = ["1=1"]
            if stations:
                st_in = "'" + "','".join(stations) + "'"
                where_clauses.append(f"s.code_station IN ({st_in})")
            elif station_nom_libre:
                where_clauses.append(f"LOWER(s.nom) LIKE LOWER('%{station_nom_libre}%')")
            elif gouvernorat:
                where_clauses.append(f"UPPER(s.gouvernorat) LIKE '%{gouvernorat}%'")
            if annee:
                where_clauses.append(f"st.annee = {annee}")
            return f"""
                SELECT s.nom as station, s.gouvernorat, st.annee, st.debit_max_jour, st.debit_moyen, st.volume_total_hm3
                FROM statistiques_annuelles st
                JOIN station s ON st.code_station = s.code_station
                WHERE {" AND ".join(where_clauses)}
                ORDER BY st.debit_max_jour DESC
                LIMIT 10
            """

        # --- NOMBRE DE STATIONS (REPLI) ---
        if any(w in q for w in ['nombre', 'combien', 'total', 'nb']) and ('station' in q or 'stations' in q):
            if "gouvernorat" in q or "gouv" in q:
                return """
                    SELECT gouvernorat, COUNT(*) as nb_stations
                    FROM station
                    WHERE gouvernorat IS NOT NULL AND gouvernorat != ''
                    GROUP BY gouvernorat
                    ORDER BY nb_stations DESC
                """
            return "SELECT COUNT(*) as total_stations FROM station"

        # --- COURS D'EAU ---
        if "cours d'eau" in q or "coupe d'eau" in q or "oued" in q:
            if "liste" in q or "tous" in q:
                return "SELECT DISTINCT cours_eau FROM station WHERE cours_eau IS NOT NULL AND cours_eau != '' ORDER BY cours_eau"
            if "station" in q:
                return "SELECT nom, cours_eau FROM station WHERE cours_eau IS NOT NULL AND cours_eau != '' ORDER BY cours_eau"

        # --- STATIONS D'UN GOUVERNORAT ---
        if gouvernorat:
            return f"""
                SELECT nom as station, gouvernorat, cours_eau
                FROM station
                WHERE UPPER(gouvernorat) LIKE '%{gouvernorat}%'
                ORDER BY nom
                LIMIT 15
            """

        # --- STATION SPÉCIFIQUE ---
        if "station" in q and not any(w in q for w in ['combien', 'nombre', 'liste', 'toutes', 'tous']):
            match = re.search(r'station\s+(?:de\s+|du\s+|d\')?([a-zA-Z\s\-]+)', q)
            if match:
                name = match.group(1).strip()
                if name and name not in ('en tout', 'au total'):
                    return f"SELECT nom as station, gouvernorat, cours_eau FROM station WHERE LOWER(nom) LIKE LOWER('%{name}%')"

        # --- STATISTIQUES GÉNÉRALES ---
        if "statistique" in q or "général" in q or "global" in q:
            return """
                SELECT 
                    COUNT(*) as total_stations,
                    COUNT(DISTINCT gouvernorat) as nb_gouvernorats,
                    COUNT(DISTINCT cours_eau) as nb_cours_eau
                FROM station
            """

        if not fallback_default:
            return None

        return None

    def understand_question(self, question):
        """Comprend la question et génère une requête SQL"""
        # 1. Vérifier si la question correspond à une intention hydrométrique structurée
        # (rapide, déterministe et sans hallucination)
        sql = self._understand_with_keywords(question, fallback_default=False)
        if sql:
            print(f"🎯 Requête SQL déterministe générée (0s) : {sql.strip()[:90]}...")
            return sql

        # 2. Si question ouverte ou complexe, faire appel au LLM
        sql = self._understand_with_llm(question)
        if sql:
            print(f"🤖 LLM a généré: {sql[:100]}...")
            return sql
        
        # 3. Ne plus renvoyer de fallback aveugle sur 10 stations
        print("ℹ️ Aucune requête SQL déduite pour cette demande.")
        return None

    def indexer_stations_dans_zvec(self):
        """Lit toutes les stations de la base PostgreSQL et les indexe dans Zvec"""
        if not self.zvec_db:
            print("⚠️ Zvec non initialisé ou non disponible.")
            return False
        if not self.llm:
            print("⚠️ LLM non disponible pour générer les embeddings.")
            return False

        stations = self.get_stations_info()
        if not stations:
            print("⚠️ Aucune station récupérée depuis PostgreSQL.")
            return False

        print(f"🧬 Début de l'indexation de {len(stations)} stations dans Zvec...")
        count = 0
        for station in stations:
            code = station.get("code_station")
            nom = station.get("nom") or ""
            gouv = station.get("gouvernorat") or ""
            cours = station.get("cours_eau") or ""
            
            if not code:
                continue

            # Créer un texte descriptif riche à vectoriser
            desc = f"Station de mesure hydrométrique. Nom: {nom}. Gouvernorat: {gouv}. Cours d'eau: {cours}."
            
            # Générer l'embedding
            emb = self.llm.get_embedding(desc)
            if not emb:
                print(f"❌ Échec de génération d'embedding pour la station {nom}")
                continue

            # Inserer/mettre a jour dans Zvec.
            # IMPORTANT : upsert() et non insert() - insert() echoue si l'ID
            # existe deja (comportement documente de Zvec), ce qui aurait
            # fait planter cette fonction des le 2e lancement (par exemple
            # apres l'ajout de nouvelles stations). upsert() met a jour la
            # station si elle existe deja, l'insere sinon.
            self.zvec_db.upsert(zvec.Doc(
                id=str(code),
                vectors={"embedding": emb},
                fields={
                    "nom": str(nom),
                    "gouvernorat": str(gouv),
                    "cours_eau": str(cours)
                }
            ))
            count += 1
            if count % 10 == 0:
                print(f"   Indexed {count}/{len(stations)} stations...")

        # Optimiser l'index
        self.zvec_db.optimize()
        print(f"✅ Indexation terminée : {count} stations indexées avec succès.")
        return True

    def recherche_semantique_station(self, question, limit=5):
        """Effectue une recherche sémantique de stations dans Zvec"""
        if not self.zvec_db:
            print("⚠️ Zvec non disponible.")
            return []
        if not self.llm:
            print("⚠️ LLM non disponible.")
            return []

        emb = self.llm.get_embedding(question)
        if not emb:
            return []

        try:
            # IMPORTANT : la methode de recherche Zvec s'appelle query(),
            # pas search() - et les parametres sont queries=zvec.Query(...)
            # / topk=, pas vector=/vector_name=/limit=. L'ancienne version
            # levait une AttributeError des le premier appel.
            resultats = self.zvec_db.query(
                queries=zvec.Query(field_name="embedding", vector=emb),
                topk=limit,
            )

            out = []
            for doc in resultats:
                out.append({
                    "code_station": doc.id,
                    "nom": doc.fields.get("nom"),
                    "gouvernorat": doc.fields.get("gouvernorat"),
                    "cours_eau": doc.fields.get("cours_eau"),
                    "score": doc.score
                })
            return out
        except Exception as e:
            print(f"⚠️ Erreur recherche Zvec: {e}")
            return []

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
                (SELECT COUNT(*) FROM ({base_select}) s_all) as nb_stations,
                (SELECT COUNT(DISTINCT s_all.gouvernorat) FROM ({base_select}) s_all WHERE s_all.gouvernorat IS NOT NULL AND s_all.gouvernorat <> '') as nb_gouvernorats,
                AVG(st.debit_moyen) FILTER (WHERE st.debit_moyen::text <> 'NaN') as debit_moyen_global,
                MAX(st.debit_max_jour) FILTER (WHERE st.debit_max_jour::text <> 'NaN') as debit_max_global,
                SUM(st.volume_total_hm3) FILTER (WHERE st.volume_total_hm3::text <> 'NaN') as volume_total_global,
                AVG(st.taux_remplissage) as taux_remplissage_moyen,
                MIN(st.annee) as annee_min,
                MAX(st.annee) as annee_max
            FROM statistiques_annuelles st
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
              AND st.{critere} IS NOT NULL
              AND st.{critere}::text <> 'NaN'
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
        1. Essayer de comprendre la question et d'interroger la base via SQL
        2. Si aucun résultat et qu'il s'agit d'une recherche descriptive de station, faire une recherche sémantique avec Zvec.
        3. Si aucune donnée temporelle ou de mesure n'est trouvée, répondre explicitement qu'aucune donnée n'existe dans la base.
        4. Formater la réponse.
        """
        print(f"🔍 Question: {question}")
        
        data = None
        sql = None
        is_semantic_fallback = False

        # Extraire les entités pour vérifier s'il s'agit d'une recherche temporelle / de données
        annee, gouvernorat, stations, date_iso, date_fr, station_nom_libre = self.rag._extraire_entites(question)
        est_requete_donnees = bool(
            date_iso or annee or stations or station_nom_libre or any(
                w in question.lower() for w in [
                    'crue', 'crues', 'crus', 'inondation', 'debit', 'débit',
                    'volume', 'hm3', 'moyen', 'maximum', 'statistique', 'eau',
                    'donnée', 'données', 'donnee', 'donnees', 'mesure', 'mesures'
                ]
            )
        )
        
        # 1. Tenter la recherche SQL classique
        sql = self.rag.understand_question(question)
        if sql:
            print(f"📝 SQL généré: {sql}")
            try:
                data = self.rag._execute_query_raising(sql)
            except Exception as e:
                print(f"⚠️ SQL invalide généré par le LLM ({e}) — repli sur les mots-clés")
                sql = self.rag._understand_with_keywords(question)
                print(f"📝 SQL de secours: {sql}")
                data = self.rag._execute_query(sql)
                
        # 2. Si pas de données trouvées dans la base :
        if not data or len(data) == 0:
            # Si le LLM a échoué par timeout (problème de ressources GPU)
            llm_err = getattr(self.rag.llm, 'last_error', None) if self.rag.llm else None
            if llm_err == 'timeout':
                return (
                    "⚠️ **Délai d'attente dépassé (Problème de GPU / LLM).**\n\n"
                    "Le modèle de langage local a mis trop de temps à répondre pour traiter cette question.\n\n"
                    "💡 **Cause :** Les ressources du GPU local (NVIDIA GeForce MX450 - 2 Go) sont insuffisantes "
                    "pour exécuter le modèle de 7.6 milliards de paramètres en local.\n\n"
                    "👉 **Recommandations :**\n"
                    "• Posez une question ciblée avec des termes hydrométriques précis (ex: *« Quel gouvernorat a le plus grand débit ? »*, *« Informations sur les crues »*, *« Stations de Béja »*).\n"
                    "• Ou relancez le modèle distant avec GPU dédié via Google Colab (`python maj_llm_host.py <url>`)."
                )

            # Ne faire de recherche sémantique Zvec QUE si c'est explicitement une recherche descriptive de station
            # et JAMAIS pour une demande de données à une date/période donnée !
            if not est_requete_donnees and self.rag.zvec_db and any(
                w in question.lower() for w in ['station', 'cherche', 'trouve', 'situe', 'localisation', 'ou se trouve', 'pres de']
            ):
                print("🔍 Tentative de recherche sémantique de station via Zvec...")
                semantic_results = self.rag.recherche_semantique_station(question, limit=5)
                if semantic_results:
                    data = semantic_results
                    is_semantic_fallback = True
                    print(f"🧠 Recherche sémantique Zvec a trouvé {len(data)} stations similaires.")
                    return self._format_semantic_answer(question, data)

            # Répondre clairement qu'aucune donnée n'existe dans la base
            print(f"ℹ️ Aucune donnée trouvée dans la base hydrométrique.")
            return self._format_no_data_answer(question, annee=annee, date_fr=date_fr, stations=stations, gouvernorat=gouvernorat, station_nom_libre=station_nom_libre)

        return self._format_answer(question, data, sql)

    def _format_no_data_answer(self, question, annee=None, date_fr=None, stations=None, gouvernorat=None, station_nom_libre=None):
        """Formate une réponse claire et explicite indiquant l'absence de données dans la base."""
        elements = []
        if date_fr:
            elements.append(f"la date du **{date_fr}**")
        elif annee:
            elements.append(f"l'année **{annee}**")

        if station_nom_libre:
            elements.append(f"la station **{station_nom_libre.title()}**")
        elif stations:
            stations_info = self.rag.get_stations_info() if hasattr(self.rag, 'get_stations_info') else []
            stations_noms = []
            for code in stations:
                st = next((s for s in stations_info if str(s.get('code_station')) == str(code)), None)
                if st and st.get('nom'):
                    stations_noms.append(st['nom'])
            if stations_noms:
                elements.append(f"la station **{', '.join(set(stations_noms))}**")
        elif gouvernorat:
            elements.append(f"le gouvernorat de **{gouvernorat}**")

        if elements:
            contexte = " pour " + " et ".join(elements)
        else:
            contexte = " pour les critères demandés"

        return (
            f"⚠️ **Aucune donnée trouvée dans la base hydrométrique{contexte}.**\n\n"
            f"ℹ️ **Précisions :**\n"
            f"• Les mesures enregistrées dans la base couvrent principalement les années hydrologiques récentes (**2019 à 2024**).\n"
            f"• Si vous recherchez un événement précis, vérifiez la date ou essayez une période couverte par le réseau de mesure.\n"
            f"• Si de nouvelles données viennent d'être importées dans la base, demandez le recalcul : *« Recalcule les statistiques pour {annee or 2024} »*."
        )

    def _format_semantic_answer(self, question, data):
        """Formate la réponse sémantique en utilisant le LLM"""
        if not data:
            return "Aucune station similaire trouvée."
            
        if self.use_llm and self.llm:
            try:
                context = "\n".join([
                    f"- Station: {r['nom']} (Gouvernorat: {r['gouvernorat']}, Cours d'eau: {r['cours_eau']}) [similarité: {r['score']:.4f}]"
                    for r in data
                ])
                prompt = f"""
Tu es un expert hydromologue. L'utilisateur a posé une question descriptive ou floue pour chercher des stations.
Nous avons fait une recherche sémantique dans la base de données et trouvé les stations les plus pertinentes ci-dessous.

Question de l'utilisateur : "{question}"

Stations trouvées :
{context}

Rédige une réponse claire et professionnelle présentant ces résultats à l'utilisateur de manière naturelle.
Ne mentionne pas le terme "score de similarité" directement ou de manière trop technique, mais présente-les par ordre de pertinence.
"""
                response = self.llm.generate(prompt, max_tokens=300)
                if response:
                    return response
            except Exception as e:
                print(f"⚠️ Erreur enrichissement sémantique LLM: {e}")
                
        # Formatage basique de secours
        lines = [f"📊 Stations les plus similaires trouvées pour votre recherche :"]
        for i, r in enumerate(data, 1):
            lines.append(f"  {i}. **{r['nom']}** ({r['gouvernorat']}) sur le cours d'eau {r['cours_eau']} (score: {r['score']:.3f})")
        return "\n".join(lines)

    def _format_answer(self, question, data, sql):
        """Formate la réponse de manière naturelle et lisible"""
        if not data:
            return "⚠️ Aucune donnée trouvée dans la base hydrométrique pour votre requête."
        
        first = data[0] if isinstance(data, list) and len(data) > 0 else {}
        q_lower = question.lower().strip()

        # 0. Format DÉBITS JOURNALIERS (date spécifique)
        if 'jour' in first:
            lines = [f"🌊 **Débits journaliers enregistrés ({len(data)} résultat(s)) :**\n"]
            for i, row in enumerate(data, 1):
                st = row.get('station') or row.get('nom') or 'Station'
                gouv = row.get('gouvernorat', '')
                gouv_str = f" ({gouv})" if gouv else ""
                jour_val = row.get('jour')
                try:
                    import pandas as _pd
                    jour_str = _pd.to_datetime(jour_val).strftime('%d/%m/%Y')
                except Exception:
                    jour_str = str(jour_val)

                dmoy = row.get('debit_moyen')
                dmax = row.get('debit_max')
                dmoy_str = f"débit moyen : **{float(dmoy):.2f} m³/s**" if dmoy is not None and str(dmoy).lower() != 'nan' else ""
                dmax_str = f"débit max : **{float(dmax):.2f} m³/s**" if dmax is not None and str(dmax).lower() != 'nan' else ""
                debit_info = " | ".join(filter(None, [dmoy_str, dmax_str]))
                lines.append(f"  {i}. **{st}**{gouv_str} le {jour_str} : {debit_info}")
            return "\n".join(lines)

        # 1. Format CRUES (débits de pointe, crues historiques)
        if any(k in first for k in ['debit_max_m3s', 'date_debut']):
            lines = [f"🌊 **Principales crues enregistrées ({len(data)} résultat(s)) :**\n"]
            for i, row in enumerate(data, 1):
                st = row.get('station') or row.get('nom') or 'Station'
                gouv = row.get('gouvernorat', '')
                gouv_str = f" ({gouv})" if gouv else ""
                annee = row.get('annee')
                annee_str = f" — Année {annee}" if annee else ""
                debit = row.get('debit_max_m3s')
                debit_str = f"**{float(debit):.2f} m³/s**" if debit is not None else "N/A"
                
                date_val = row.get('date_debut')
                if date_val is not None:
                    try:
                        date_str = pd.to_datetime(date_val).strftime('%d/%m/%Y à %H:%M')
                    except Exception:
                        date_str = str(date_val)
                    lines.append(f"  {i}. **{st}**{gouv_str}{annee_str} : débit de pointe de {debit_str} le {date_str}")
                else:
                    lines.append(f"  {i}. **{st}**{gouv_str}{annee_str} : débit de pointe de {debit_str}")
            return "\n".join(lines)

        # 2. Format CLASSEMENT GOUVERNORATS PAR DÉBIT MAXIMAL
        if 'max_debit' in first and 'gouvernorat' in first:
            top = data[0]
            top_gouv = top.get('gouvernorat', '')
            top_val = float(top.get('max_debit', 0))
            top_st = top.get('station_max', '')
            top_an = top.get('annee_max', '')
            an_txt = f" (année {top_an})" if top_an else ""
            st_txt = f" enregistré à la station **{top_st}**{an_txt}" if top_st else ""

            lines = [
                f"🌊 Le gouvernorat ayant le plus grand débit est **{top_gouv}**, avec un débit maximal journalier de **{top_val:.2f} m³/s**{st_txt}.\n",
                "📊 **Classement des gouvernorats par débit maximal enregistré :**\n"
            ]
            for i, row in enumerate(data[:10], 1):
                g = row.get('gouvernorat', '')
                v = float(row.get('max_debit', 0))
                s = row.get('station_max', '')
                a = row.get('annee_max', '')
                a_str = f" [{a}]" if a else ""
                s_str = f" — Station {s}{a_str}" if s else ""
                lines.append(f"  {i}. **{g}** : **{v:.2f} m³/s**{s_str}")
            return "\n".join(lines)

        # 3. Format CLASSEMENT GOUVERNORATS PAR VOLUME MAXIMAL
        if 'max_volume' in first and 'gouvernorat' in first:
            top = data[0]
            top_gouv = top.get('gouvernorat', '')
            top_val = float(top.get('max_volume', 0))
            top_st = top.get('station_max', '')
            top_an = top.get('annee_max', '')
            an_txt = f" (année {top_an})" if top_an else ""
            st_txt = f" mesuré à la station **{top_st}**{an_txt}" if top_st else ""

            lines = [
                f"💧 Le gouvernorat ayant le plus grand volume annuel d'eau écoulé est **{top_gouv}**, avec un volume maximal de **{top_val:,.2f} Hm³**{st_txt}.\n",
                "📊 **Classement des gouvernorats par volume annuel maximal :**\n"
            ]
            for i, row in enumerate(data[:10], 1):
                g = row.get('gouvernorat', '')
                v = float(row.get('max_volume', 0))
                s = row.get('station_max', '')
                a = row.get('annee_max', '')
                a_str = f" [{a}]" if a else ""
                s_str = f" — Station {s}{a_str}" if s else ""
                lines.append(f"  {i}. **{g}** : **{v:,.2f} Hm³**{s_str}")
            return "\n".join(lines)

        # 4. Format NOMBRE DE STATIONS PAR GOUVERNORAT
        if 'nb_stations' in first and 'gouvernorat' in first:
            max_nb = data[0].get('nb_stations', 0)
            top_gouvs = [r.get('gouvernorat', '') for r in data if r.get('nb_stations') == max_nb]
            if len(top_gouvs) > 1:
                lead = f"Les gouvernorats qui comptent le plus grand nombre de stations sont **{'** et **'.join(top_gouvs)}** avec **{max_nb} stations** chacun"
            else:
                lead = f"Le gouvernorat qui compte le plus grand nombre de stations est **{top_gouvs[0]}** avec **{max_nb} stations**"

            lines = [
                f"📍 {lead}.\n",
                "📊 **Répartition des stations par gouvernorat :**\n"
            ]
            for i, r in enumerate(data, 1):
                g = r.get('gouvernorat', '')
                nb = r.get('nb_stations', 0)
                lines.append(f"  {i}. **{g}** : {nb} station{'s' if nb > 1 else ''}")
            return "\n".join(lines)

        # 5. Format TOTAL DES STATIONS
        if 'total_stations' in first and len(first) == 1:
            tot = data[0].get('total_stations', 0)
            return f"📍 Le réseau hydrométrique national de la DGRE compte actuellement un total de **{tot} stations** réparties sur toute la Tunisie."

        # 6. Format SUPERLATIF DÉBIT PAR STATION
        if any(w in q_lower for w in ['plus grand', 'max', 'maximum', 'record', 'plus fort', 'plus eleve', 'plus élevé']) and 'debit_max_jour' in first and not ('gouvernorat' in q_lower or 'gouv' in q_lower):
            top = data[0]
            st = top.get('station') or top.get('nom') or 'Station'
            gouv = top.get('gouvernorat', '')
            gouv_str = f" (gouvernorat de **{gouv}**)" if gouv else ""
            an = top.get('annee')
            an_str = f" en {an}" if an else ""
            dmax = float(top.get('debit_max_jour', 0))

            lines = [
                f"🌊 La station enregistrant le plus grand débit est **{st}**{gouv_str}, avec un débit maximal journalier de **{dmax:.2f} m³/s**{an_str}.\n",
                f"📊 **Top {len(data)} des débits journaliers maximaux enregistrés :**\n"
            ]
            for i, row in enumerate(data[:5], 1):
                s = row.get('station') or row.get('nom') or 'Station'
                g = row.get('gouvernorat', '')
                g_s = f" ({g})" if g else ""
                a = row.get('annee')
                a_s = f" [{a}]" if a else ""
                val = float(row.get('debit_max_jour', 0))
                lines.append(f"  {i}. **{s}**{g_s}{a_s} — Débit max : **{val:.2f} m³/s**")
            return "\n".join(lines)

        # 7. Format SUPERLATIF VOLUME PAR STATION
        if any(w in q_lower for w in ['plus grand', 'max', 'maximum', 'record', 'plus fort', 'plus eleve', 'plus élevé']) and 'volume_total_hm3' in first and not ('gouvernorat' in q_lower or 'gouv' in q_lower):
            top = data[0]
            st = top.get('station') or top.get('nom') or 'Station'
            gouv = top.get('gouvernorat', '')
            gouv_str = f" (gouvernorat de **{gouv}**)" if gouv else ""
            an = top.get('annee')
            an_str = f" en {an}" if an else ""
            vmax = float(top.get('volume_total_hm3', 0))

            lines = [
                f"💧 La station enregistrant le plus grand volume d'eau est **{st}**{gouv_str}, avec un volume total annuel de **{vmax:,.2f} Hm³**{an_str}.\n",
                f"📊 **Top {len(data)} des volumes annuels enregistrés :**\n"
            ]
            for i, row in enumerate(data[:5], 1):
                s = row.get('station') or row.get('nom') or 'Station'
                g = row.get('gouvernorat', '')
                g_s = f" ({g})" if g else ""
                a = row.get('annee')
                a_s = f" [{a}]" if a else ""
                val = float(row.get('volume_total_hm3', 0))
                lines.append(f"  {i}. **{s}**{g_s}{a_s} — Volume : **{val:,.2f} Hm³**")
            return "\n".join(lines)

        # 8. Format STATIONS HYDROMÉTRIQUES D'UN GOUVERNORAT SPÉCIFIQUE
        if ('station' in first or 'nom' in first) and 'cours_eau' in first:
            annee_e, gouv_e, _, _, _, _ = self.rag._extraire_entites(question) if hasattr(self, 'rag') else (None, None, None, None, None, None)
            if gouv_e:
                lines = [f"📍 **Stations hydrométriques du gouvernorat de {gouv_e} ({len(data)} résultat(s)) :**\n"]
                for i, row in enumerate(data, 1):
                    st = row.get('station') or row.get('nom')
                    cours = row.get('cours_eau')
                    cours_str = f" — Cours d'eau : {cours}" if cours else ""
                    lines.append(f"  {i}. **{st}**{cours_str}")
                return "\n".join(lines)

        # 9. Format DÉBITS ET VOLUMES GÉNÉRAUX
        if any(k in first for k in ['volume_total_hm3', 'debit_max_jour', 'debit_moyen']):
            lines = [f"💧 **Données de débit et volume ({len(data)} résultat(s)) :**\n"]
            for i, row in enumerate(data, 1):
                st = row.get('station') or row.get('nom') or 'Station'
                gouv = row.get('gouvernorat', '')
                gouv_str = f" ({gouv})" if gouv else ""
                annee = row.get('annee')
                annee_str = f" [Année {annee}]" if annee else ""
                
                details = []
                if 'debit_max_jour' in row and row['debit_max_jour'] is not None and str(row['debit_max_jour']).lower() != 'nan':
                    try:
                        details.append(f"Débit max : **{float(row['debit_max_jour']):.2f} m³/s**")
                    except:
                        pass
                if 'debit_moyen' in row and row['debit_moyen'] is not None and str(row['debit_moyen']).lower() != 'nan':
                    try:
                        details.append(f"Débit moyen : **{float(row['debit_moyen']):.2f} m³/s**")
                    except:
                        pass
                if 'volume_total_hm3' in row and row['volume_total_hm3'] is not None and str(row['volume_total_hm3']).lower() != 'nan':
                    try:
                        details.append(f"Volume : **{float(row['volume_total_hm3']):.2f} Hm³**")
                    except:
                        pass
                detail_text = " — " + " | ".join(details) if details else ""
                lines.append(f"  {i}. **{st}**{gouv_str}{annee_str}{detail_text}")
            return "\n".join(lines)

        # 10. Format STATIONS HYDROMÉTRIQUES (général)
        if 'station' in first or ('nom' in first and 'gouvernorat' in first):
            lines = [f"📍 **Stations hydrométriques ({len(data)} résultat(s)) :**\n"]
            for i, row in enumerate(data, 1):
                st = row.get('station') or row.get('nom')
                gouv = row.get('gouvernorat')
                cours = row.get('cours_eau')
                parts = [f"**{st}**"]
                if gouv:
                    parts.append(f"Gouvernorat : {gouv}")
                if cours:
                    parts.append(f"Cours d'eau : {cours}")
                lines.append(f"  {i}. " + " — ".join(parts))
            return "\n".join(lines)

        # 11. Format COMPTAGES / STATISTIQUES GLOBALES
        if any(k in first for k in ['total_stations', 'nb_stations', 'nb_gouvernorats', 'nb_cours_eau']):
            lines = ["📊 **Statistiques :**\n"]
            for row in data:
                for k, v in row.items():
                    label = k.replace('_', ' ').capitalize()
                    lines.append(f"  • **{label}** : {v}")
            return "\n".join(lines)

        # 12. Format COURS D'EAU
        if 'cours_eau' in first and len(first) == 1:
            lines = [f"🌊 **Cours d'eau répertoriés ({len(data)} résultat(s)) :**\n"]
            for i, row in enumerate(data, 1):
                lines.append(f"  {i}. {row.get('cours_eau')}")
            return "\n".join(lines)

        # 13. Format générique propre (exclut coordonnées brutes et IDs)
        lines = [f"📊 **{len(data)} résultat(s) :**\n"]
        for i, row in enumerate(data[:15], 1):
            clean_parts = []
            for k, v in row.items():
                if k in ['id', 'code_station', 'coordonnee_x', 'coordonnee_y', 'x_utm', 'y_utm']:
                    continue
                if v is not None and str(v).lower() != 'nan':
                    if isinstance(v, float):
                        clean_parts.append(f"{k}: {v:.2f}")
                    else:
                        clean_parts.append(f"{k}: {v}")
            if clean_parts:
                lines.append(f"  {i}. " + " | ".join(clean_parts))
        return "\n".join(lines)


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