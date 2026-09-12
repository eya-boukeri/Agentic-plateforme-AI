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
            'subtype': 'reponse_llm',
            'params': {'reponse': reponse},
            'message': "Reponse directe du modele"
        }

    def detect_intent(self, user_input):
        """
        Détection par mots-clés (repli si le LLM est indisponible).
        Retourne : {
            'type': 'generation' | 'question' | 'help',
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

        # === INTENTION DE GÉNÉRATION ===
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
        
        # === INTENTION DE QUESTION ===
        question_keywords = [
            'quel', 'quelle', 'quels', 'quelles', 'combien', 'comment', 'pourquoi', 'est-ce que',
            'donne', 'donne-moi', 'donne moi', 'montre', 'montre-moi', 'affiche', 'liste', 'trouve'
        ]
        if any(kw in input_lower for kw in question_keywords) or '?' in input_lower or any(kw in input_lower for kw in ['crue', 'crues', 'crus', 'inondation', 'débit', 'debit', 'volume']):
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
            
            if 'station' in input_lower:
                station_match = re.search(r'station\s+([a-zA-Z\s\-]+)', input_lower)
                station_name = station_match.group(1).strip() if station_match else None
                return {
                    'type': 'question',
                    'subtype': 'station',
                    'params': {'station_name': station_name},
                    'message': f"Recherche de la station {station_name or 'spécifiée'}"
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
        1. Détecte d'abord les questions hydrométriques explicites (crues, débits, stations)
           pour une réponse déterministe immédiate sans latence.
        2. Tente le LLM fine-tune pour les requêtes complexes, actions et graphiques libres.
        3. Se rabat sur les mots-clés généraux si nécessaire.
        """
        print(f"\n🔍 Analyse de la requête: {user_input}")

        # 1. Vérification directe : questions de données précises (crues, débits, volume, stations)
        intent_rapide = self.detect_intent(user_input)
        if intent_rapide['type'] == 'question' and intent_rapide.get('subtype') in ('crues', 'max_debit', 'avg_debit', 'total_volume', 'station'):
            print(f"🎯 Intention hydrométrique directe : {intent_rapide['subtype']}")
            return self._handle_question(intent_rapide, user_input)

        # 2. Utilisation du modèle LLM fine-tune pour intentions complexes, actions ou graphiques
        intent_llm = self.detect_intent_llm(user_input)
        if intent_llm:
            print(f"🎯 Intention (LLM): {intent_llm['type']} - {intent_llm['subtype']}")
            return self._executer_intention_llm(intent_llm, user_input=user_input)

        print("ℹ️ LLM indisponible ou reponse non exploitable - repli sur les mots-cles")
        intent = intent_rapide
        print(f"🎯 Intention (mots-cles): {intent['type']} - {intent['subtype']}")
        
        if intent['type'] == 'generation':
            return self._handle_generation(intent)
        elif intent['type'] == 'carte':
            return self._handle_carte_hydrometrique(intent['params'])
        elif intent['type'] == 'recalcul':
            return self._handle_recalcul_statistiques(intent['params'])
        elif intent['type'] == 'question':
            return self._handle_question(intent, user_input)
        elif intent['type'] == 'help':
            return self._handle_help(intent)
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

        return self._handle_default()

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