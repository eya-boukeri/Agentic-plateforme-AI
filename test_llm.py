# test_llm.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_ollama():
    try:
        host = os.getenv("LLM_HOST", "http://localhost:11434")
        model = os.getenv("LLM_MODEL", "hydrometrie")
        
        # Vérifier que le serveur répond
        response = requests.get(f"{host}/api/tags", timeout=5)
        print("✅ Serveur Ollama OK")
        models = [m.get("name") for m in response.json().get("models", [])]
        print(f"📦 Modèles disponibles : {models}")
        
        # Tester le modèle hydrometrie
        print(f"🤖 Test du modèle '{model}'...")
        payload = {
            "model": model,
            "prompt": "Dis bonjour en tant qu'assistant de la DGRE en une phrase courte.",
            "stream": False,
            "options": {"num_predict": 50}
        }
        response = requests.post(f"{host}/api/generate", json=payload, timeout=180)
        print(f"🤖 Réponse : {response.json().get('response')}")
        
    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    test_ollama()