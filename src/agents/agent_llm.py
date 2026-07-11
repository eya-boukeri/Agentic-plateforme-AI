"""
src/agents/agent_llm.py
Agent LLM - Utilisation de modèles open source via Ollama
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
import time
from datetime import datetime

class AgentLLM:
    """
    Agent LLM utilisant Ollama pour générer des réponses en langage naturel
    Modèles recommandés : mistral, llama3, phi3, gemma
    """
    
    def __init__(self, model="mistral", host="http://localhost:11434"):
        """
        Initialise l'agent LLM avec un modèle Ollama
        
        Args:
            model: Nom du modèle Ollama (mistral, llama3, phi3, etc.)
            host: URL du serveur Ollama
        """
        self.model = model
        self.host = host
        self.api_url = f"{host}/api/generate"
        self.chat_url = f"{host}/api/chat"
        self.available = False
        self.model_loaded = False
        
        # Vérifier la disponibilité d'Ollama
        self._check_availability()
    
    def _check_availability(self):
        """Vérifie si Ollama est disponible"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                
                # Vérifier si le modèle demandé est disponible
                if any(self.model in name for name in model_names):
                    self.available = True
                    self.model_loaded = True
                    print(f"✅ LLM disponible : {self.model}")
                else:
                    self.available = True
                    self.model_loaded = False
                    print(f"⚠️ Modèle {self.model} non trouvé.")
                    print(f"   Modèles disponibles : {', '.join(model_names)}")
                    print(f"   Installez-le avec : ollama pull {self.model}")
            else:
                self.available = False
                print("⚠️ Ollama n'est pas disponible. Vérifiez qu'il est lancé (ollama serve)")
        except Exception as e:
            self.available = False
            print(f"⚠️ Erreur de connexion à Ollama : {e}")
    
    def generate(self, prompt, system_prompt=None, temperature=0.7, max_tokens=500):
        """
        Génère une réponse à partir d'un prompt
        
        Args:
            prompt: Le prompt utilisateur
            system_prompt: Prompt système optionnel
            temperature: Créativité (0-1)
            max_tokens: Nombre max de tokens
        
        Returns:
            str: Réponse générée ou None en cas d'erreur
        """
        if not self.available:
            return None
        
        try:
            # Construire le prompt complet
            full_prompt = ""
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n"
            full_prompt += prompt
            
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                print(f"❌ Erreur LLM: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            print("❌ Erreur LLM: Timeout - Le modèle met trop de temps à répondre")
            return None
        except Exception as e:
            print(f"❌ Erreur LLM: {e}")
            return None
    
    def chat(self, messages, temperature=0.7, max_tokens=500):
        """
        Mode chat avec historique des messages
        
        Args:
            messages: Liste de dictionnaires [{"role": "user", "content": "..."}]
            temperature: Créativité (0-1)
            max_tokens: Nombre max de tokens
        
        Returns:
            str: Réponse générée
        """
        if not self.available:
            return None
        
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            
            response = requests.post(
                self.chat_url,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('message', {}).get('content', '').strip()
            else:
                print(f"❌ Erreur LLM chat: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Erreur LLM chat: {e}")
            return None
    
    def enrich_response(self, question, data, intent):
        """
        Enrichit les données brutes avec une réponse en langage naturel
        
        Args:
            question: Question originale de l'utilisateur
            data: Données brutes (dict ou list)
            intent: Type de question détecté
        
        Returns:
            str: Réponse enrichie
        """
        if not self.available:
            # Fallback : réponse simple sans LLM
            return self._format_basic(question, data, intent)
        
        if not self.model_loaded:
            return self._format_basic(question, data, intent)
        
        # Construire le prompt système
        system_prompt = """Tu es un assistant hydrométrique expert de la Direction Générale des Ressources en Eau de Tunisie.

Instructions importantes :
1. Réponds UNIQUEMENT en français
2. Utilise les données fournies, ne les invente pas
3. Sois précis et professionnel
4. Structure ta réponse de manière claire
5. Utilise des emojis pertinents (📊 🌊 📈 🏆 💧)
6. Si les données sont manquantes, indique-le clairement
7. Ne donne pas d'informations qui ne sont pas dans les données"""

        # Formater les données pour le prompt
        if isinstance(data, list):
            if len(data) > 10:
                data_str = json.dumps(data[:10], ensure_ascii=False, indent=2, default=str) + "\n... (et d'autres résultats)"
            else:
                data_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        else:
            data_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        
        # Adapter le prompt selon l'intention
        intent_descriptions = {
            "max_debit": "L'utilisateur veut savoir quel gouvernorat a le débit maximum.",
            "avg_debit": "L'utilisateur veut connaître le débit moyen par gouvernorat.",
            "total_volume": "L'utilisateur veut connaître le volume total par gouvernorat.",
            "crues": "L'utilisateur veut des informations sur les crues.",
            "general_stats": "L'utilisateur veut des statistiques générales.",
            "station": "L'utilisateur veut des détails sur une station spécifique."
        }
        
        intent_desc = intent_descriptions.get(intent, "L'utilisateur pose une question sur les données hydrométriques.")
        
        prompt = f"""
{intent_desc}

Question de l'utilisateur : {question}

Données extraites de la base de données :
{data_str}

Réponds à la question de manière claire et professionnelle en utilisant les données fournies.
Si les données sont un tableau, présente-les de façon lisible.
Si c'est une liste, numérote les éléments.
Sois concis mais complet.
"""
        
        response = self.generate(prompt, system_prompt, temperature=0.3)
        
        if response:
            return response
        else:
            return self._format_basic(question, data, intent)
    
    def _format_basic(self, question, data, intent):
        """Formatage de base sans LLM"""
        if not data:
            return "Aucune donnée trouvée pour votre question."
        
        if isinstance(data, list):
            if len(data) == 0:
                return "Aucune donnée trouvée."
            
            if intent == "max_debit":
                row = data[0]
                return f"🏆 Le gouvernorat de **{row.get('gouvernorat', 'Inconnu')}** a le débit maximum avec **{row.get('debit_max', 0):.2f} m³/s** à la station **{row.get('station', 'Inconnue')}**."
            
            elif intent == "avg_debit":
                lines = ["📊 **Débit moyen par gouvernorat :**"]
                for row in data[:5]:
                    lines.append(f"  • {row.get('gouvernorat', 'Inconnu')}: {row.get('debit_moyen', 0):.2f} m³/s")
                return "\n".join(lines)
            
            elif intent == "total_volume":
                lines = ["💧 **Volume total par gouvernorat :**"]
                for row in data[:5]:
                    lines.append(f"  • {row.get('gouvernorat', 'Inconnu')}: {row.get('volume_total', 0):.2f} Hm³")
                return "\n".join(lines)
            
            elif intent == "crues":
                lines = ["🌊 **Crues les plus importantes :**"]
                for i, row in enumerate(data, 1):
                    lines.append(f"  {i}. {row.get('station', 'Inconnue')} ({row.get('gouvernorat', 'Inconnu')}) : {row.get('debit_max_m3s', 0):.2f} m³/s")
                return "\n".join(lines)
            
            elif intent == "general_stats":
                if len(data) > 0:
                    row = data[0]
                    return f"""📈 **Statistiques générales :**
  • {int(row.get('nb_stations', 0))} stations hydrométriques
  • {int(row.get('nb_gouvernorats', 0))} gouvernorats
  • Débit moyen global : {row.get('debit_moyen_global', 0):.2f} m³/s
  • Volume total global : {row.get('volume_total_global', 0):.2f} Hm³
  • Débit maximum global : {row.get('debit_max_global', 0):.2f} m³/s"""
            
            elif intent == "station":
                if len(data) > 0:
                    row = data[0]
                    return f"""📍 **Détails de la station :**
  • Nom : {row.get('station', 'Inconnu')}
  • Gouvernorat : {row.get('gouvernorat', 'Inconnu')}
  • Cours d'eau : {row.get('cours_eau', 'Inconnu')}
  • Débit moyen : {row.get('debit_moyen', 0):.2f} m³/s
  • Débit max : {row.get('debit_max_jour', 0):.2f} m³/s
  • Volume total : {row.get('volume_total_hm3', 0):.2f} Hm³
  • Année : {row.get('annee', 'Inconnue')}"""
            
            # Format générique
            return f"📊 Résultats : {len(data)} enregistrement(s) trouvé(s)"
        
        return str(data)
    
    def list_models(self):
        """Liste les modèles disponibles sur Ollama"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [m.get('name', '') for m in models]
            return []
        except:
            return []
    
    def pull_model(self, model_name):
        """Télécharge un modèle Ollama"""
        try:
            print(f"📥 Téléchargement du modèle {model_name}...")
            print("   Cela peut prendre plusieurs minutes...")
            
            response = requests.post(
                f"{self.host}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=600
            )
            
            if response.status_code == 200:
                # Afficher la progression
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if 'status' in data:
                                print(f"   {data['status']}")
                        except:
                            pass
                print(f"✅ Modèle {model_name} téléchargé")
                return True
            else:
                print(f"❌ Erreur: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
    
    def get_available_models(self):
        """Retourne la liste des modèles disponibles sur le serveur"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [m.get('name') for m in data.get('models', [])]
            return []
        except:
            return []


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    print("="*70)
    print("🧠 TEST DE L'AGENT LLM")
    print("="*70)
    
    # Initialiser l'agent
    llm = AgentLLM(model="mistral")
    
    print(f"\n📦 Modèle: {llm.model}")
    print(f"✅ Disponible: {llm.available}")
    print(f"✅ Modèle chargé: {llm.model_loaded}")
    
    if llm.available:
        print("\n📋 Modèles disponibles sur le serveur:")
        models = llm.get_available_models()
        for m in models:
            print(f"  - {m}")
        
        if not llm.model_loaded:
            print(f"\n⚠️ Le modèle {llm.model} n'est pas installé.")
            print(f"   Installez-le avec: ollama pull {llm.model}")
            print(f"   Ou utilisez l'un des modèles disponibles: {', '.join(models)}")
        else:
            # Test de génération simple
            print("\n🧪 Test de génération:")
            response = llm.generate("Dis 'Bonjour' en français")
            print(f"   Réponse: {response}")
            
            # Test d'enrichissement
            print("\n🧪 Test d'enrichissement:")
            test_data = [
                {"gouvernorat": "JENDOUBA", "debit_max": 92.54, "station": "BOU SALEM GP6"}
            ]
            result = llm.enrich_response(
                "Quel gouvernorat a le plus grand débit ?",
                test_data,
                "max_debit"
            )
            print(f"   Réponse enrichie:\n{result}")
    else:
        print("\n❌ Ollama n'est pas disponible")
        print("   Assurez-vous qu'Ollama est lancé:")
        print("   - Dans un terminal: ollama serve")
        print("   - Ou vérifiez que le service est démarré")