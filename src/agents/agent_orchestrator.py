"""
src/agents/agent_orchestrator.py
Agent Orchestrateur - Coordonne tous les agents métier
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import json
import re

class AgentOrchestrator:
    """
    Orchestrateur principal - Gère le pipeline complet :
    1. Analyse de l'intention utilisateur
    2. Coordination des agents métier
    3. Génération de l'annuaire
    4. Réponse aux questions
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
        self._init_agents()
        print("✅ Agent Orchestrateur initialisé")
    
    def _init_agents(self):
        """Initialise tous les agents"""
        try:
            from agents.agent_calcul import AgentCalcul
            self.agents['calcul'] = AgentCalcul(self.db_config)
            print("✅ AgentCalcul chargé")
        except Exception as e:
            print(f"⚠️ AgentCalcul non disponible: {e}")
        
        try:
            from agents.agent_edition import AgentEdition
            self.agents['edition'] = AgentEdition(self.db_config)
            print("✅ AgentEdition chargé")
        except Exception as e:
            print(f"⚠️ AgentEdition non disponible: {e}")
        
        try:
            from agents.agent_rag import AgentRAGOrchestrator
            self.agents['rag'] = AgentRAGOrchestrator(self.db_config)
            print("✅ AgentRAG chargé")
        except Exception as e:
            print(f"⚠️ AgentRAG non disponible: {e}")
    
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
    
    def detect_intent(self, user_input):
        """
        Détecte l'intention de l'utilisateur
        Retourne : {
            'type': 'generation' | 'question' | 'help',
            'subtype': 'pdf' | 'stats' | 'station' | 'crues' | ...,
            'params': {...}
        }
        """
        input_lower = user_input.lower().strip()
        
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
        question_keywords = ['quel', 'quelle', 'quels', 'quelles', 'combien', 'comment', 'pourquoi', 'est-ce que']
        if any(kw in input_lower for kw in question_keywords) or '?' in input_lower:
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
            
            if 'volume' in input_lower:
                return {
                    'type': 'question',
                    'subtype': 'total_volume',
                    'params': {},
                    'message': "Recherche du volume total"
                }
            
            if 'crue' in input_lower or 'crues' in input_lower:
                return {
                    'type': 'question',
                    'subtype': 'crues',
                    'params': {},
                    'message': "Recherche des informations sur les crues"
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
        Point d'entrée principal - Exécute l'intention détectée
        """
        print(f"\n🔍 Analyse de la requête: {user_input}")
        
        intent = self.detect_intent(user_input)
        print(f"🎯 Intention: {intent['type']} - {intent['subtype']}")
        
        if intent['type'] == 'generation':
            return self._handle_generation(intent)
        elif intent['type'] == 'question':
            return self._handle_question(intent, user_input)
        elif intent['type'] == 'help':
            return self._handle_help(intent)
        else:
            return self._handle_default()
    
    def _handle_generation(self, intent):
        """Gère la génération de l'annuaire PDF"""
        annee = intent['params'].get('annee', 2019)
        
        try:
            from agents.agent_edition import AgentEdition
            
            print(f"📄 Génération de l'annuaire {annee}...")
            
            agent = AgentEdition(
                annee=annee,
                output_dir="output/pdf/",
                db_config=self.db_config
            )
            
            try:
                pdf_path = agent.generer_pdf()
                return {
                    'status': 'success',
                    'type': 'generation',
                    'message': f"✅ Annuaire {annee}-{annee+1} généré avec succès !",
                    'pdf_path': pdf_path,
                    'annee': annee
                }
            finally:
                agent.close()
                
        except Exception as e:
            return {
                'status': 'error',
                'type': 'generation',
                'message': f"❌ Erreur lors de la génération : {str(e)}"
            }
    
    def _handle_question(self, intent, user_input):
        """Gère les questions de l'utilisateur"""
        try:
            from agents.agent_rag import AgentRAGOrchestrator
            
            print(f"🤖 Traitement de la question...")
            
            rag = AgentRAGOrchestrator(self.db_config)
            try:
                answer = rag.answer(user_input)
                return {
                    'status': 'success',
                    'type': 'question',
                    'subtype': intent['subtype'],
                    'message': answer,
                    'answer': answer
                }
            finally:
                rag.close()
                
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

🔍 **Questions sur les données**
   • "Quel gouvernorat a le plus grand débit ?"
   • "Quel est le débit moyen par gouvernorat ?"
   • "Donne-moi les informations sur les crues"
   • "Quelle est la station avec le plus grand volume ?"
   • "Donne-moi les statistiques générales"

📊 **Informations sur les stations**
   • "Station PONT DE BIZERTE"
   • "Informations sur la station TUBURBO MAJUS"

💡 **Suggestions**
   • Posez vos questions en langage naturel
   • Spécifiez l'année si nécessaire
   • Soyez précis pour de meilleurs résultats
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
            "Quel gouvernorat a le plus grand débit ?",
            "Donne-moi les statistiques générales",
            "aide",
            "Station PONT DE BIZERTE"
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
            else:
                print(f"❌ Erreur: {result['message']}")
    
    finally:
        orchestrator.close()
        print("\n" + "="*70)
        print("✅ Test terminé")