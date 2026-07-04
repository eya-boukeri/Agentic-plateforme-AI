"""
src/agents/agent_edition.py
Agent Édition - Génération de l'annuaire hydrométrique PDF
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

class AgentEdition:
    def __init__(self, db_config=None, annee=None, output_dir="output/pdf/"):
        # Valeurs par défaut avec mot de passe simple
        self.db_host = 'localhost'
        self.db_port = 5432
        self.db_name = 'hydrometry'
        self.db_user = 'postgres'
        self.db_password = 'postgres'  # Mot de passe simple
        
        # Surcharger si config fournie
        if db_config:
            self.db_host = db_config.get('host', self.db_host)
            self.db_port = db_config.get('port', self.db_port)
            self.db_name = db_config.get('database', self.db_name)
            self.db_user = db_config.get('user', self.db_user)
            self.db_password = db_config.get('password', 'postgres')
        
        self.annee = annee or 2019
        self.output_dir = output_dir
        
        # Connexion avec mot de passe simple
        db_url = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        self.engine = create_engine(db_url)
        print(f"✅ Connexion PostgreSQL : {self.db_host}:{self.db_port}/{self.db_name}")
        
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs("output/graphs/", exist_ok=True)
    
    def close(self):
        if self.engine:
            self.engine.dispose()
            print("🔒 Connexion fermée")
    
    def get_stations(self):
        query = """
            SELECT DISTINCT 
                s."Id_Station" as code_station,
                s."Nom" as nom
            FROM stations_base s
            INNER JOIN statistiques_annuelles st ON s."Id_Station" = st.code_station
            WHERE st.annee = %s
            ORDER BY s."Nom"
        """
        return pd.read_sql(query, self.engine, params=(self.annee,))
    
    def get_statistiques(self, code_station):
        query = """
            SELECT 
                debit_moyen,
                debit_max_jour,
                date_max_jour,
                debit_min_jour,
                date_min_jour,
                debit_max_inst,
                date_max_inst,
                debit_min_inst,
                date_min_inst,
                volume_total_hm3,
                lame_ecoulee_mm,
                dc1, dc3, dc6, dc9, dc11, dce, dcc,
                q10, q50, q90, q95,
                source
            FROM statistiques_annuelles
            WHERE code_station = %s AND annee = %s
        """
        return pd.read_sql(query, self.engine, params=(code_station, self.annee))
    
    def get_debits_journaliers(self, code_station):
        query = """
            SELECT jour, debit_moyen
            FROM debits_journaliers
            WHERE code_station = %s AND annee = %s
            ORDER BY jour
        """
        return pd.read_sql(query, self.engine, params=(code_station, self.annee))
    
    def generer_hydrogramme_annuel(self, df_debits, code_station, nom_station):
        if df_debits.empty:
            return None
        
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(df_debits['jour'], df_debits['debit_moyen'], color='#1a5276', linewidth=1.5)
        
        moyenne = df_debits['debit_moyen'].mean()
        ax.axhline(y=moyenne, color='#27ae60', linestyle='--', label=f'Moyenne: {moyenne:.2f} m³/s')
        
        ax.set_xlabel('Mois')
        ax.set_ylabel('Débit (m³/s)')
        ax.set_title(f'Hydrogramme annuel - {nom_station} ({self.annee})')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        filename = f"output/graphs/hydrogramme_{code_station}_{self.annee}.png"
        fig.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close(fig)
        return filename
    
    def generer_pdf(self):
        print("\n📄 GÉNÉRATION DE L'ANNUAIRE PDF")
        
        stations = self.get_stations()
        print(f"🏛️ {len(stations)} stations à traiter")
        
        filename = os.path.join(self.output_dir, f"annuaire_hydrometrique_{self.annee}.pdf")
        doc = SimpleDocTemplate(filename, pagesize=A4, 
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='CustomTitle', parent=styles['Title'], 
                                  fontSize=18, alignment=TA_CENTER, spaceAfter=30))
        styles.add(ParagraphStyle(name='CustomHeading', parent=styles['Heading2'], 
                                  fontSize=14, spaceBefore=20, spaceAfter=10))
        styles.add(ParagraphStyle(name='CustomBody', parent=styles['Normal'], 
                                  fontSize=10, spaceAfter=6))
        
        elements = []
        
        # Page de garde
        elements.append(Paragraph("RÉPUBLIQUE TUNISIENNE", styles['CustomTitle']))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph("Ministère de l'Agriculture, des Ressources Hydrauliques et de la Pêche", styles['CustomTitle']))
        elements.append(Paragraph("Direction Générale des Ressources en Eau", styles['CustomTitle']))
        elements.append(Spacer(1, 2*cm))
        elements.append(Paragraph(f"ANNUAIRE HYDROMÉTRIQUE {self.annee}", styles['CustomTitle']))
        elements.append(Spacer(1, 1*cm))
        elements.append(Paragraph(f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['CustomBody']))
        elements.append(PageBreak())
        
        # Introduction
        elements.append(Paragraph("INTRODUCTION", styles['CustomHeading']))
        elements.append(Paragraph(
            f"Le présent annuaire présente les résultats des observations hydrométriques "
            f"de l'année hydrologique {self.annee}. Il a été généré automatiquement par la "
            f"plateforme Agentic AI de la DGRE.",
            styles['CustomBody']
        ))
        elements.append(PageBreak())
        
        # Traiter chaque station
        for _, station in stations.iterrows():
            code = station['code_station']
            nom = station['nom']
            
            print(f"📊 {nom} ({code})")
            
            stats = self.get_statistiques(code)
            debits = self.get_debits_journaliers(code)
            
            if stats.empty:
                continue
            
            row = stats.iloc[0]
            
            elements.append(Paragraph(f"Station : {nom} - {code}", styles['CustomHeading']))
            elements.append(Spacer(1, 0.5*cm))
            
            elements.append(Paragraph("Caractéristiques hydrométriques", styles['CustomHeading']))
            elements.append(Paragraph(f"Débit moyen annuel : {row['debit_moyen']:.3f} m³/s", styles['CustomBody']))
            elements.append(Paragraph(f"Débit max : {row['debit_max_jour']:.3f} m³/s ({row['date_max_jour']})", styles['CustomBody']))
            elements.append(Paragraph(f"Volume total : {row['volume_total_hm3']:.2f} Hm³", styles['CustomBody']))
            
            if not debits.empty:
                img_path = self.generer_hydrogramme_annuel(debits, code, nom)
                if img_path:
                    try:
                        img = Image(img_path, width=16*cm, height=7*cm)
                        elements.append(img)
                    except:
                        pass
            
            elements.append(PageBreak())
        
        doc.build(elements)
        print(f"✅ PDF généré : {filename}")
        return filename

if __name__ == "__main__":
    agent = AgentEdition(annee=2019)
    try:
        agent.generer_pdf()
    finally:
        agent.close()