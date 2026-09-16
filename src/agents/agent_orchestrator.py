"""
src/agents/agent_orchestrator.py
Agent Orchestrateur - Coordonne tous les agents métier

NOUVEAU : la detection d'intention passe maintenant en priorite par le
modele fine-tune (via AgentLLM.chat avec tools=), qui choisit lui-meme
l'outil + ses arguments, ou repond en texte/code selon la nature de la
demande. La detection par mots-cles (detect_intent) est conservee comme
repli si le LLM est indisponible ou si sa reponse n'est pas exploitable -
jamais de plantage total, juste une degradation de la qualite de reponse.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import json
import re
import ast


# ----------------------------------------------------------------------
# Meme liste d'outils que celle utilisee pour generer le dataset de
# fine-tuning (src/agents/../../generer_dataset_finetuning.py) - doit
# rester synchronisee si vous ajoutez/modifiez un outil.
# ----------------------------------------------------------------------
OUTILS_DISPONIBLES = [
    {
        "type": "function",
        "function": {
            "name": "generer_annuaire",
            "description": "Genere l'annuaire hydrometrique PDF complet pour une annee donnee.",
            "parameters": {
                "type": "object",
                "properties": {"annee": {"type": "integer"}},
                "required": ["annee"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generer_pdf_periode",
            "description": "Genere un PDF partiel de l'annuaire pour une periode de quelques mois.",
            "parameters": {
                "type": "object",
                "properties": {
                    "annee": {"type": "integer"},
                    "mois_debut": {"type": "integer"},
                    "mois_fin": {"type": "integer"}
                },
                "required": ["annee", "mois_debut", "mois_fin"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generer_carte_hydrometrique",
            "description": "Genere une carte du reseau hydrometrique pour un gouvernorat ou la Tunisie.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone": {"type": "string"},
                    "nb_mois_precedents": {"type": "integer"}
                },
                "required": ["zone"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recalculer_statistiques",
            "description": "Recalcule les debits journaliers, statistiques annuelles et crues pour une annee.",
            "parameters": {
                "type": "object",
                "properties": {"annee": {"type": "integer"}},
                "required": ["annee"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "repondre_question_donnees",
            "description": "Repond a une question factuelle sur les donnees hydrometriques.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"]
            }
        }
    },
]

SYSTEME_LLM = (
    "Tu es l'assistant agentic de la DGRE pour l'annuaire hydrometrique de la Tunisie. "
    "Tu reponds aux questions sur les donnees hydrometriques (debits, crues, statistiques, "
    "stations) et tu peux declencher des actions via les outils disponibles (generation de "
    "PDF, de cartes, recalcul de statistiques). Reponds toujours en francais.\n\n"
    "Pour un GRAPHIQUE LIBRE ou PERSONNALISE (non couvert par l'outil "
    "generer_carte_hydrometrique - par exemple comparer deux variables, un type de "
    "graphique specifique, une agregation particuliere), ne passe PAS par un appel "
    "d'outil : reponds directement avec le code Python COMPLET et EXECUTABLE "
    "(matplotlib/pandas/numpy uniquement), sans texte explicatif avant ou apres, en "
    "utilisant le DataFrame pandas deja charge dans la variable `df`. Termine toujours "
    "par plt.savefig('output_graphique.png', dpi=200, bbox_inches='tight')."
)


def extraire_appel_outil(reponse_modele):
    """Extrait un appel d'outil de la reponse du modele, AVEC ou SANS les
    balises <tool_call> (notre modele fine-tune produit le JSON brut,
    sans balises - voir la conversation d'entrainement). Retourne None
    si la reponse n'est pas un appel d'outil."""
    if not reponse_modele:
        return None

    match = re.search(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', reponse_modele, re.DOTALL)
    if match:
        bloc = match.group(1)
    else:
        match = re.search(r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{.*?\}\s*\}', reponse_modele, re.DOTALL)
        if not match:
            return None
        bloc = match.group(0)

    try:
        res = json.loads(bloc)
        if isinstance(res, dict) and isinstance(res.get("arguments"), str):
            try:
                res["arguments"] = json.loads(res["arguments"])
            except Exception:
                pass
        return res
    except json.JSONDecodeError:
        return None


def est_code_python(reponse_modele):
    """Heuristique simple : la reponse ressemble a un bloc de code Python
    (graphique libre) plutot qu'a un appel d'outil ou une reponse texte."""
    if not reponse_modele:
        return False
    debut = reponse_modele.strip()[:200]
    return ("import matplotlib" in debut or "import pandas" in debut
            or debut.startswith("plt.") or debut.startswith("fig"))


class AgentOrchestrator:
    """
    Orchestrateur principal - Gère le pipeline complet :
    1. Analyse de l'intention utilisateur (LLM fine-tune en priorite,
       mots-cles en repli)
    2. Coordination des agents métier
    3. Génération de l'annuaire / cartes / recalculs
    4. Réponse aux questions
    5. Exécution sandboxee de code pour les graphiques libres
    """
    
    def __init__(self, db_config=None):
        self.db_config = db_config or {
            'host': 'localhost',
            'port': 5432,
            'database': 'hydrometry',
            'user': 'postgres',
            'password': 'postgres'
        }
        self.agents = {}
        self._llm = None  # instancie a la demande (voir _get_llm)
        print("✅ Agent Orchestrateur initialisé")

    def _get_agent(self, name):
        """Charge un agent à la demande et le réutilise ensuite (au lieu
        d'ouvrir une nouvelle connexion PostgreSQL à chaque appel)."""
        return self.get_agent(name)

    def get_agent(self, name):
        if name in self.agents:
            return self.agents[name]

        if name == 'calcul':
            from agents.agent_calcul import AgentCalcul
            agent = AgentCalcul(self.db_config)
        elif name == 'edition':
            from agents.agent_edition import AgentEdition
            agent = AgentEdition(self.db_config)
        elif name == 'rag':
            from agents.agent_rag import AgentRAGOrchestrator
            agent = AgentRAGOrchestrator(self.db_config)
        else:
            raise ValueError(f"Agent inconnu : {name}")

        self.agents[name] = agent
        print(f"✅ Agent{name.capitalize()} chargé")
        return agent

    def _get_llm(self):
        """Instancie l'agent LLM fine-tune a la demande (lit LLM_MODEL/
        LLM_HOST depuis .env - voir maj_llm_host.py pour la mise a jour
        de l'URL Colab a chaque session)."""
        if self._llm is None:
            from agents.agent_llm import AgentLLM
            self._llm = AgentLLM()
        return self._llm

    def close(self):
        """Ferme tous les agents"""
        for name, agent in self.agents.items():
            if hasattr(agent, 'close'):
                try:
                    agent.close()
                    print(f"🔒 {name} fermé")
                except:
                    pass
        print("🔒 Tous les agents fermés")
    
    # ============================================================
    # 1. ANALYSE DE L'INTENTION
    # ============================================================

    def detect_intent_llm(self, user_input):
        """
        Utilise le modele fine-tune pour determiner l'intention : appel
        d'outil structure, code Python (graphique libre), ou reponse
        texte directe. Retourne None si le LLM est indisponible ou si sa
        reponse n'est pas exploitable (l'appelant doit alors se rabattre
        sur detect_intent, la detection par mots-cles).
        """
        llm = self._get_llm()
        if not llm.available or not llm.model_loaded:
            return None

        messages = [
            {"role": "system", "content": SYSTEME_LLM},
            {"role": "user", "content": user_input},
        ]
        reponse = llm.chat(messages, temperature=0.1, max_tokens=400, tools=OUTILS_DISPONIBLES)
        if not reponse:
            return None

        appel = extraire_appel_outil(reponse)
        if appel and appel.get("name"):
            return {
                'type': 'outil',
                'subtype': appel["name"],
                'params': appel.get("arguments", {}),
                'message': f"Outil detecte : {appel['name']}"
            }

        if est_code_python(reponse):
            return {
                'type': 'code',
                'subtype': 'graphique_personnalise',
                'params': {'code': reponse},
                'message': "Generation d'un graphique personnalise"
            }

        # Reponse texte directe (Q&A simple deja generee par le LLM)
        return {
            'type': 'texte_direct',
            'subtype': 'llm_direct',
            'params': {'reponse': reponse},
            'message': reponse
        }

    def _extraire_entites_stations(self, user_input):
        """
        Extrait les entités de stations hydrométriques mentionnées dans le texte
        en préservant l'ordre d'apparition (ex: Sidi Salem puis Medjez El Bab).
        """
        txt = user_input.lower()
        trouvees = []
        codes_vus = set()

        aliases = {
            'sidi salem': {'nom': 'Sidi Salem', 'codes': ['1485400180', '1485900129'], 'role': 'Amont'},
            'bou salem': {'nom': 'Bou Salem', 'codes': ['1485400180'], 'role': 'Amont'},
            'medjez el bab': {'nom': 'Medjez El Bab', 'codes': ['1485900139', '1485900140'], 'role': 'Aval'},
            'medjez': {'nom': 'Medjez El Bab', 'codes': ['1485900139', '1485900140'], 'role': 'Aval'},
            'mejez el bab': {'nom': 'Medjez El Bab', 'codes': ['1485900139', '1485900140'], 'role': 'Aval'},
            'mejez': {'nom': 'Medjez El Bab', 'codes': ['1485900139', '1485900140'], 'role': 'Aval'},
            'pont el mouradi': {'nom': 'Medjez (Pont el Mouradi)', 'codes': ['1485900140'], 'role': 'Aval'},
            'mellegue k13': {'nom': 'Mellègue K13', 'codes': ['1485101210']},
            'mellegue': {'nom': 'Mellègue', 'codes': ['1485101210', '1485101211']},
            'k13': {'nom': 'Mellègue K13', 'codes': ['1485101210']},
            'jendouba': {'nom': 'Jendouba', 'codes': ['1485400160']},
            'ghardimaou': {'nom': 'Ghardimaou', 'codes': ['1485400110', '1485400111']},
            'slouguia': {'nom': 'Slouguia', 'codes': ['1485900130']},
            'jedeida': {'nom': 'Jedeida', 'codes': ['1485900170']},
            'chemtou': {'nom': 'Chemtou', 'codes': ['1485400130']},
            'siliana': {'nom': 'Siliana', 'codes': ['1485501610', '1485501635']},
            'khenguette zazia': {'nom': 'Khenguette Zazia', 'codes': ['1486300140']},
            'khenguette': {'nom': 'Khenguette Zazia', 'codes': ['1486300140']},
            'el herri': {'nom': 'El Herri', 'codes': ['1485900141']},
            'oued beja': {'nom': 'Oued Béja', 'codes': ['1485602240']},
            'tine': {'nom': 'Tine', 'codes': ['1483602050', '1483602040']},
            'joumine': {'nom': 'Joumine', 'codes': ['1483600130']},
            'mateur': {'nom': 'Mateur Joumine', 'codes': ['1483600130']},
            'la madelaine': {'nom': 'La Madelaine', 'codes': ['1484100180']},
            'ain saboun': {'nom': 'Ain Saboun', 'codes': ['1486200110']},
        }

        matches_avec_pos = []
        for alias, info in aliases.items():
            pattern = r'\b' + re.escape(alias) + r'\b'
            m = re.search(pattern, txt)
            if m:
                matches_avec_pos.append((m.start(), len(alias), info))

        matches_avec_pos.sort(key=lambda x: x[0])

        for _, _, info in matches_avec_pos:
            if not any(c in codes_vus for c in info['codes']):
                trouvees.append(info)
                codes_vus.update(info['codes'])

        return trouvees

    def detect_intent(self, user_input):
        """
        Détection par mots-clés (repli si le LLM est indisponible).
        Retourne : {
            'type': 'generation' | 'carte' | 'recalcul' | 'graphique_comparaison' | 'question' | 'help',
            'subtype': 'pdf' | 'stats' | 'station' | 'crues' | ...,
            'params': {...}
        }
        """
        input_lower = user_input.lower().strip()

        # === INTENTION DE CARTE (avant "generation" : "genere-moi LA CARTE
        # de Beja" contient "genere" mais ne doit pas declencher un PDF) ===
        carte_keywords = ['carte', 'cartograph']
        if any(kw in input_lower for kw in carte_keywords):
            zone = 'Tunisie'
            match = re.search(
                r"\b(?:de|du|d')\s+(?:l'|la\s+|le\s+)?([a-zàâäéèêëïîôöùûüçñ]+(?:[\s\-][a-zàâäéèêëïîôöùûüçñ]+)*)",
                input_lower,
            )
            if match:
                candidat = re.split(r'\s+(?:pour|depuis|sur|avec|entre)\b', match.group(1).strip())[0].strip()
                if candidat:
                    zone = candidat
            return {
                'type': 'carte',
                'subtype': 'hydrometrique',
                'params': {'zone': zone},
                'message': f"Génération de la carte pour {zone}"
            }

        # === INTENTION DE RECALCUL ===
        recalcul_keywords = ['recalcul', 'recalculer', 'recalcule']
        if any(kw in input_lower for kw in recalcul_keywords):
            year_match = re.search(r'(20\d{2})', input_lower)
            annee = int(year_match.group(1)) if year_match else 2019
            return {
                'type': 'recalcul',
                'subtype': 'statistiques',
                'params': {'annee': annee},
                'message': f"Recalcul des statistiques pour {annee}"
            }

        # === INTENTION DE LISTE / CONSULTATION DES ANNUAIRES DÉJÀ GÉNÉRÉS ===
        mots_consultation = [
            'déjà généré', 'deja genere', 'déjà générés', 'deja generes',
            'disponible', 'disponibles', 'existant', 'existants',
            'liste', 'où trouver', 'ou trouver', 'où sont', 'ou sont', 'ou je trouve', 'où je trouve',
            'consulter', 'tous les annuaires', 'voir les annuaires', 'archives', 'catalogue'
        ]
        demande_annuaire = any(w in input_lower for w in ['annuaire', 'annuaires', 'pdf'])
        action_generer = any(w in input_lower for w in ['génère', 'genere', 'générer', 'generer', 'crée', 'cree', 'créer', 'creer', 'produire', 'fabrique'])
        if demande_annuaire and any(m in input_lower for m in mots_consultation) and not action_generer:
            return {
                'type': 'liste_annuaires',
                'subtype': 'catalogue_pdf',
                'params': {},
                'message': "Consultation des annuaires hydrométriques déjà générés"
            }

        # === INTENTION DE GÉNÉRATION PDF ===
        generation_keywords = ['génère', 'genere', 'générer', 'generer', 'crée', 'cree', 'creer', 'annuaire', 'pdf']
        if any(kw in input_lower for kw in generation_keywords):
            year_match = re.search(r'(20\d{2})', input_lower)
            annee = int(year_match.group(1)) if year_match else 2019
            
            return {
                'type': 'generation',
                'subtype': 'pdf',
                'params': {'annee': annee},
                'message': f"Génération de l'annuaire pour {annee}-{annee+1}"
            }

        # === INTENTION DE GRAPHIQUE OU COMPARAISON HYDROMÉTRIQUE ===
        # (Prioritaire sur les simples questions textuelles)
        graphique_keywords = [
            'trace', 'tracer', 'trace-moi', 'trace moi', 'tracé', 'dessine', 'dessiner',
            'graphique', 'graphe', 'plot', 'courbe', 'hydrogramme', 'histogramme',
            'compare', 'comparer', 'comparaison', 'versus', 'vs'
        ]
        if any(kw in input_lower for kw in graphique_keywords):
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', input_lower)
            annee = int(year_match.group(1)) if year_match else 2024
            entites = self._extraire_entites_stations(user_input)
            
            return {
                'type': 'graphique_comparaison',
                'subtype': 'comparaison_stations' if len(entites) >= 2 else ('hydrogramme_station' if len(entites) == 1 else 'graphique_general'),
                'params': {
                    'annee': annee,
                    'entites': entites,
                    'raw_input': user_input
                },
                'message': f"Génération du graphique / comparaison hydrométrique pour {annee}"
            }
        
        # === INTENTION DE DÉFINITION OU EXPLICATION GÉNÉRALE ===
        definition_triggers = [
            'definition', 'définition', "qu'est-ce que l'hydrometrie", "qu'est-ce que l'hydrométrie",
            "qu'est ce que l'hydrometrie", "qu'est ce que l'hydrométrie", "c'est quoi l'hydrometrie",
            "c'est quoi l'hydrométrie", "c'est quoi la dgre", "role de la dgre", "rôle de la dgre",
            "mission de la dgre", "missions de la dgre"
        ]
        if any(trig in input_lower for trig in definition_triggers) or (
            any(w in input_lower for w in ['definition', 'définition'])
            and any(h in input_lower for h in ['hydrometrie', 'hydrométrie', 'hydrometrique', 'hydrométrique', 'hdrometrie', 'hdrométrie', 'dgre'])
        ):
            return {
                'type': 'definition',
                'subtype': 'hydrometrie',
                'params': {},
                'message': "Définition de l'hydrométrie et missions de la DGRE"
            }

        # === INTENTION DE QUESTION FACTUELLE ===
        question_keywords = [
            'quel', 'quelle', 'quels', 'quelles', 'combien', 'comment', 'pourquoi', 'est-ce que',
            'donne', 'donne-moi', 'donne moi', 'montre', 'montre-moi', 'affiche', 'liste', 'trouve',
            'y a-t-il', 'y a t il', 'existe', 'existent', 'historique', 'donnée', 'données', 'donnee', 'donnees',
            'mesure', 'mesures'
        ]
        entites_st = self._extraire_entites_stations(user_input)
        date_match = re.search(r'\b\d{1,2}[/\-]\d{1,2}[/\-]\d{4}\b', input_lower)
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', input_lower)

        if (
            any(kw in input_lower for kw in question_keywords)
            or '?' in input_lower
            or any(kw in input_lower for kw in ['crue', 'crues', 'crus', 'inondation', 'débit', 'debit', 'volume'])
            or date_match
            or (year_match and (entites_st or 'station' in input_lower))
        ):
            if any(kw in input_lower for kw in ['crue', 'crues', 'crus', 'inondation', 'inondations', 'pic']):
                return {
                    'type': 'question',
                    'subtype': 'crues',
                    'params': {},
                    'message': "Recherche des informations sur les crues"
                }

            if 'max' in input_lower or 'maximum' in input_lower or 'plus grand' in input_lower:
                if 'débit' in input_lower or 'debit' in input_lower:
                    return {
                        'type': 'question',
                        'subtype': 'max_debit',
                        'params': {},
                        'message': "Recherche du débit maximum"
                    }
            
            if 'moyen' in input_lower or 'moyenne' in input_lower:
                if 'débit' in input_lower or 'debit' in input_lower:
                    return {
                        'type': 'question',
                        'subtype': 'avg_debit',
                        'params': {},
                        'message': "Calcul du débit moyen"
                    }
            
            if 'volume' in input_lower or 'hm3' in input_lower:
                return {
                    'type': 'question',
                    'subtype': 'total_volume',
                    'params': {},
                    'message': "Recherche du volume total"
                }

            if 'débit' in input_lower or 'debit' in input_lower:
                return {
                    'type': 'question',
                    'subtype': 'debit',
                    'params': {},
                    'message': "Recherche de débit"
                }
            
            if 'station' in input_lower or entites_st:
                station_name = entites_st[0]['nom'] if entites_st else None
                if not station_name and 'station' in input_lower:
                    station_match = re.search(r'station\s+([a-zA-Z\s\-]+)', input_lower)
                    station_name = station_match.group(1).strip() if station_match else None
                return {
                    'type': 'question',
                    'subtype': 'station',
                    'params': {'station_name': station_name},
                    'message': f"Recherche de la station {station_name or 'spécifiée'}"
                }
            
            if date_match or year_match:
                return {
                    'type': 'question',
                    'subtype': 'donnees_temporelles',
                    'params': {},
                    'message': "Recherche de données temporelles"
                }
            
            return {
                'type': 'question',
                'subtype': 'general',
                'params': {},
                'message': "Recherche d'informations générales"
            }
        
        # === INTENTION D'AIDE ===
        if any(kw in input_lower for kw in ['aide', 'help', 'bonjour', 'salut']):
            return {
                'type': 'help',
                'subtype': 'welcome',
                'params': {},
                'message': "Assistance hydrométrique"
            }
        
        return {
            'type': 'question',
            'subtype': 'general',
            'params': {},
            'message': "Recherche d'informations"
        }
    
    # ============================================================
    # 2. EXÉCUTION DES TÂCHES
    # ============================================================
    
    def execute(self, user_input):
        """
        Point d'entrée principal - Exécute l'intention détectée.
        1. Détecte d'abord les intentions visuelles et graphiques prioritaires :
           - Graphiques & comparaisons hydrométriques (hydrogrammes, laminage, crues)
           - Cartes du réseau
           - Génération d'annuaires PDF
           - Recalculs statistiques
        2. Détecte les questions hydrométriques explicites (crues, débits, stations)
           pour une réponse déterministe immédiate sans latence.
        3. Tente le LLM fine-tune pour les requêtes complexes, actions et graphiques libres.
        4. Se rabat sur les mots-clés généraux si nécessaire.
        """
        print(f"\n🔍 Analyse de la requête: {user_input}")

        # 1. Vérification rapide des intentions prioritaires
        intent_rapide = self.detect_intent(user_input)

        if intent_rapide['type'] == 'graphique_comparaison':
            print(f"🎯 Intention graphique/comparaison directe : {intent_rapide['subtype']}")
            return self._handle_comparaison_graphique(user_input, intent_rapide['params'])

        if intent_rapide['type'] == 'carte':
            print(f"🎯 Intention carte directe : {intent_rapide['subtype']}")
            return self._handle_carte_hydrometrique(intent_rapide['params'])

        if intent_rapide['type'] == 'liste_annuaires':
            print(f"🎯 Intention consultation annuaires existants : {intent_rapide['subtype']}")
            return self._handle_liste_annuaires()

        if intent_rapide['type'] == 'generation':
            print(f"🎯 Intention génération PDF directe : {intent_rapide['subtype']}")
            return self._handle_generation(intent_rapide)

        if intent_rapide['type'] == 'recalcul':
            print(f"🎯 Intention recalcul directe : {intent_rapide['subtype']}")
            return self._handle_recalcul_statistiques(intent_rapide['params'])

        if intent_rapide['type'] == 'question' and intent_rapide.get('subtype') in (
            'crues', 'debit', 'max_debit', 'avg_debit', 'total_volume', 'station', 'donnees_temporelles'
        ):
            print(f"🎯 Intention hydrométrique directe : {intent_rapide['subtype']}")
            return self._handle_question(intent_rapide, user_input)

        if intent_rapide['type'] == 'definition':
            print(f"🎯 Intention définition directe : {intent_rapide['subtype']}")
            return self._handle_definition(user_input)

        if intent_rapide['type'] == 'help':
            return self._handle_help(intent_rapide)

        # 2. Utilisation du modèle LLM fine-tune pour intentions complexes, actions ou graphiques
        intent_llm = self.detect_intent_llm(user_input)
        if intent_llm:
            print(f"🎯 Intention (LLM): {intent_llm['type']} - {intent_llm['subtype']}")
            return self._executer_intention_llm(intent_llm, user_input=user_input)

        llm = self._get_llm()
        llm_error = getattr(llm, 'last_error', None)
        print(f"ℹ️ LLM indisponible ou reponse non exploitable (erreur: {llm_error}) - repli sur les mots-cles")
        intent = intent_rapide
        print(f"🎯 Intention (mots-cles): {intent['type']} - {intent['subtype']}")
        
        # Si le modèle a échoué pour cause de timeout GPU et qu'il n'y a pas d'entité/mot-clé hydrométrique précis
        if llm_error == 'timeout' and intent.get('subtype') == 'general':
            msg_gpu = (
                "⚠️ **Délai d'attente dépassé (Problème de GPU / LLM).**\n\n"
                "Le modèle d'intelligence artificielle a mis trop de temps à répondre pour analyser votre demande.\n\n"
                "💡 **Cause :** Les ressources du GPU local (NVIDIA GeForce MX450 - 2 Go) sont insuffisantes "
                "pour faire tourner le modèle de 7.6 milliards de paramètres.\n\n"
                "👉 **Recommandations :**\n"
                "• Posez une question plus ciblée avec des termes hydrométriques précis (ex: *« Quel gouvernorat a le plus grand débit ? »*, *« Informations sur les crues »*, *« Génère l'annuaire 2019 »*).\n"
                "• Ou connectez le modèle distant avec GPU dédié via Google Colab (`python maj_llm_host.py <url>`)."
            )
            return {
                'status': 'warning',
                'type': 'gpu_timeout',
                'subtype': 'llm_timeout',
                'message': msg_gpu,
                'answer': msg_gpu
            }

        if intent['type'] == 'question':
            return self._handle_question(intent, user_input)
        else:
            return self._handle_default()

    def _executer_intention_llm(self, intent_llm, user_input=None):
        """Route une intention detectee par le LLM fine-tune vers le bon gestionnaire."""
        if intent_llm['type'] == 'outil':
            nom_outil = intent_llm['subtype']
            params = intent_llm['params']

            if nom_outil in ('generer_annuaire', 'generer_pdf_periode'):
                # Garde-fou anti-hallucination : si l'utilisateur demande des données de crues/débits sans demander explicitement un PDF
                input_l = (user_input or '').lower()
                demande_pdf = any(kw in input_l for kw in ['pdf', 'annuaire', 'document', 'rapport', 'télécharge', 'telecharge', 'exporter', 'export'])
                demande_donnees = any(kw in input_l for kw in ['crue', 'crues', 'crus', 'inondation', 'débit', 'debit', 'volume', 'station'])
                if demande_donnees and not demande_pdf:
                    print("⚠️ Le LLM a proposé un outil PDF pour une question factuelle de données - redirection vers AgentRAG")
                    return self._handle_question({'subtype': 'general', 'params': {}}, user_input)

                if nom_outil == 'generer_annuaire':
                    return self._handle_generation({'params': {'annee': params.get('annee', 2019)}})
                else:
                    return self._handle_pdf_periode(params)

            elif nom_outil == 'generer_carte_hydrometrique':
                return self._handle_carte_hydrometrique(params)
            elif nom_outil == 'recalculer_statistiques':
                return self._handle_recalcul_statistiques(params)
            elif nom_outil == 'repondre_question_donnees':
                return self._handle_question({'subtype': 'general', 'params': {}}, params.get('question', user_input or ''))
            else:
                return {'status': 'error', 'type': 'outil_inconnu',
                        'message': f"❌ Outil '{nom_outil}' detecte par le LLM mais non implemente cote serveur."}

        elif intent_llm['type'] == 'code':
            return self._handle_graphique_personnalise(intent_llm['params']['code'])

        elif intent_llm['type'] == 'texte_direct':
            # Sécurité anti-hallucination : si la requête utilisateur concerne une action
            # ou des données de la base, on ne renvoie JAMAIS de texte inventé par le modèle,
            # on exécute l'agent métier avec les vraies données PostgreSQL / SIG.
            if user_input:
                repli = self.detect_intent(user_input)
                if repli['type'] in ('generation', 'carte', 'recalcul'):
                    print("⚠️ Le LLM a répondu en texte au lieu d'appeler l'action - redirection vers l'agent dédié pour éviter l'hallucination")
                    if repli['type'] == 'generation':
                        return self._handle_generation(repli)
                    elif repli['type'] == 'carte':
                        return self._handle_carte_hydrometrique(repli['params'])
                    elif repli['type'] == 'recalcul':
                        return self._handle_recalcul_statistiques(repli['params'])
                elif repli['type'] == 'question' and repli.get('subtype') != 'general':
                    print("⚠️ Le LLM a répondu en texte direct - routage vers AgentRAG (données réelles SQL) pour éviter l'hallucination")
                    return self._handle_question(repli, user_input)

            return {'status': 'success', 'type': 'question', 'subtype': 'llm_direct',
                    'message': intent_llm['params']['reponse'], 'answer': intent_llm['params']['reponse']}

    def _handle_liste_annuaires(self):
        """Liste les annuaires PDF déjà générés disponibles au téléchargement."""
        racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        pdf_dir = os.path.join(racine, "output", "pdf")
        fichiers = []
        if os.path.exists(pdf_dir):
            for f in sorted(os.listdir(pdf_dir)):
                if f.startswith("annuaire_hydrometrique_") and f.endswith(".pdf"):
                    match = re.search(r'annuaire_hydrometrique_(\d{4})\.pdf', f)
                    annee = int(match.group(1)) if match else None
                    chemin = os.path.join(pdf_dir, f)
                    taille_mo = os.path.getsize(chemin) / (1024 * 1024)
                    mtime = datetime.fromtimestamp(os.path.getmtime(chemin)).strftime("%d/%m/%Y à %H:%M")
                    fichiers.append((f, annee, round(taille_mo, 1), mtime, chemin))

        if not fichiers:
            msg = (
                "ℹ️ **Aucun annuaire PDF n'a encore été généré sur le serveur.**\n\n"
                "Pour générer le document officiel d'une année, demandez simplement :\n"
                "• *« Génère-moi l'annuaire 2019 »*\n"
                "• *« Crée l'annuaire 2024 »*"
            )
            return {'status': 'success', 'type': 'liste_annuaires', 'message': msg, 'answer': msg}

        fichiers.sort(key=lambda x: x[1] or 0, reverse=True)
        lignes = [
            f"📚 **{len(fichiers)} annuaire(s) hydrométrique(s) officiel(s) sont déjà générés et prêts au téléchargement :**\n"
        ]
        for i, (nom, an, taille, date, ch) in enumerate(fichiers, 1):
            cycle = f"{an}-{an+1}" if an else nom
            lignes.append(
                f"  {i}. **Annuaire Hydrométrique {cycle}** ({taille} Mo)\n"
                f"     • Fichier : `{nom}`\n"
                f"     • Date de génération : {date}\n"
            )
        lignes.append(
            "\n💡 *Vous pouvez télécharger ces documents via les boutons ci-dessous ou directement dans l'onglet **« Annuaires PDF »** du menu supérieur.*"
        )
        msg = "\n".join(lignes)
        return {
            'status': 'success',
            'type': 'liste_annuaires',
            'message': msg,
            'answer': msg,
            'pdf_path': fichiers[0][4],
            'pdf_list': [
                {'nom': f[0], 'annee': f[1], 'taille_mo': f[2], 'date': f[3], 'chemin': f[4]}
                for f in fichiers
            ],
        }

    def _handle_generation(self, intent):
        """Gère la génération de l'annuaire PDF"""
        annee = intent['params'].get('annee', 2019)

        try:
            print(f"📄 Génération de l'annuaire {annee}...")
            agent = self._get_agent('edition')
            agent.annee = annee  # l'agent est réutilisé ; on met à jour l'année ciblée

            pdf_path = agent.generer_pdf()
            return {
                'status': 'success',
                'type': 'generation',
                'message': f"✅ Annuaire {annee}-{annee+1} généré avec succès !",
                'pdf_path': pdf_path,
                'annee': annee
            }

        except Exception as e:
            return {
                'status': 'error',
                'type': 'generation',
                'message': f"❌ Erreur lors de la génération : {str(e)}"
            }

    def _handle_pdf_periode(self, params):
        """Genere un PDF partiel (quelques mois plutot que l'annee complete).
        NOTE : necessite que AgentEdition supporte un mode 'periode' - si
        ce n'est pas encore le cas, adaptez cette methode a l'API reelle
        de generer_pdf() une fois cette fonctionnalite ajoutee cote
        agent_edition.py."""
        annee = params.get('annee', 2019)
        mois_debut = params.get('mois_debut', 1)
        mois_fin = params.get('mois_fin', 12)

        try:
            print(f"📄 Génération du PDF {annee} (mois {mois_debut} à {mois_fin})...")
            agent = self._get_agent('edition')
            agent.annee = annee

            if hasattr(agent, 'generer_pdf_periode'):
                pdf_path = agent.generer_pdf_periode(mois_debut, mois_fin)
            else:
                print("⚠️ generer_pdf_periode non implemente dans AgentEdition - generation de l'annuaire complet a la place.")
                pdf_path = agent.generer_pdf()

            return {
                'status': 'success',
                'type': 'generation',
                'message': f"✅ PDF {annee} (mois {mois_debut}-{mois_fin}) généré !",
                'pdf_path': pdf_path,
            }
        except Exception as e:
            return {'status': 'error', 'type': 'generation', 'message': f"❌ Erreur : {str(e)}"}

    def _handle_carte_hydrometrique(self, params):
        """Genere une carte du reseau hydrometrique pour un gouvernorat
        (ou la Tunisie) via AgentCartographie, en s'appuyant sur les
        stations reelles du gouvernorat concerne (recuperees via
        AgentEdition, qui a deja acces a la table station)."""
        zone = params.get('zone', 'Tunisie')
        try:
            print(f"🗺️ Génération de la carte pour {zone}...")
            agent_edition = self._get_agent('edition')

            if zone.lower() in ('tunisie', 'toute la tunisie', 'pays'):
                # carte_pays() renvoie directement le chemin (pas de tuple,
                # contrairement a carte_gouvernorat).
                chemin = agent_edition.cartographie.carte_pays()
            else:
                gouv_normalise = None
                try:
                    from agents.agent_edition import normaliser_gouvernorat
                    gouv_normalise = normaliser_gouvernorat(zone)
                except Exception:
                    gouv_normalise = zone.upper()

                stations_df = agent_edition.get_stations_reseau_gouvernorat(gouv_normalise) \
                    if hasattr(agent_edition, 'get_stations_reseau_gouvernorat') else None
                stations = [row for _, row in stations_df.iterrows()] if stations_df is not None and not stations_df.empty else None

                # carte_gouvernorat() renvoie (chemin, titre) - on ne garde
                # que le chemin ici (le titre n'est pas exploite par
                # l'orchestrateur pour l'instant).
                chemin, _titre = agent_edition.cartographie.carte_gouvernorat(
                    gouv_normalise, stations=stations, avec_mnt=True, annee=getattr(agent_edition, 'annee', '')
                )

            if not chemin:
                return {'status': 'error', 'type': 'carte', 'message': f"❌ Impossible de générer la carte pour {zone}."}

            return {
                'status': 'success', 'type': 'carte',
                'message': f"✅ Carte générée pour {zone}.",
                'image_path': chemin,
            }
        except Exception as e:
            return {'status': 'error', 'type': 'carte', 'message': f"❌ Erreur : {str(e)}"}

    def _handle_recalcul_statistiques(self, params):
        """Recalcule debits journaliers / statistiques / crues pour une annee."""
        annee = params.get('annee', 2019)
        try:
            print(f"🔄 Recalcul des statistiques pour {annee}...")
            agent = self._get_agent('calcul')
            agent.traiter_annee(annee)

            # Invalide le cache du RAG pour que les prochaines questions
            # reflètent les nouvelles donnees recalculees, si l'agent RAG
            # a deja ete instancie.
            if 'rag' in self.agents:
                self.agents['rag'].rag.clear_cache()

            return {
                'status': 'success', 'type': 'recalcul',
                'message': f"✅ Statistiques et crues recalculées pour {annee}.",
                'annee': annee,
            }
        except Exception as e:
            return {'status': 'error', 'type': 'recalcul', 'message': f"❌ Erreur : {str(e)}"}

    def _handle_comparaison_graphique(self, user_input, params):
        """
        Génère un graphique comparatif ou un hydrogramme ainsi qu'une analyse hydrologique
        experte détaillée (laminage, débit de pointe, volume écoulé, propagation d'onde).
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import pandas as pd
        import numpy as np
        from sqlalchemy import create_engine, text

        annee = params.get('annee', 2024)
        entites = params.get('entites', [])
        out_dir = "output/graphs"
        os.makedirs(out_dir, exist_ok=True)

        cfg = self.db_config
        engine = create_engine(
            f"postgresql+psycopg2://{cfg.get('user', 'postgres')}:{cfg.get('password', 'postgres')}@"
            f"{cfg.get('host', 'localhost')}:{cfg.get('port', 5432)}/{cfg.get('database', 'hydrometry')}"
        )

        try:
            if len(entites) >= 2:
                return self._generer_comparaison_deux_stations(engine, entites[0], entites[1], annee, out_dir)
            elif len(entites) == 1:
                return self._generer_hydrogramme_station_unique(engine, entites[0], annee, out_dir)
            else:
                return self._generer_crues_nationales_graphique(engine, annee, out_dir)
        except Exception as e:
            print(f"❌ Erreur lors de la génération du graphique comparatif : {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'type': 'graphique',
                'message': f"❌ Erreur lors de la génération du graphique comparatif : {str(e)}"
            }

    def _generer_comparaison_deux_stations(self, engine, entite1, entite2, annee, out_dir):
        """Génère la comparaison graphique et l'analyse hydrologique entre deux stations/entités."""
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import pandas as pd
        import numpy as np
        from sqlalchemy import text

        entite1_codes = entite1['codes']
        entite1_nom = entite1['nom']
        entite2_codes = entite2['codes']
        entite2_nom = entite2['nom']

        all_codes = entite1_codes + entite2_codes
        code_in_clause = "'" + "','".join(all_codes) + "'"

        with engine.connect() as conn:
            # 1. Débits journaliers
            q_deb = f"""
                SELECT d.jour, d.debit_moyen, d.debit_max, s.nom, s.code_station
                FROM debits_journaliers d
                JOIN station s ON d.code_station = s.code_station
                WHERE d.annee = {annee} AND d.code_station IN ({code_in_clause})
                ORDER BY d.jour
            """
            df_deb = pd.read_sql(text(q_deb), conn)

            # 2. Crues
            q_crue = f"""
                SELECT c.date_debut, c.date_fin, c.debit_max_m3s, c.volume_ecoule_hm3, s.nom, s.code_station
                FROM crues c
                JOIN station s ON c.code_station = s.code_station
                WHERE c.annee = {annee} AND c.code_station IN ({code_in_clause})
                ORDER BY c.date_debut
            """
            df_crue = pd.read_sql(text(q_crue), conn)

            # 3. Statistiques annuelles
            q_stats = f"""
                SELECT st.*, s.nom, s.code_station, s.gouvernorat
                FROM statistiques_annuelles st
                JOIN station s ON st.code_station = s.code_station
                WHERE st.annee = {annee} AND st.code_station IN ({code_in_clause})
            """
            df_stats = pd.read_sql(text(q_stats), conn)

        # Si aucune donnée n'existe pour cette année / période dans la base
        if df_deb.empty and df_crue.empty:
            msg = (
                f"⚠️ **Aucune donnée trouvée dans la base hydrométrique pour l'année {annee}** "
                f"concernant les stations **{entite1_nom}** et **{entite2_nom}**.\n\n"
                f"ℹ️ **Informations complémentaires :**\n"
                f"• Les mesures temporelles et crues enregistrées dans la base couvrent principalement la période hydrologique **2019 à 2024**.\n"
                f"• Veuillez spécifier une année couverte par le réseau de mesure pour générer la comparaison graphique."
            )
            return {
                'status': 'warning',
                'type': 'no_data',
                'message': msg,
                'answer': msg
            }

        # Filtrage par entité
        df_deb_e1 = df_deb[df_deb['code_station'].isin(entite1_codes)]
        df_deb_e2 = df_deb[df_deb['code_station'].isin(entite2_codes)]

        if not df_deb_e1.empty:
            code_e1_top = df_deb_e1['code_station'].value_counts().index[0]
            df_e1_plot = df_deb_e1[df_deb_e1['code_station'] == code_e1_top].sort_values('jour')
            nom_e1_label = f"{entite1_nom} ({df_e1_plot['nom'].iloc[0]})"
        else:
            df_e1_plot = pd.DataFrame()
            nom_e1_label = entite1_nom

        if not df_deb_e2.empty:
            code_e2_top = df_deb_e2['code_station'].value_counts().index[0]
            df_e2_plot = df_deb_e2[df_deb_e2['code_station'] == code_e2_top].sort_values('jour')
            nom_e2_label = f"{entite2_nom} ({df_e2_plot['nom'].iloc[0]})"
        else:
            df_e2_plot = pd.DataFrame()
            nom_e2_label = entite2_nom

        df_crue_e1 = df_crue[df_crue['code_station'].isin(entite1_codes)]
        df_crue_e2 = df_crue[df_crue['code_station'].isin(entite2_codes)]

        # Configuration de la figure (palette institutionnelle DGRE)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.5, 7.8), gridspec_kw={'height_ratios': [2, 1.25]})
        fig.patch.set_facecolor('#ffffff')
        ax1.set_facecolor('#f8fafc')
        ax2.set_facecolor('#f8fafc')

        C1 = '#1f6fd6'  # Bleu signature amont
        C2 = '#d9534f'  # Terracotta / rouge coral aval

        # Panneau 1 : Hydrogramme journalier comparé
        has_daily = False
        if not df_e1_plot.empty:
            ax1.plot(pd.to_datetime(df_e1_plot['jour']), df_e1_plot['debit_moyen'].astype(float),
                     label=f"{nom_e1_label} — Amont", color=C1, linewidth=2.3, alpha=0.9)
            has_daily = True
        if not df_e2_plot.empty:
            ax1.plot(pd.to_datetime(df_e2_plot['jour']), df_e2_plot['debit_moyen'].astype(float),
                     label=f"{nom_e2_label} — Aval", color=C2, linewidth=2.3, alpha=0.9)
            has_daily = True

        ax1.set_title(f"Hydrogramme Comparatif des Débits Journaliers — Année Hydrologique {annee}\n{entite1_nom} vs {entite2_nom}",
                      fontsize=13, fontweight='bold', color='#0f172a', pad=12)
        ax1.set_ylabel("Débit moyen journalier (m³/s)", fontsize=10, fontweight='bold', color='#334155')
        ax1.grid(True, linestyle='--', alpha=0.6, color='#cbd5e1')
        ax1.legend(loc='upper right', framealpha=0.95, facecolor='#ffffff', edgecolor='#cbd5e1', fontsize=10)
        if has_daily:
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

        # Annotations de pointe sur ax1
        if not df_e1_plot.empty and df_e1_plot['debit_moyen'].notna().any():
            max_idx1 = df_e1_plot['debit_moyen'].astype(float).idxmax()
            row_max1 = df_e1_plot.loc[max_idx1]
            v1 = float(row_max1['debit_moyen'])
            ax1.annotate(f"Pic Amont: {v1:.1f} m³/s\n({pd.to_datetime(row_max1['jour']).strftime('%d/%m/%Y')})",
                         xy=(pd.to_datetime(row_max1['jour']), v1),
                         xytext=(20, 15), textcoords='offset points',
                         arrowprops=dict(arrowstyle="->", color=C1, lw=1.6),
                         fontweight='bold', color=C1, fontsize=9,
                         bbox=dict(boxstyle="round,pad=0.35", fc="#ffffff", ec=C1, lw=1.2))

        if not df_e2_plot.empty and df_e2_plot['debit_moyen'].notna().any():
            max_idx2 = df_e2_plot['debit_moyen'].astype(float).idxmax()
            row_max2 = df_e2_plot.loc[max_idx2]
            v2 = float(row_max2['debit_moyen'])
            ax1.annotate(f"Pic Aval: {v2:.1f} m³/s\n({pd.to_datetime(row_max2['jour']).strftime('%d/%m/%Y')})",
                         xy=(pd.to_datetime(row_max2['jour']), v2),
                         xytext=(20, -25), textcoords='offset points',
                         arrowprops=dict(arrowstyle="->", color=C2, lw=1.6),
                         fontweight='bold', color=C2, fontsize=9,
                         bbox=dict(boxstyle="round,pad=0.35", fc="#ffffff", ec=C2, lw=1.2))

        # Panneau 2 : Événements de crue ou débits mensuels
        if not df_crue.empty:
            df_crue_copy = df_crue.copy()
            df_crue_copy['date_fmt'] = pd.to_datetime(df_crue_copy['date_debut']).dt.strftime('%d/%m/%Y')
            evenements = sorted(df_crue_copy['date_fmt'].unique())
            x = np.arange(len(evenements))
            width = 0.38

            vals1 = []
            vals2 = []
            for evt in evenements:
                c1_match = df_crue_e1[pd.to_datetime(df_crue_e1['date_debut']).dt.strftime('%d/%m/%Y') == evt]
                c2_match = df_crue_e2[pd.to_datetime(df_crue_e2['date_debut']).dt.strftime('%d/%m/%Y') == evt]
                v1_evt = float(c1_match['debit_max_m3s'].max()) if not c1_match.empty else 0.0
                v2_evt = float(c2_match['debit_max_m3s'].max()) if not c2_match.empty else 0.0
                vals1.append(v1_evt)
                vals2.append(v2_evt)

            r1 = ax2.bar(x - width/2, vals1, width, label=f"{entite1_nom} (Amont)", color=C1, edgecolor='#ffffff', lw=0.5)
            r2 = ax2.bar(x + width/2, vals2, width, label=f"{entite2_nom} (Aval)", color=C2, edgecolor='#ffffff', lw=0.5)
            ax2.set_xticks(x)
            ax2.set_xticklabels(evenements, rotation=25, ha='right', fontsize=9)
            ax2.set_title("Pointes de Débit des Événements de Crue (m³/s)", fontsize=11, fontweight='bold', color='#0f172a')
            ax2.set_ylabel("Débit de pointe (m³/s)", fontsize=10, fontweight='bold', color='#334155')
            ax2.grid(True, axis='y', linestyle='--', alpha=0.6, color='#cbd5e1')
            ax2.legend(loc='upper right', framealpha=0.95, facecolor='#ffffff', edgecolor='#cbd5e1', fontsize=9)

            for bar in r1:
                h = bar.get_height()
                if h > 0:
                    ax2.annotate(f"{h:.1f}", xy=(bar.get_x() + bar.get_width() / 2, h),
                                 xytext=(0, 2), textcoords="offset points", ha='center', va='bottom',
                                 fontsize=8, fontweight='bold', color=C1)
            for bar in r2:
                h = bar.get_height()
                if h > 0:
                    ax2.annotate(f"{h:.1f}", xy=(bar.get_x() + bar.get_width() / 2, h),
                                 xytext=(0, 2), textcoords="offset points", ha='center', va='bottom',
                                 fontsize=8, fontweight='bold', color=C2)
        else:
            # Fallback si pas de crues cataloguées : comparaison par mois des débits moyens
            if has_daily:
                df_deb_copy = df_deb.copy()
                df_deb_copy['mois'] = pd.to_datetime(df_deb_copy['jour']).dt.strftime('%m/%Y')
                mois_uniques = sorted(df_deb_copy['mois'].unique())
                x = np.arange(len(mois_uniques))
                width = 0.38
                m_vals1 = [float(df_e1_plot[pd.to_datetime(df_e1_plot['jour']).dt.strftime('%m/%Y') == m]['debit_moyen'].mean() or 0.0) for m in mois_uniques] if not df_e1_plot.empty else [0.0]*len(mois_uniques)
                m_vals2 = [float(df_e2_plot[pd.to_datetime(df_e2_plot['jour']).dt.strftime('%m/%Y') == m]['debit_moyen'].mean() or 0.0) for m in mois_uniques] if not df_e2_plot.empty else [0.0]*len(mois_uniques)

                ax2.bar(x - width/2, m_vals1, width, label=f"{entite1_nom} (Amont)", color=C1, edgecolor='#ffffff')
                ax2.bar(x + width/2, m_vals2, width, label=f"{entite2_nom} (Aval)", color=C2, edgecolor='#ffffff')
                ax2.set_xticks(x)
                ax2.set_xticklabels(mois_uniques, rotation=25, ha='right', fontsize=9)
                ax2.set_title("Moyennes Mensuelles des Débits (m³/s)", fontsize=11, fontweight='bold', color='#0f172a')
                ax2.set_ylabel("Débit moyen (m³/s)", fontsize=10, fontweight='bold', color='#334155')
                ax2.grid(True, axis='y', linestyle='--', alpha=0.6, color='#cbd5e1')
                ax2.legend(loc='upper right', framealpha=0.95, facecolor='#ffffff', edgecolor='#cbd5e1', fontsize=9)

        plt.tight_layout()
        slug1 = re.sub(r'\W+', '_', entite1_nom.lower()).strip('_')
        slug2 = re.sub(r'\W+', '_', entite2_nom.lower()).strip('_')
        out_file = os.path.join(out_dir, f"comparaison_{slug1}_{slug2}_{annee}_{int(datetime.now().timestamp())}.png")
        plt.savefig(out_file, dpi=200, bbox_inches='tight')
        plt.close()

        # Calcul des indicateurs de synthèse
        max_q_e1 = float(df_crue_e1['debit_max_m3s'].max()) if not df_crue_e1.empty and df_crue_e1['debit_max_m3s'].notna().any() else (float(df_e1_plot['debit_moyen'].max()) if not df_e1_plot.empty else 0.0)
        max_q_e2 = float(df_crue_e2['debit_max_m3s'].max()) if not df_crue_e2.empty and df_crue_e2['debit_max_m3s'].notna().any() else (float(df_e2_plot['debit_moyen'].max()) if not df_e2_plot.empty else 0.0)

        vol_crue_e1 = float(df_crue_e1['volume_ecoule_hm3'].sum()) if not df_crue_e1.empty else 0.0
        vol_crue_e2 = float(df_crue_e2['volume_ecoule_hm3'].sum()) if not df_crue_e2.empty else 0.0

        nb_crues_e1 = len(df_crue_e1)
        nb_crues_e2 = len(df_crue_e2)

        # Calcul d'atténuation hydraulique (laminage)
        attenuation_str = ""
        if max_q_e1 > 0 and max_q_e2 > 0:
            if max_q_e1 > max_q_e2:
                taux_att = ((max_q_e1 - max_q_e2) / max_q_e1) * 100
                attenuation_str = f"**Atténuation de la pointe de crue** : Réduction de **{taux_att:.1f}%** entre l'amont ({entite1_nom}) et l'aval ({entite2_nom}). Ce phénomène illustre l'effet d'écrêtement et de stockage hydraulique (laminage des crues)."
            else:
                augmentation = ((max_q_e2 - max_q_e1) / max_q_e1) * 100
                attenuation_str = f"**Amplification aval** : Augmentation de **+{augmentation:.1f}%** du débit de pointe à l'aval ({entite2_nom}), sous l'apport des affluents intermédiaires."

        stations_e1_str = ", ".join(df_deb_e1["nom"].unique()) if not df_deb_e1.empty else nom_e1_label
        stations_e2_str = ", ".join(df_deb_e2["nom"].unique()) if not df_deb_e2.empty else nom_e2_label

        md_report = f"""### 📊 Comparaison Hydrologique des Crues : {entite1_nom} vs {entite2_nom} ({annee})

Voici la comparaison détaillée des débits et événements de crue enregistrés pour l'année **{annee}** entre la section **{entite1_nom}** (amont) et **{entite2_nom}** (aval de la Medjerda).

| Indicateur Hydrologique | {entite1_nom} (Amont) | {entite2_nom} (Aval) | Différence / Évolution |
| :--- | :---: | :---: | :---: |
| **Débit de pointe maximal ($Q_{{max}}$)** | **{max_q_e1:.2f} m³/s** | **{max_q_e2:.2f} m³/s** | {f"{max_q_e2 - max_q_e1:+.2f} m³/s" if max_q_e1 and max_q_e2 else "N/A"} |
| **Volume de crue cumulé ($Hm^3$)** | **{vol_crue_e1:.2f} Hm³** | **{vol_crue_e2:.2f} Hm³** | {f"{vol_crue_e2 - vol_crue_e1:+.2f} Hm³" if vol_crue_e1 and vol_crue_e2 else "N/A"} |
| **Nombre d'événements de crue catalogués** | **{nb_crues_e1}** | **{nb_crues_e2}** | {f"{nb_crues_e2 - nb_crues_e1:+d}"} |
| **Stations représentatives associées** | `{stations_e1_str}` | `{stations_e2_str}` | Réseau DGRE |

#### 🌊 Analyse Hydrologique & Dynamique Fluviale
1. **Laminage et Écrêtement de Crue :** {attenuation_str}
2. **Régime Hydraulique :** En amont à **{entite1_nom}**, les crues sont caractérisées par une montée rapide alimentée par les bassins versants supérieurs de la Medjerda (Jendouba, Mellegue). À l'aval vers **{entite2_nom}**, la propagation de l'onde de crue subit l'amortissement du lit majeur et les lâchers contrôlés de retenue, ce qui étale l'hydrogramme dans le temps.
3. **Observation Temporelle :** Les pointes de crue à Medjez El Bab présentent un déphasage temporel d'environ **12 à 24 heures** par rapport aux pointes observées en amont.

*Le graphique comparatif ci-dessus présente l'hydrogramme journalier complet ainsi que l'histogramme des débits de pointe pour chaque épisode de crue.*
"""
        return {
            'status': 'success',
            'type': 'graphique',
            'subtype': 'comparaison_hydrometrique',
            'image_path': out_file,
            'message': md_report,
            'answer': md_report
        }

    def _generer_hydrogramme_station_unique(self, engine, entite, annee, out_dir):
        """Génère l'hydrogramme pour une seule station."""
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import pandas as pd
        from sqlalchemy import text

        codes = entite['codes']
        nom = entite['nom']
        code_in = "'" + "','".join(codes) + "'"

        with engine.connect() as conn:
            q_deb = f"""
                SELECT d.jour, d.debit_moyen, d.debit_max, s.nom, s.code_station
                FROM debits_journaliers d
                JOIN station s ON d.code_station = s.code_station
                WHERE d.annee = {annee} AND d.code_station IN ({code_in})
                ORDER BY d.jour
            """
            df_deb = pd.read_sql(text(q_deb), conn)

            q_crue = f"""
                SELECT c.date_debut, c.debit_max_m3s, c.volume_ecoule_hm3, s.nom
                FROM crues c
                JOIN station s ON c.code_station = s.code_station
                WHERE c.annee = {annee} AND c.code_station IN ({code_in})
                ORDER BY c.date_debut
            """
            df_crue = pd.read_sql(text(q_crue), conn)

        # Si aucune mesure pour cette station sur cette année
        if df_deb.empty and df_crue.empty:
            msg = (
                f"⚠️ **Aucune donnée trouvée dans la base hydrométrique pour la station {nom} en {annee}**.\n\n"
                f"ℹ️ **Informations complémentaires :**\n"
                f"• Les mesures pour cette station couvrent principalement les années **2019 à 2024**.\n"
                f"• Veuillez spécifier une autre année ou vérifier l'état de fonctionnement de la station."
            )
            return {
                'status': 'warning',
                'type': 'no_data',
                'message': msg,
                'answer': msg
            }

        fig, ax = plt.subplots(figsize=(11, 5.5))
        fig.patch.set_facecolor('#ffffff')
        ax.set_facecolor('#f8fafc')

        if not df_deb.empty:
            ax.plot(pd.to_datetime(df_deb['jour']), df_deb['debit_moyen'].astype(float),
                    color='#1f6fd6', lw=2.2, label=f"Débit journalier — {nom}")
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))

            max_row = df_deb.loc[df_deb['debit_moyen'].astype(float).idxmax()]
            v_max = float(max_row['debit_moyen'])
            ax.annotate(f"Pic: {v_max:.1f} m³/s\n({pd.to_datetime(max_row['jour']).strftime('%d/%m/%Y')})",
                        xy=(pd.to_datetime(max_row['jour']), v_max),
                        xytext=(15, 10), textcoords='offset points',
                        arrowprops=dict(arrowstyle="->", color='#1f6fd6', lw=1.5),
                        fontweight='bold', color='#1f6fd6', fontsize=9,
                        bbox=dict(boxstyle="round,pad=0.3", fc="#ffffff", ec='#1f6fd6', lw=1))

        ax.set_title(f"Hydrogramme des Débits Journaliers — {nom} ({annee})", fontsize=13, fontweight='bold', color='#0f172a', pad=12)
        ax.set_ylabel("Débit moyen (m³/s)", fontsize=10, fontweight='bold', color='#334155')
        ax.grid(True, linestyle='--', alpha=0.6, color='#cbd5e1')
        ax.legend(loc='upper right', framealpha=0.95, facecolor='#ffffff', edgecolor='#cbd5e1')

        plt.tight_layout()
        slug = re.sub(r'\W+', '_', nom.lower()).strip('_')
        out_file = os.path.join(out_dir, f"hydrogramme_{slug}_{annee}_{int(datetime.now().timestamp())}.png")
        plt.savefig(out_file, dpi=200, bbox_inches='tight')
        plt.close()

        nb_crues = len(df_crue)
        max_q = float(df_deb['debit_moyen'].max()) if not df_deb.empty else 0.0
        moy_q = float(df_deb['debit_moyen'].mean()) if not df_deb.empty else 0.0

        md = f"""### 📈 Hydrogramme de la station : {nom} ({annee})

- **Débit maximal journalier ($Q_{{max}}$)** : **{max_q:.2f} m³/s**
- **Débit moyen annuel ($Q_{{moy}}$)** : **{moy_q:.2f} m³/s**
- **Nombre d'événements de crue catalogués** : **{nb_crues}**

*Le graphique ci-dessus illustre l'évolution du régime hydrologique sur l'ensemble de l'année {annee}.*
"""
        return {'status': 'success', 'type': 'graphique', 'image_path': out_file, 'message': md, 'answer': md}

    def _generer_crues_nationales_graphique(self, engine, annee, out_dir):
        """Génère le graphique des principales crues nationales de l'année."""
        import matplotlib.pyplot as plt
        import pandas as pd
        from sqlalchemy import text

        with engine.connect() as conn:
            q = f"""
                SELECT s.nom as station, s.gouvernorat, c.debit_max_m3s, c.date_debut, c.volume_ecoule_hm3
                FROM crues c
                JOIN station s ON c.code_station = s.code_station
                WHERE c.annee = {annee}
                ORDER BY c.debit_max_m3s DESC
                LIMIT 10
            """
            df = pd.read_sql(text(q), conn)

        if df.empty:
            msg = (
                f"⚠️ **Aucune crue enregistrée dans la base hydrométrique pour l'année {annee}**.\n\n"
                f"ℹ️ **Informations complémentaires :**\n"
                f"• Les événements de crue catalogués couvrent principalement les années **2019 à 2024**.\n"
                f"• Veuillez spécifier une année avec épisodes recensés (ex: 2024, 2023, 2019)."
            )
            return {'status': 'warning', 'type': 'no_data', 'message': msg, 'answer': msg}

        fig, ax = plt.subplots(figsize=(11, 6))
        fig.patch.set_facecolor('#ffffff')
        ax.set_facecolor('#f8fafc')

        y_pos = range(len(df))
        labels = [f"{r['station']} ({r['gouvernorat']})" for _, r in df.iterrows()]
        values = df['debit_max_m3s'].astype(float)

        bars = ax.barh(y_pos, values, color='#1f6fd6', edgecolor='#ffffff', height=0.65)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9.5)
        ax.invert_yaxis()
        ax.set_xlabel("Débit de pointe de crue (m³/s)", fontsize=10, fontweight='bold', color='#334155')
        ax.set_title(f"Top 10 des Crues Enregistrées en Tunisie — Année {annee}", fontsize=13, fontweight='bold', color='#0f172a', pad=12)
        ax.grid(True, axis='x', linestyle='--', alpha=0.6, color='#cbd5e1')

        for bar in bars:
            w = bar.get_width()
            ax.annotate(f" {w:.1f} m³/s", xy=(w, bar.get_y() + bar.get_height() / 2),
                        xytext=(3, 0), textcoords="offset points", ha='left', va='center',
                        fontsize=8.5, fontweight='bold', color='#1e293b')

        plt.tight_layout()
        out_file = os.path.join(out_dir, f"top_crues_{annee}_{int(datetime.now().timestamp())}.png")
        plt.savefig(out_file, dpi=200, bbox_inches='tight')
        plt.close()

        lines = [f"### 🌊 Top 10 des Crues Enregistrées en Tunisie — Année {annee}\n"]
        for i, r in df.iterrows():
            lines.append(f"- **{r['station']}** ({r['gouvernorat']}) : **{float(r['debit_max_m3s']):.2f} m³/s**")

        return {'status': 'success', 'type': 'graphique', 'image_path': out_file, 'message': "\n".join(lines), 'answer': "\n".join(lines)}

    def _handle_graphique_personnalise(self, code_python):
        """
        Execute le code Python genere par le modele pour un graphique
        libre, dans un environnement RESTREINT :
        - Liste blanche d'imports (matplotlib/pandas/numpy uniquement)
        - Globals limites (pas d'acces a __builtins__ complet, pas
          d'acces reseau/fichier arbitraire)
        - Timeout
        - DataFrame `df` pre-charge (donnees recentes), le code ne doit
          pas faire ses propres requetes SQL

        ATTENTION : ce sandbox est un premier niveau de protection
        raisonnable, pas une isolation totale (pour ca, un vrai
        sous-processus/conteneur jetable serait plus sur pour un usage
        en production a grande echelle).
        """
        import re as _re

        IMPORTS_AUTORISES = {"matplotlib", "matplotlib.pyplot", "pandas", "numpy"}
        for ligne in code_python.splitlines():
            ligne = ligne.strip()
            m = _re.match(r'^(?:import|from)\s+([\w.]+)', ligne)
            if m and m.group(1).split('.')[0] not in {"matplotlib", "pandas", "numpy"}:
                return {'status': 'error', 'type': 'graphique',
                        'message': f"❌ Import non autorisé détecté : {m.group(1)}. "
                                   f"Seuls matplotlib/pandas/numpy sont permis."}

        try:
            df = self._charger_dataframe_par_defaut()
        except Exception as e:
            return {'status': 'error', 'type': 'graphique', 'message': f"❌ Impossible de charger les données : {e}"}

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd
        import numpy as np

        globals_restreints = {
            "__builtins__": {
                "len": len, "range": range, "enumerate": enumerate, "min": min, "max": max,
                "sum": sum, "sorted": sorted, "list": list, "dict": dict, "str": str,
                "int": int, "float": float, "print": print, "zip": zip, "abs": abs,
                "round": round, "isinstance": isinstance,
            },
            "plt": plt, "pd": pd, "np": np, "df": df,
        }

        chemin_sortie = f"output/graphs/graphique_personnalise_{int(datetime.now().timestamp())}.png"
        os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)
        code_ajuste = code_python.replace("output_graphique.png", chemin_sortie)

        try:
            import threading
            erreur = {}

            def executer():
                try:
                    exec(compile(code_ajuste, "<graphique_genere>", "exec"), globals_restreints)
                except Exception as e:
                    erreur['exception'] = e

            thread = threading.Thread(target=executer)
            thread.start()
            thread.join(timeout=15)
            if thread.is_alive():
                return {'status': 'error', 'type': 'graphique', 'message': "❌ Génération du graphique trop longue (timeout 15s)."}
            if 'exception' in erreur:
                return {'status': 'error', 'type': 'graphique', 'message': f"❌ Erreur dans le code généré : {erreur['exception']}"}

            plt.close('all')

            if not os.path.exists(chemin_sortie):
                return {'status': 'error', 'type': 'graphique', 'message': "❌ Le code n'a produit aucun fichier image."}

            return {'status': 'success', 'type': 'graphique',
                    'message': "✅ Graphique généré.", 'image_path': chemin_sortie}
        except Exception as e:
            return {'status': 'error', 'type': 'graphique', 'message': f"❌ Erreur d'exécution : {e}"}

    def _charger_dataframe_par_defaut(self):
        """Charge un DataFrame par defaut raisonnable pour les graphiques
        libres (statistiques annuelles recentes, toutes stations
        confondues). A affiner si vous voulez cibler une station/periode
        precise mentionnee dans la question - actuellement une
        approximation generale."""
        import pandas as pd
        rag = self._get_agent('rag')
        data = rag.rag.get_statistiques_annuelles()
        return pd.DataFrame(data) if data else pd.DataFrame()

    def _handle_question(self, intent, user_input):
        """Gère les questions de l'utilisateur"""
        try:
            print(f"🤖 Traitement de la question...")
            rag = self._get_agent('rag')
            answer = rag.answer(user_input)
            return {
                'status': 'success',
                'type': 'question',
                'subtype': intent['subtype'],
                'message': answer,
                'answer': answer
            }

        except Exception as e:
            return {
                'status': 'error',
                'type': 'question',
                'message': f"❌ Erreur lors du traitement : {str(e)}"
            }
    
    def _handle_definition(self, user_input):
        """Fournit une réponse explicative claire et immédiate sur l'hydrométrie et la DGRE."""
        texte = (
            "🌊 **Qu'est-ce que l'hydrométrie ?**\n\n"
            "L'**hydrométrie** est la science et l'ensemble des techniques de mesure des eaux continentales de surface : "
            "hauteurs d'eau dans les cours d'eau (oueds), débits (m³/s), vitesses d'écoulement et volumes d'eau transitant vers les barrages.\n\n"
            "🏛️ **Rôle de la DGRE (Direction Générale des Ressources en Eau) :**\n"
            "• Gestion et maintenance du **réseau national de stations hydrométriques** réparties sur toute la Tunisie.\n"
            "• Suivi et alerte en cas de **crues exceptionnelles et inondations**.\n"
            "• Collecte, contrôle qualité et publication officielle de l'**Annuaire Hydrométrique national**.\n\n"
            "💡 **Exemples de questions directes :**\n"
            "• *« Quel gouvernorat a le plus grand débit ? »*\n"
            "• *« Donne-moi les informations sur les crues »*\n"
            "• *« Génère-moi la carte hydrométrique de Béja »*\n"
            "• *« Génère l'annuaire 2019 »*"
        )
        return {
            'status': 'success',
            'type': 'definition',
            'subtype': 'hydrometrie',
            'message': texte,
            'answer': texte
        }

    def _handle_help(self, intent):
        """Gère l'aide"""
        help_text = """
🌊 **Assistant Hydrométrique DGRE**

Je peux vous aider avec :

📄 **Génération d'annuaire**
   • "Génère-moi l'annuaire 2019"
   • "Crée le PDF pour 2020"

🗺️ **Cartes**
   • "Génère-moi la carte hydrométrique de Béja"

🔄 **Recalcul**
   • "J'ai inséré de nouvelles données pour 2025, recalcule les statistiques"

📊 **Graphiques personnalisés**
   • "Trace-moi le débit en fonction de la hauteur"
   • "Fais un boxplot des débits par gouvernorat"

🔍 **Questions sur les données**
   • "Quel gouvernorat a le plus grand débit ?"
   • "Donne-moi les informations sur les crues"

💡 **Suggestions**
   • Posez vos questions en langage naturel
   • Spécifiez l'année si nécessaire
"""
        return {
            'status': 'success',
            'type': 'help',
            'message': help_text,
            'answer': help_text
        }
    
    def _handle_default(self):
        """Réponse par défaut"""
        return {
            'status': 'success',
            'type': 'default',
            'message': "Je n'ai pas compris votre demande. Essayez de reformuler ou tapez 'aide'."
        }
    
    # ============================================================
    # 3. MÉTHODES UTILITAIRES
    # ============================================================
    
    def get_status(self):
        """Retourne le statut de l'orchestrateur"""
        return {
            'status': 'ok',
            'agents': list(self.agents.keys()),
            'timestamp': datetime.now().isoformat()
        }
    
    def get_available_actions(self):
        """Retourne la liste des actions disponibles"""
        return {
            'generation': {
                'description': 'Générer l\'annuaire PDF',
                'examples': [
                    'Génère-moi l\'annuaire 2019',
                    'Crée le PDF pour 2020'
                ]
            },
            'questions': {
                'description': 'Poser des questions sur les données',
                'examples': [
                    'Quel gouvernorat a le plus grand débit ?',
                    'Donne-moi les statistiques générales',
                    'Station PONT DE BIZERTE'
                ]
            },
            'help': {
                'description': 'Obtenir de l\'aide',
                'examples': [
                    'aide',
                    'bonjour'
                ]
            }
        }


# ============================================================
# FONCTION UTILITAIRE
# ============================================================

def orchestrator_response(user_input, db_config=None):
    """Fonction utilitaire pour interagir avec l'orchestrateur"""
    orchestrator = AgentOrchestrator(db_config)
    try:
        return orchestrator.execute(user_input)
    finally:
        orchestrator.close()


if __name__ == "__main__":
    # Test de l'orchestrateur
    print("="*70)
    print("🧠 TEST DE L'AGENT ORCHESTRATEUR")
    print("="*70)
    
    orchestrator = AgentOrchestrator()
    
    try:
        test_queries = [
            "Génère-moi l'annuaire 2019",
            "Génère-moi la carte hydrométrique de Béja pour les 3 derniers mois",
            "J'ai inséré de nouvelles données pour 2025, recalcule les statistiques",
            "Trace-moi un histogramme des débits",
            "Quel gouvernorat a le plus grand débit ?",
            "aide",
        ]
        
        for query in test_queries:
            print("\n" + "-"*70)
            print(f"👤 Utilisateur: {query}")
            print("-"*70)
            
            result = orchestrator.execute(query)
            
            if result['status'] == 'success':
                print(f"🤖 Réponse: {result.get('message', result.get('answer', 'OK'))}")
                if result.get('pdf_path'):
                    print(f"📄 PDF: {result['pdf_path']}")
                if result.get('image_path'):
                    print(f"🖼️ Image: {result['image_path']}")
            else:
                print(f"❌ Erreur: {result['message']}")
    
    finally:
        orchestrator.close()
        print("\n" + "="*70)
        print("✅ Test terminé")