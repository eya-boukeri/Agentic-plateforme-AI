"""
src/agents/__init__.py
Import des agents
"""

from .agent_calcul import AgentCalcul
from .agent_edition import AgentEdition
from .agent_orchestrator import AgentOrchestrator

# Importer AgentRAG et AgentRAGOrchestrator
try:
    from .agent_rag import AgentRAG, AgentRAGOrchestrator
except ImportError as e:
    print(f"⚠️ Erreur import AgentRAG: {e}")
    # Définir des classes vides pour éviter les erreurs d'import
    class AgentRAG:
        def __init__(self, *args, **kwargs):
            print("⚠️ AgentRAG non disponible")
        def close(self):
            pass
    
    class AgentRAGOrchestrator:
        def __init__(self, *args, **kwargs):
            print("⚠️ AgentRAGOrchestrator non disponible")
        def close(self):
            pass
        def answer(self, question):
            return "AgentRAG non disponible. Veuillez vérifier l'installation."

__all__ = [
    'AgentCalcul',
    'AgentEdition',
    'AgentOrchestrator',
    'AgentRAG',
    'AgentRAGOrchestrator'
]