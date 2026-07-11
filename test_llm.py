# test_llm.py
import requests

def test_ollama():
    try:
        # Vérifier que le serveur répond
        response = requests.get("http://localhost:11434/api/tags")
        print("✅ Serveur Ollama OK")
        print(f"📦 Modèles disponibles : {response.json()}")
        
        # Tester un modèle
        payload = {
            "model": "mistral",
            "prompt": "Dis bonjour en français",
            "stream": False
        }
        response = requests.post("http://localhost:11434/api/generate", json=payload)
        print(f"🤖 Réponse : {response.json().get('response')}")
        
    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    test_ollama()