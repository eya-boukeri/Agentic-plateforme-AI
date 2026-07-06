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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

class AgentEdition:
    def __init__(self, db_config=None, annee=None, output_dir="output/pdf/"):
    
        self.db_host = 'localhost'
        self.db_port = 5432
        self.db_name = 'hydrometry'
        self.db_user = 'postgres'
        self.db_password = 'postgres'  
        
        # Surcharger si config fournie
        if db_config:
            self.db_host = db_config.get('host', self.db_host)
            self.db_port = db_config.get('port', self.db_port)
            self.db_name = db_config.get('database', self.db_name)
            self.db_user = db_config.get('user', self.db_user)
            self.db_password = db_config.get('password', 'postgres')
        
        try:
            self.annee = int(annee) if annee is not None else 2019
        except (TypeError, ValueError):
            self.annee = 2019
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

    def get_station_details(self, code_station):
        query = """
            SELECT *
            FROM stations_base
            WHERE "Id_Station" = %s
            LIMIT 1
        """
        df = pd.read_sql(query, self.engine, params=(code_station,))
        return df.iloc[0].to_dict() if not df.empty else {}
    
    def get_debits_journaliers(self, code_station):
        query = """
            SELECT
                "Date" AS date_heure,
                "Valeur" AS debit_m3s
            FROM debits
            WHERE "Id_Station" = %s
              AND "Date" >= %s
              AND "Date" < %s
            ORDER BY "Date"
        """
        start_date = f"{self.annee}-09-01"
        end_date = f"{self.annee + 1}-09-01"
        df = pd.read_sql(query, self.engine, params=(code_station, start_date, end_date))

        if df.empty:
            return pd.DataFrame(columns=["jour", "debit_moyen"])

        df["date_heure"] = pd.to_datetime(df["date_heure"], errors="coerce")
        df["debit_m3s"] = pd.to_numeric(df["debit_m3s"], errors="coerce")
        df = df.dropna(subset=["date_heure", "debit_m3s"])
        df["jour"] = df["date_heure"].dt.normalize()

        journalier = (
            df.groupby("jour", as_index=False)["debit_m3s"]
            .mean()
            .rename(columns={"debit_m3s": "debit_moyen"})
            .sort_values("jour")
        )

        return journalier

    def get_crues(self, code_station):
        query = """
            SELECT
                date_debut,
                date_fin,
                temps_base_min,
                temps_montee_min,
                debit_debut,
                debit_fin,
                debit_max_m3s,
                volume_ecoule_hm3,
                volume_ruiss_hm3,
                lame_ecoulee_mm,
                lame_ruiss_mm
            FROM crues
            WHERE code_station = %s AND annee = %s
            ORDER BY date_debut
        """
        return pd.read_sql(query, self.engine, params=(code_station, self.annee))

    def get_etalonnage(self, code_station):
        query = """
            SELECT hauteur_cm, debit_m3s, date_validite, description
            FROM courbes_tarage
            WHERE code_station = %s
            ORDER BY date_validite NULLS LAST, hauteur_cm
        """
        try:
            return pd.read_sql(query, self.engine, params=(code_station,))
        except Exception:
            return pd.DataFrame()

    def get_tableau_debits_moyens_journaliers(self, code_station):
        df_debits = self.get_debits_journaliers(code_station)

        mois_order = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
        mois_labels = [
            "Sep", "Oct", "Nov", "Déc", "Jan", "Fév",
            "Mar", "Avr", "Mai", "Juin", "Juil", "Août"
        ]

        if df_debits.empty:
            tableau_vide = pd.DataFrame(index=range(1, 32), columns=mois_labels)
            tableau_vide.index.name = "Jour"
            return tableau_vide

        df = df_debits.copy()
        df["jour"] = pd.to_datetime(df["jour"])
        df["jour_num"] = df["jour"].dt.day
        df["mois_num"] = df["jour"].dt.month
        df["debit_moyen"] = pd.to_numeric(df["debit_moyen"], errors="coerce")

        pivot = df.pivot_table(
            index="jour_num",
            columns="mois_num",
            values="debit_moyen",
            aggfunc="mean"
        )

        pivot = pivot.reindex(index=range(1, 32), columns=mois_order)
        pivot.columns = mois_labels
        pivot.index.name = "Jour"
        return pivot

    def _format_value(self, value, decimals=2):
        if pd.isna(value):
            return ""

        if isinstance(value, (pd.Timestamp, datetime)):
            return value.strftime("%d/%m/%Y")

        if isinstance(value, (float, np.floating)):
            return f"{value:.{decimals}f}".replace(".", ",")

        if isinstance(value, (int, np.integer)):
            return str(value)

        if isinstance(value, (np.int64, np.int32, np.int16, np.int8)):
            return str(int(value))

        return str(value)

    def dataframe_to_table(self, df, font_size=6, header_bg=colors.HexColor("#1a5276")):
        if df is None or df.empty:
            return None

        data = [list(df.columns)]
        for _, row in df.iterrows():
            data.append([self._format_value(value) for value in row.tolist()])

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEADING", (0, 0), (-1, -1), font_size + 1),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
        ]))
        return table

    def _pick_value(self, record, candidates, default=""):
        normalized = {str(key).lower().replace(" ", "_").replace("-", "_"): value for key, value in record.items()}
        for candidate in candidates:
            key = candidate.lower().replace(" ", "_").replace("-", "_")
            if key in normalized and pd.notna(normalized[key]):
                return normalized[key]
        return default

    def _station_info_rows(self, code_station, nom_station):
        details = self.get_station_details(code_station)

        return [
            ["Station", f"{nom_station} - {code_station}"],
            ["Date de mise en service", self._pick_value(details, ["Date mise en service", "DateMiseEnService", "Date_mise_en_service"])],
            ["Secteur hydrographique", self._pick_value(details, ["Secteur hydrographique", "Secteur_Hydrographique", "Zone"])],
            ["Sous-secteur hydrographique", self._pick_value(details, ["Sous-Secteur hydrographique", "SousZone", "Sous_secteur"])],
            ["Cours d'eau", self._pick_value(details, ["Cours d'eau", "Cours_eau", "CoursEau"])],
            ["Superficie bassin", self._pick_value(details, ["Superficie", "Superficie_Bassin", "superficie"])],
            ["Coordonnées UTM", f"X: {self._pick_value(details, ['X_UTM', 'x_utm'])} / Y: {self._pick_value(details, ['Y_UTM', 'y_utm'])}"],
            ["Altitude", self._pick_value(details, ["Altitude", "altitude"])],
            ["Crue maximale observée", self._pick_value(details, ["Crue maximale Observée", "Crue_maximale_observee", "SeuilCrue"])],
            ["Dispositif de jaugeage", self._pick_value(details, ["Dispositif de jaugeage", "Equipement", "dispositif_jaugeage"])],
        ]

    def _station_info_table(self, code_station, nom_station, font_size=6):
        details = self.get_station_details(code_station)

        def make_line(label, value, with_check=True):
            prefix = "✓ " if with_check else ""
            formatted_value = self._format_value(value, decimals=3).replace("\n", "<br/>")
            return Paragraph(
                f'<font size="{font_size}"><b>{prefix}{label}:</b> {formatted_value}</font>',
                getSampleStyleSheet()["BodyText"]
            )

        def make_title(text):
            return Paragraph(f'<font size="{font_size + 0.5}"><b>{text}</b></font>', getSampleStyleSheet()["BodyText"])

        left_rows = [
            [make_title("Caractéristiques de la station:")],
            [make_line("Date de mise en service", self._pick_value(details, ["Date mise en service", "DateMiseEnService", "Date_mise_en_service"]))],
            [make_line("Secteur hydrographique", self._pick_value(details, ["Secteur hydrographique", "Secteur_Hydrographique", "Zone"]))],
            [make_line("Sous-Secteur hydrographique", self._pick_value(details, ["Sous-Secteur hydrographique", "SousZone", "Sous_secteur"]))],
            [make_line("Cours d'eau", self._pick_value(details, ["Cours d'eau", "Cours_eau", "CoursEau"]))],
            [make_line("Superficie Bassin", self._pick_value(details, ["Superficie", "Superficie_Bassin", "superficie"]))],
            [make_title("Equipement de la station:")],
            [make_line("Radar RLS + Duosens", self._pick_value(details, ["Equipement", "dispositif_jaugeage"]), with_check=True)],
            [make_line("Echelle", self._pick_value(details, ["Echelle", "Echelle_Station", "echelle"]), with_check=True)],
        ]

        right_rows = [
            [make_title(" ")],
            [make_line("Coordonnées (UTM en m) X", self._pick_value(details, ["X_UTM", "x_utm"]))],
            [make_line("Coordonnées (UTM en m) Y", self._pick_value(details, ["Y_UTM", "y_utm"]))],
            [make_line("Altitude approximative", self._pick_value(details, ["Altitude", "altitude"]))],
            [make_line("Crue maximale Observée", f"{self._pick_value(details, ['Crue maximale Observée', 'Crue_maximale_observee', 'SeuilCrue'])}\nle 28 Février 2012")],
            [make_title("Dispositif de Jaugeage:")],
            [make_line("Crue", "saumnon de 50 kg et treuil")],
            [make_line("Etiage", "à gué")],
        ]

        left_table = Table(left_rows, colWidths=[8.0*cm])
        left_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))

        right_table = Table(right_rows, colWidths=[8.1*cm])
        right_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))

        table = Table(
            [[Paragraph("<font size='7'><b>1/Fiche de renseignements de la station: Transmission en temps réel</b></font>", getSampleStyleSheet()["BodyText"])], [Table([[left_table, right_table]], colWidths=[8.0*cm, 8.1*cm])]],
            colWidths=[16.1*cm]
        )
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.0, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return table

    def _daily_table_with_summary(self, tableau_debits):
        if tableau_debits is None or tableau_debits.empty:
            return None

        display = tableau_debits.reset_index().copy()
        display["Jour"] = pd.to_numeric(display["Jour"], errors="coerce").fillna(0).astype(int)

        numeric_columns = [col for col in display.columns if col != "Jour"]
        summary_rows = []

        moy_row = {"Jour": "Moy"}
        min_row = {"Jour": "Min"}
        max_row = {"Jour": "Max"}

        for column in numeric_columns:
            values = pd.to_numeric(display[column], errors="coerce")
            moy_row[column] = values.mean()
            min_row[column] = values.min()
            max_row[column] = values.max()

        summary_rows.extend([moy_row, min_row, max_row])
        display = pd.concat([display, pd.DataFrame(summary_rows)], ignore_index=True)
        return display

    def _section_table(self, title, rows, col_widths=(5.3*cm, 10.1*cm), font_size=7):
        data = [[Paragraph(f"<b>{title}</b>", getSampleStyleSheet()["BodyText"]), ""]]
        for label, value in rows:
            data.append([label, self._format_value(value, decimals=3) if isinstance(value, (float, np.floating)) else self._format_value(value)])

        table = Table(data, colWidths=list(col_widths), repeatRows=1)
        table.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return table

    def _plot_courbe_etalonnage(self, code_station):
        df = self.get_etalonnage(code_station)
        if df.empty:
            return None

        data = df.copy()
        data["hauteur_cm"] = pd.to_numeric(data["hauteur_cm"], errors="coerce")
        data["debit_m3s"] = pd.to_numeric(data["debit_m3s"], errors="coerce")
        data = data.dropna(subset=["hauteur_cm", "debit_m3s"]).sort_values("hauteur_cm")
        if data.empty:
            return None

        fig, ax = plt.subplots(figsize=(4.8, 3.1))
        ax.plot(data["hauteur_cm"], data["debit_m3s"], color="#1a5276", marker="o", linewidth=1.2, markersize=2.5)
        ax.set_title("Courbe d'étalonnage", fontsize=8)
        ax.set_xlabel("Hauteur (cm)", fontsize=7)
        ax.set_ylabel("Débit (m³/s)", fontsize=7)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=6)
        plt.tight_layout()

        filename = f"output/graphs/etalonnage_{code_station}_{self.annee}.png"
        fig.savefig(filename, dpi=250, bbox_inches="tight")
        plt.close(fig)
        return filename

    def _plot_hydrogramme_crue(self, debits, stats, code_station):
        if debits.empty or not stats:
            return None

        date_max = pd.to_datetime(stats.get("date_max_jour"), errors="coerce")
        if pd.isna(date_max):
            return None

        data = debits.copy()
        data["jour"] = pd.to_datetime(data["jour"])
        window = data[(data["jour"] >= date_max - pd.Timedelta(days=10)) & (data["jour"] <= date_max + pd.Timedelta(days=10))]
        if window.empty:
            window = data

        fig, ax = plt.subplots(figsize=(4.8, 3.1))
        ax.plot(window["jour"], window["debit_moyen"], color="#2e5aac", linewidth=1.2)
        ax.axvline(date_max, color="#c0392b", linestyle="--", linewidth=1)
        ax.set_title("Hydrogramme de crue", fontsize=8)
        ax.set_xlabel("Date", fontsize=7)
        ax.set_ylabel("Débit (m³/s)", fontsize=7)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=6)
        fig.autofmt_xdate(rotation=25)
        plt.tight_layout()

        filename = f"output/graphs/crue_{code_station}_{self.annee}.png"
        fig.savefig(filename, dpi=250, bbox_inches="tight")
        plt.close(fig)
        return filename

    def _safe_image(self, path, width, height):
        if not path or not os.path.exists(path):
            return None
        return Image(path, width=width, height=height)

    def _crues_table(self, crues_df):
        if crues_df is None or crues_df.empty:
            return None

        columns = [
            ("Date Début", "date_debut"),
            ("Date Fin", "date_fin"),
            ("Tps_Base\n(mn)", "temps_base_min"),
            ("Tps_Montée\n(mn)", "temps_montee_min"),
            ("Val.Début\n(m³/s)", "debit_debut"),
            ("Val.Fin\n(m³/s)", "debit_fin"),
            ("Val_Maxi\n(m³/s)", "debit_max_m3s"),
            ("V_Ecou\n(Hm³)", "volume_ecoule_hm3"),
            ("V_Ruiss\n(Hm³)", "volume_ruiss_hm3"),
            ("Q_Ecou\n(m³/s)", "debit_debut"),
            ("Q_Ruiss\n(m³/s)", "debit_fin"),
            ("L_Ecou\n(mm)", "lame_ecoulee_mm"),
            ("L_Ruiss\n(mm)", "lame_ruiss_mm"),
        ]

        data = [[Paragraph(f"<b>{label}</b>", getSampleStyleSheet()["BodyText"]) for label, _ in columns]]

        for _, row in crues_df.iterrows():
            row_values = []
            for header, key in columns:
                value = row.get(key, "")
                if key in ("date_debut", "date_fin"):
                    if pd.notna(value):
                        timestamp = pd.to_datetime(value)
                        value = f"{timestamp.strftime('%d/%m/%Y')}<br/>{timestamp.strftime('%H:%M')}"
                    else:
                        value = ""
                elif isinstance(value, (float, np.floating)):
                    if key in ("volume_ecoule_hm3", "volume_ruiss_hm3"):
                        value = f"{value:.4f}".replace(".", ",")
                    elif key in ("lame_ecoulee_mm", "lame_ruiss_mm"):
                        value = f"{value:.1f}".replace(".", ",")
                    else:
                        value = f"{value:.2f}".replace(".", ",")
                elif isinstance(value, (int, np.integer)):
                    value = str(int(value))
                else:
                    value = self._format_value(value)

                row_values.append(Paragraph(f"<font size='4.4'>{value}</font>", getSampleStyleSheet()["BodyText"]))
            data.append(row_values)

        width = 16.1 * cm
        col_width = width / len(columns)
        table = Table(data, colWidths=[col_width] * len(columns), repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 4.4),
            ("LEADING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return table

    def build_station_report_data(self, code_station, nom_station):
        stats = self.get_statistiques(code_station)
        debits = self.get_debits_journaliers(code_station)
        crues = self.get_crues(code_station)
        tableau_debits = self.get_tableau_debits_moyens_journaliers(code_station)
        etalonnage_path = self._plot_courbe_etalonnage(code_station)

        stats_row = stats.iloc[0].to_dict() if not stats.empty else {}
        hydrogramme_path = None
        hydrogramme_crue_path = None

        if not debits.empty:
            hydrogramme_path = self.generer_hydrogramme_annuel(debits, code_station, nom_station)
            hydrogramme_crue_path = self._plot_hydrogramme_crue(debits, stats_row, code_station)

        return {
            "code_station": code_station,
            "nom_station": nom_station,
            "caracteristiques_hydrometriques": stats_row,
            "debits_journaliers": debits,
            "tableau_debits_moyens_journaliers": tableau_debits,
            "crues": crues,
            "etalonnage_path": etalonnage_path,
            "hydrogramme_crue_path": hydrogramme_crue_path,
            "hydrogramme_path": hydrogramme_path,
        }

    def generer_df_annuaire(self):
        stations = self.get_stations()
        rapports = []

        for index, station in stations.iterrows():
            code = station["code_station"]
            nom = station["nom"]
            stats = self.get_statistiques(code)

            if stats.empty:
                continue

            rapports.append({
                "code_station": code,
                "nom_station": nom,
                "caracteristiques_hydrometriques": stats.iloc[0].to_dict(),
                "tableau_debits_moyens_journaliers": self.get_tableau_debits_moyens_journaliers(code),
                "crues": self.get_crues(code),
            })

        return pd.DataFrame(rapports)
    
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
        styles.add(ParagraphStyle(name='SectionTitle', parent=styles['Normal'], fontSize=9, leading=10, spaceAfter=2))
        
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
        for position, (_, station) in enumerate(stations.iterrows()):
            code = station['code_station']
            nom = station['nom']
            
            print(f"📊 {nom} ({code})")
            
            report_data = self.build_station_report_data(code, nom)
            stats = report_data["caracteristiques_hydrometriques"]
            tableau_debits = report_data["tableau_debits_moyens_journaliers"]
            crues = report_data["crues"]
            etalonnage_path = report_data["etalonnage_path"]
            hydrogramme_crue_path = report_data["hydrogramme_crue_path"]
            img_path = report_data["hydrogramme_path"]
            
            if not stats:
                continue
            
            station_title = Paragraph(f"<b>Station : {nom} - {code}</b>", styles['CustomHeading'])
            section_1 = self._station_info_table(code, nom, font_size=6)

            tableau_debits_display = self._daily_table_with_summary(tableau_debits)
            section_3_table = self.dataframe_to_table(tableau_debits_display, font_size=4.8)
            if section_3_table is None:
                section_3_table = Paragraph("Tableau des débits moyens journaliers non disponible", styles['SectionTitle'])
            section_3 = Table([[Paragraph("<b>3/ Débits moyens journaliers :</b>", styles['SectionTitle'])], [section_3_table]], colWidths=[10.8*cm])
            section_3.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

            etalonnage_elements = [Paragraph("<b>2/ Etalonnage de la station :</b>", styles['SectionTitle']), Paragraph("Valide du 01/01/2012 jusqu'à nos jours", styles['SectionTitle'])]
            if etalonnage_path:
                etalonnage_img = self._safe_image(etalonnage_path, width=5.8*cm, height=4.2*cm)
                if etalonnage_img:
                    etalonnage_elements.append(etalonnage_img)
            else:
                etalonnage_elements.append(Paragraph("Courbe d'étalonnage non disponible", styles['SectionTitle']))
            section_2 = Table([[item] for item in etalonnage_elements], colWidths=[5.9*cm])
            section_2.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

            top_panel = Table([[section_2, section_3]], colWidths=[6.2*cm, 10.1*cm], hAlign="LEFT")
            top_panel.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

            caracs_rows = [
                ["Débit moyen annuel", f"{stats['debit_moyen']:.2f} m³/s"],
                ["Volume Total écoulé à la station", f"{stats['volume_total_hm3']:.2f} Hm³"],
                ["Hauteur de la lame d'eau écoulée", f"{stats['lame_ecoulee_mm']:.1f} mm" if pd.notna(stats.get('lame_ecoulee_mm')) else ""],
            ]
            section_4 = self._section_table("4/Caractéristiques hydrométriques de la station:", caracs_rows, col_widths=(7.2*cm, 8.7*cm), font_size=8)

            crues_table = self._crues_table(crues)
            section_5_title = Paragraph("<b>5/Caractéristiques des crues</b>", styles['SectionTitle'])
            if crues_table is None:
                crues_table = Paragraph("Aucune crue détectée", styles['SectionTitle'])

            hydro_crue_img = self._safe_image(hydrogramme_crue_path, width=8.7*cm, height=6.0*cm)
            if hydro_crue_img is None:
                hydro_crue_img = Paragraph("Hydrogramme de crue non disponible", styles['SectionTitle'])

            hydro_annuel_img = self._safe_image(img_path, width=14.7*cm, height=7.2*cm)
            if hydro_annuel_img is None:
                hydro_annuel_img = Paragraph("Hydrogramme annuel non disponible", styles['SectionTitle'])

            page1 = [station_title, Spacer(1, 0.12*cm), section_1, Spacer(1, 0.12*cm), top_panel, Spacer(1, 0.12*cm), section_4]
            elements.extend(page1)
            elements.append(PageBreak())

            page2 = [
                section_5_title,
                crues_table,
                Spacer(1, 0.15*cm),
                Paragraph("6/Hydrogramme de crue", styles['CustomHeading']),
                hydro_crue_img,
                Spacer(1, 0.15*cm),
                Paragraph("7/Hydrogramme annuel", styles['CustomHeading']),
                hydro_annuel_img,
            ]
            elements.extend(page2)
            if position < len(stations) - 1:
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