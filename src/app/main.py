"""
src/app/main.py
Interface Streamlit - Génération et téléchargement de l'annuaire
"""

import streamlit as st
import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_edition import AgentEdition


def get_db_config():
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'hydrometry'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
    }


# Configuration de la page
st.set_page_config(
    page_title="Annuaire Hydrométrique DGRE",
    page_icon="🌊",
    layout="wide"
)

st.title("🌊 Plateforme Agentic AI - Annuaire Hydrométrique")
st.markdown("---")

# ============================================================
# BARRE LATÉRALE
# ============================================================

st.sidebar.header("📋 Paramètres")

# Sélection de l'année
annee = st.sidebar.selectbox("📅 Année", [2019, 2020, 2021, 2022, 2023, 2024], index=0)

# Sélection des stations
show_all = st.sidebar.checkbox("Toutes les stations", value=True)

# Bouton de génération
if st.sidebar.button("🚀 Générer l'annuaire", type="primary"):
    
    with st.spinner("⏳ Génération de l'annuaire en cours..."):
        
        # Créer une instance de l'Agent Édition (avec la vraie config .env,
        # sinon elle utilisait toujours localhost/postgres/postgres en dur)
        agent = AgentEdition(annee=annee, db_config=get_db_config())
        
        try:
            # Générer le PDF
            pdf_path = agent.generer_pdf()

            # Nombre reel de stations traitees (plus de valeur factice)
            try:
                nb_stations = len(agent.get_stations_with_gouvernorat())
            except Exception:
                nb_stations = "N/A"
            
            # Lire le fichier PDF
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()
            
            # Afficher le succès
            st.success(f"✅ Annuaire généré avec succès !")
            
            # Téléchargement
            st.download_button(
                label="📥 Télécharger le PDF",
                data=pdf_data,
                file_name=f"annuaire_hydrometrique_{annee}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            # Afficher un aperçu
            st.info(f"📄 Fichier : annuaire_hydrometrique_{annee}.pdf")
            st.metric("📊 Stations", nb_stations)
            st.metric("📅 Année", annee)
            
        except Exception as e:
            st.error(f"❌ Erreur : {e}")
        
        finally:
            agent.close()


# ============================================================
# INFORMATIONS
# ============================================================

st.markdown("---")
st.markdown("""
### 📖 À propos

Cette application permet de générer automatiquement l'annuaire hydrométrique 
de la DGRE pour une année donnée.

**Fonctionnalités :**
- 📄 Génération du PDF de l'annuaire
- 📊 Tableaux des débits journaliers (31×12)
- 📈 Hydrogrammes annuels
- 🌊 Caractéristiques des crues
- 📋 Statistiques hydrométriques

**Données :** PostgreSQL
**Année :** 2019 (exemple)
""")