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
from dotenv import load_dotenv

load_dotenv()  # s'assure que LLM_MODEL / LLM_HOST sont lus même si ce module
                # est importé/instancié avant que main.py n'appelle load_dotenv()

class AgentLLM:
    """
    Agent LLM utilisant Ollama pour générer des réponses en langage naturel
    Modèle par défaut : hydrometrie (modèle fine-tuné pour l'hydrométrie tunisienne)
    Modèles compatibles : hydrometrie, mistral, llama3, phi3, gemma
    """
    
    def __init__(self, model=None, host=None):
        """
        Initialise l'agent LLM avec un modèle Ollama

        Args:
            model: Nom du modèle Ollama (hydrometrie, mistral, llama3, phi3, etc.)
                   Si non fourni, lit LLM_MODEL dans .env (fallback: "hydrometrie")
            host: URL du serveur Ollama
                   Si non fourni, lit LLM_HOST dans .env (fallback: "http://localhost:11434")
        """
        # ⚠️ CORRECTION : "mistral" → "hydrometrie"
        self.model = model or os.getenv("LLM_MODEL", "hydrometrie")
        self.host = host or os.getenv("LLM_HOST", "http://localhost:11434")
        try:
            self.timeout = int(os.getenv("LLM_TIMEOUT", "30"))
        except (ValueError, TypeError):
            self.timeout = 30
        self.api_url = f"{self.host}/api/generate"
        self.chat_url = f"{self.host}/api/chat"
        self.available = False
        self.model_loaded = False
        self.last_check = None
        self.available_models = []
        self.status_message = "Non vérifié"
        self.last_error = None
        
        # Vérifier la disponibilité d'Ollama
        self._check_availability()
    
    def _check_availability(self):
        """Vérifie si Ollama est disponible (avec détection automatique Docker -> hôte)"""
        self.last_check = datetime.utcnow().isoformat() + "Z"

        # Si localhost échoue (courant sous Docker), tenter host.docker.internal
        hosts_a_tester = [self.host]
        if "localhost" in self.host or "127.0.0.1" in self.host:
            hosts_a_tester.append("http://host.docker.internal:11434")
        elif "host.docker.internal" in self.host:
            hosts_a_tester.append("http://localhost:11434")

        derniere_erreur = None
        for h in hosts_a_tester:
            try:
                response = requests.get(f"{h}/api/tags", timeout=5)
                if response.status_code == 200:
                    # Mettre à jour l'hôte effectif joignable
                    self.host = h
                    self.api_url = f"{self.host}/api/generate"
                    self.chat_url = f"{self.host}/api/chat"

                    models = response.json().get('models', [])
                    model_names = [m.get('name', '') for m in models]
                    self.available_models = model_names

                    # Vérifier si le modèle demandé est disponible
                    if any(self.model in name for name in model_names):
                        self.available = True
                        self.model_loaded = True
                        self.status_message = f"Modèle {self.model} chargé"
                        print(f"✅ LLM disponible : {self.model} (sur {self.host})")
                    else:
                        self.available = True
                        self.model_loaded = False
                        self.status_message = f"Modèle {self.model} absent"
                        print(f"⚠️ Modèle {self.model} non trouvé sur {self.host}.")
                        print(f"   Modèles disponibles : {', '.join(model_names)}")
                    return
                else:
                    derniere_erreur = f"Ollama a renvoyé {response.status_code}"
            except Exception as e:
                derniere_erreur = f"Erreur de connexion: {e}"

        self.available = False
        self.model_loaded = False
        self.status_message = derniere_erreur or "Ollama injoignable"
        print(f"⚠️ Erreur de connexion à Ollama : {self.status_message}")

    def get_status(self):
        """Retourne un état simple de disponibilité pour l'UI."""
        return {
            "available": self.available,
            "model_loaded": self.model_loaded,
            "model": self.model,
            "host": self.host,
            "available_models": list(self.available_models),
            "last_check": self.last_check,
            "status_message": self.status_message,
        }
    
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
        
        self.last_error = None
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
                "keep_alive": "30m",  # garde le modèle chargé en mémoire entre les appels
                                       # (évite de recharger ~7B à chaque question)
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                print(f"❌ Erreur LLM: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            self.last_error = 'timeout'
            print("❌ Erreur LLM: Timeout - Le modèle met trop de temps à répondre")
            return None
        except Exception as e:
            self.last_error = str(e)
            print(f"❌ Erreur LLM: {e}")
            return None
    
    def chat(self, messages, temperature=0.7, max_tokens=500, tools=None):
        """
        Mode chat avec historique des messages, avec support optionnel du
        function/tool calling natif d'Ollama (transmis tel quel au modele,
        qui repond soit en texte normal, soit avec un appel d'outil selon
        ce qu'il a appris a l'entrainement).

        Args:
            messages: Liste de dictionnaires [{"role": "user", "content": "..."}]
            temperature: Créativité (0-1)
            max_tokens: Nombre max de tokens
            tools: Liste optionnelle de definitions d'outils (meme format
                   que celui utilise pour le fine-tuning : name/description/
                   parameters). Normalisé automatiquement vers le format
                   type=function attendu par l'API /api/chat d'Ollama.

        Returns:
            str: Réponse générée (texte brut - peut contenir un appel
                 d'outil ou du code selon l'entrainement du modele ;
                 voir agent_orchestrator.py pour l'extraction/le routage)
        """
        if not self.available:
            return None
        
        self.last_error = None
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            if tools:
                # Normaliser les outils au format fonction standardisé attendu par Ollama /api/chat
                formatted_tools = []
                for tool in tools:
                    if isinstance(tool, dict):
                        if tool.get("type") == "function" and "function" in tool:
                            formatted_tools.append(tool)
                        elif "name" in tool:
                            formatted_tools.append({
                                "type": "function",
                                "function": tool
                            })
                        else:
                            formatted_tools.append(tool)
                payload["tools"] = formatted_tools
            
            response = requests.post(
                self.chat_url,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                message = result.get('message', {})
                # Si le serveur/modele renvoie un appel d'outil structure
                # (certains backends Ollama recents le font pour les
                # modeles compatibles), on le reserialise en texte pour
                # rester coherent avec le format <tool_call> attendu par
                # agent_orchestrator.py - sinon on renvoie simplement le
                # contenu texte (cas le plus courant avec notre modele
                # fine-tune, qui produit deja le JSON dans le texte).
                if message.get('tool_calls'):
                    appel = message['tool_calls'][0].get('function', {})
                    args = appel.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            pass
                    return (
                        "<tool_call>\n"
                        + json.dumps({"name": appel.get("name"), "arguments": args}, ensure_ascii=False)
                        + "\n</tool_call>"
                    )
                return message.get('content', '').strip()
            else:
                print(f"❌ Erreur LLM chat: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            self.last_error = 'timeout'
            print(f"❌ Erreur LLM chat: Timeout dépassé ({self.timeout}s)")
            return None
        except Exception as e:
            self.last_error = str(e)
            print(f"❌ Erreur LLM chat: {e}")
            return None
    
    def get_embedding(self, text, model=None):
        """
        Génère un embedding vectoriel pour le texte fourni.
        
        Args:
            text (str): Le texte à vectoriser
            model (str, optional): Le modèle d'embedding à utiliser (défaut: "nomic-embed-text")
            
        Returns:
            list: Une liste de floats représentant le vecteur, ou None en cas d'erreur
        """
        if not self.available:
            return None
            
        embed_model = model or "nomic-embed-text"
        url = f"{self.host}/api/embeddings"
        
        try:
            payload = {
                "model": embed_model,
                "prompt": text
            }
            response = requests.post(url, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json().get("embedding")
            else:
                # Essayer avec le nouvel endpoint /api/embed au cas où
                url_new = f"{self.host}/api/embed"
                payload_new = {
                    "model": embed_model,
                    "input": text
                }
                response_new = requests.post(url_new, json=payload_new, timeout=60)
                if response_new.status_code == 200:
                    embeddings = response_new.json().get("embeddings")
                    if embeddings and len(embeddings) > 0:
                        return embeddings[0]
                print(f"❌ Erreur lors de la génération de l'embedding: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ Exception lors de la génération de l'embedding: {e}")
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
        
        # ⚠️ CORRECTION : Prompt système adapté au modèle hydrometrie
        system_prompt = """Tu es l'assistant agentic de la DGRE pour l'annuaire hydrométrique de la Tunisie.
Tu réponds aux questions sur les données hydrométriques (débits, crues, statistiques, stations).
Tu es précis, technique mais accessible.
Réponds toujours en français.
Si tu ne connais pas la réponse, dis-le honnêtement."""

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
        
        # ⚠️ CORRECTION : Utiliser chat() au lieu de generate() pour le modèle hydrometrie
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        response = self.chat(messages, temperature=0.3, max_tokens=300)
        
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
    llm = AgentLLM()  # lit LLM_MODEL depuis .env (fallback: hydrometrie)
    
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
            
            # Test de chat
            print("\n🧪 Test de chat:")
            messages = [
                {"role": "system", "content": "Tu es un expert en hydrométrie."},
                {"role": "user", "content": "Qu'est-ce qu'une station hydrométrique ?"}
            ]
            response = llm.chat(messages, max_tokens=200)
            print(f"   Réponse: {response[:200]}..." if response else "   Pas de réponse")
            
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