import sys
import os

# Forcer l'encodage utf-8 pour éviter les erreurs d'affichage dans la console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ajouter le chemin src pour pouvoir importer les modules
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from agents.agent_rag import AgentRAG

def main():
    print("="*60)
    print("[START] SCRIPT D'INDEXATION DES STATIONS DANS ZVEC")
    print("="*60)
    
    # Initialiser l'agent RAG (qui va lire db_config depuis PostgreSQL par défaut)
    rag = AgentRAG()
    
    if not rag.zvec_db:
        print("[ERROR] Impossible d'initialiser Zvec. Vérifiez que la bibliothèque est bien installée.")
        sys.exit(1)
        
    if not rag.llm:
        print("[ERROR] Impossible d'accéder au LLM (Ollama). Vérifiez qu'Ollama tourne et que le modèle nomic-embed-text est téléchargé.")
        sys.exit(1)
        
    try:
        # Lancer l'indexation
        success = rag.indexer_stations_dans_zvec()
        if success:
            print("[SUCCESS] Succès total de l'indexation !")
        else:
            print("[ERROR] Échec de l'indexation.")
    except Exception as e:
        print(f"[ERROR] Une erreur est survenue lors de l'indexation : {e}")
    finally:
        rag.close()

if __name__ == "__main__":
    main()
