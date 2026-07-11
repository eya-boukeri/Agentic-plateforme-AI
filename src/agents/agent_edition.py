"""
src/agents/agent_edition.py
Agent Édition - Génération de l'annuaire hydrométrique PDF
Version avec organisation par gouvernorat
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle, Frame, PageTemplate, BaseDocTemplate
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# Ordre des gouvernorats comme dans l'annuaire manuel
GOUVERNORATS_ORDER = [
    "L'ARIANA",
    "MANOUBA", 
    "BIZERTE",
    "BEJA",
    "JENDOUBA",
    "KEF",
    "SILIANA",
    "BEN AROUS",
    "NABEUL",
    "ZAGHOUAN",
    "KAIROUAN",
    "KASSERINE",
    "SIDI BOUZID",
    "SOUSSE",
    "MONASTIR",
    "MAHDIA",
    "SFAX",
    "GAFSA",
    "GABES",
    "KEBILI",
    "TOZEUR",
    "MEDENINE",
    "TATAOUINE"
]

class HeaderFooterDocTemplate(BaseDocTemplate):
    """Template personnalisé avec en-tête et pied de page"""
    
    def __init__(self, filename, **kwargs):
        self.page_number = 0
        self.station_name = ""
        self.annee = ""
        self.gouvernorat = ""
        super().__init__(filename, **kwargs)
        
        self.topMargin = 2.8*cm
        self.bottomMargin = 2.2*cm
        self.leftMargin = 1.5*cm
        self.rightMargin = 1.5*cm
        
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id='normal'
        )
        
        self.addPageTemplates([
            PageTemplate(
                id='OneColumn',
                frames=frame,
                onPage=self._header_footer
            )
        ])
    
    def _header_footer(self, canvas, doc):
        canvas.saveState()
        
        # En-tête
        canvas.setFont('Helvetica-Bold', 8)
        canvas.drawString(doc.leftMargin, A4[1] - 1.8*cm, "REPUBLIQUE TUNISIENNE")
        canvas.setFont('Helvetica', 7)
        canvas.drawString(doc.leftMargin, A4[1] - 2.2*cm, "Ministere de l'Agriculture, des Ressources Hydrauliques et de la Peche")
        canvas.drawString(doc.leftMargin, A4[1] - 2.5*cm, "Direction Generale des Ressources en Eau")
        
        canvas.line(doc.leftMargin, A4[1] - 2.6*cm, A4[0] - doc.rightMargin, A4[1] - 2.6*cm)
        
        # Titre du gouvernorat au centre
        if doc.gouvernorat:
            canvas.setFont('Helvetica-Bold', 10)
            canvas.drawCentredString(A4[0]/2, A4[1] - 2.0*cm, f"Gouvernorat de {doc.gouvernorat}")
        elif doc.station_name:
            canvas.setFont('Helvetica-Bold', 9)
            canvas.drawCentredString(A4[0]/2, A4[1] - 2.0*cm, doc.station_name)
        
        # Pied de page
        canvas.setFont('Helvetica', 7)
        canvas.drawString(doc.leftMargin, doc.bottomMargin - 0.5*cm, f"Annuaire Hydrologique de la Tunisie, {doc.annee}")
        canvas.drawRightString(A4[0] - doc.rightMargin, doc.bottomMargin - 0.5*cm, f"Page {doc.page}")
        canvas.line(doc.leftMargin, doc.bottomMargin - 0.4*cm, A4[0] - doc.rightMargin, doc.bottomMargin - 0.4*cm)
        
        canvas.restoreState()
    
    def afterFlowable(self, flowable):
        self.page = self.page + 1


class AgentEdition:
    def __init__(self, db_config=None, annee=None, output_dir="output/pdf/"):
    
        self.db_host = 'localhost'
        self.db_port = 5432
        self.db_name = 'hydrometry'
        self.db_user = 'postgres'
        self.db_password = 'postgres'  
        
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
        
        db_url = URL.create(
            "postgresql+psycopg2",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
        self.engine = create_engine(db_url, connect_args={"client_encoding": "utf8"})
        print(f"Connexion PostgreSQL : {self.db_host}:{self.db_port}/{self.db_name}")
        
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs("output/graphs/", exist_ok=True)
    
    def close(self):
        if self.engine:
            self.engine.dispose()
            print("Connexion fermee")
    
    def get_stations_with_gouvernorat(self):
        """Récupère les stations avec leur gouvernorat"""
        # Essayer plusieurs noms de colonne possibles pour le gouvernorat
        try:
            query = """
                SELECT DISTINCT 
                    s."Id_Station" as code_station,
                    s."Nom" as nom,
                    s."Gouvernorat" as gouvernorat
                FROM stations_base s
                INNER JOIN statistiques_annuelles st ON s."Id_Station" = st.code_station
                WHERE st.annee = %s
                ORDER BY s."Gouvernorat", s."Nom"
            """
            return pd.read_sql(query, self.engine, params=(self.annee,))
        except Exception:
            print("Colonne 'Gouvernorat' non trouvee, essai avec 'Gouv'...")
            try:
                query = """
                    SELECT DISTINCT 
                        s."Id_Station" as code_station,
                        s."Nom" as nom,
                        s."Gouv" as gouvernorat
                    FROM stations_base s
                    INNER JOIN statistiques_annuelles st ON s."Id_Station" = st.code_station
                    WHERE st.annee = %s
                    ORDER BY s."Gouv", s."Nom"
                """
                return pd.read_sql(query, self.engine, params=(self.annee,))
            except Exception:
                print("Colonne 'Gouv' non trouvee, essai avec 'Zone'...")
                try:
                    query = """
                        SELECT DISTINCT 
                            s."Id_Station" as code_station,
                            s."Nom" as nom,
                            s."Zone" as gouvernorat
                        FROM stations_base s
                        INNER JOIN statistiques_annuelles st ON s."Id_Station" = st.code_station
                        WHERE st.annee = %s
                        ORDER BY s."Zone", s."Nom"
                    """
                    return pd.read_sql(query, self.engine, params=(self.annee,))
                except Exception:
                    print("Colonne 'Zone' non trouvee, essai avec 'Secteur'...")
                    try:
                        query = """
                            SELECT DISTINCT 
                                s."Id_Station" as code_station,
                                s."Nom" as nom,
                                s."Secteur" as gouvernorat
                            FROM stations_base s
                            INNER JOIN statistiques_annuelles st ON s."Id_Station" = st.code_station
                            WHERE st.annee = %s
                            ORDER BY s."Secteur", s."Nom"
                        """
                        return pd.read_sql(query, self.engine, params=(self.annee,))
                    except Exception:
                        print("Aucune colonne de gouvernorat trouvee.")
                        print("Les colonnes disponibles sont :")
                        try:
                            sample_query = "SELECT * FROM stations_base LIMIT 1"
                            df_sample = pd.read_sql(sample_query, self.engine)
                            print(f"   Colonnes: {', '.join(df_sample.columns)}")
                        except:
                            pass
                        query = """
                            SELECT DISTINCT 
                                s."Id_Station" as code_station,
                                s."Nom" as nom,
                                'Toutes' as gouvernorat
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

    def get_debits_instantanes(self, code_station, date_debut, date_fin):
        query = """
            SELECT "Date" AS date_heure, "Valeur" AS debit_m3s
            FROM debits
            WHERE "Id_Station" = %s
              AND "Date" >= %s
              AND "Date" <= %s
            ORDER BY "Date"
        """
        df = pd.read_sql(query, self.engine, params=(code_station, date_debut, date_fin))
        if df.empty:
            return df
        df["date_heure"] = pd.to_datetime(df["date_heure"], errors="coerce")
        df["debit_m3s"] = pd.to_numeric(df["debit_m3s"], errors="coerce")
        return df.dropna(subset=["date_heure", "debit_m3s"]).sort_values("date_heure")

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
        mois_labels = ["Sep", "Oct", "Nov", "Dec", "Jan", "Fev", "Mar", "Avr", "Mai", "Juin", "Juil", "Aout"]

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
        return str(value)

    def dataframe_to_table(self, df, font_size=4.5, header_bg=colors.HexColor("#1a5276"), colWidths=None, total_width=None):
        if df is None or df.empty:
            return None

        data = [list(df.columns)]
        for _, row in df.iterrows():
            data.append([self._format_value(value, decimals=2) for value in row.tolist()])

        # Always give this table explicit column widths. Left to its own
        # devices, Table() sizes itself to the natural width of its content,
        # which can end up wider than whatever fixed-width cell it's later
        # placed into -- and unlike Paragraphs, a Table flowable can't shrink
        # to fit, so ReportLab raises a LayoutError at doc.build() time.
        if colWidths is None:
            n_cols = len(data[0])
            width = total_width if total_width is not None else 10.0 * cm
            colWidths = [width / n_cols] * n_cols

        table = Table(data, colWidths=colWidths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEADING", (0, 0), (-1, -1), font_size + 1),
            ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
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

    def _station_info_table(self, code_station, nom_station, font_size=6):
        details = self.get_station_details(code_station)

        def make_line(label, value, with_check=True):
            prefix = "" if with_check else ""
            formatted_value = self._format_value(value, decimals=3).replace("\n", "<br/>")
            return Paragraph(
                f'<font size="{font_size}"><b>{prefix}{label}:</b> {formatted_value}</font>',
                getSampleStyleSheet()["BodyText"]
            )

        def make_title(text):
            return Paragraph(f'<font size="{font_size + 0.5}"><b>{text}</b></font>', getSampleStyleSheet()["BodyText"])

        date_service = self._pick_value(details, ["Date mise en service", "DateMiseEnService"])
        date_service = str(date_service) if date_service and date_service != "None" else "N/A"

        superficie = self._pick_value(details, ["Superficie", "Superficie_Bassin", "superficie"])
        superficie = f"{superficie} Km²" if superficie and superficie != "None" and superficie != 0 else "N/A"

        left_rows = [
            [make_title("Caracteristiques de la station:")],
            [make_line("Date de mise en service", date_service)],
            [make_line("Secteur hydrographique", self._pick_value(details, ["Secteur hydrographique", "Zone"]))],
            [make_line("Sous-Secteur hydrographique", self._pick_value(details, ["Sous-Secteur", "SousZone"]))],
            [make_line("Cours d'eau", self._pick_value(details, ["Cours d'eau", "CoursEau"]))],
            [make_line("Superficie Bassin", superficie)],
            [make_title("Equipement de la station:")],
            [make_line("Radar RLS + Duosens", self._pick_value(details, ["Equipement"]), with_check=True)],
            [make_line("Echelle", self._pick_value(details, ["Echelle"]), with_check=True)],
        ]

        right_rows = [
            [make_title(" ")],
            [make_line("Coordonnees (UTM en m) X", self._pick_value(details, ["X_UTM", "x_utm"]))],
            [make_line("Coordonnees (UTM en m) Y", self._pick_value(details, ["Y_UTM", "y_utm"]))],
            [make_line("Altitude approximative", self._pick_value(details, ["Altitude"]))],
            [make_line("Crue maximale Observee", self._pick_value(details, ["Crue maximale Observee", "Crue_maximale_observee"]))],
            [make_title("Dispositif de Jaugeage:")],
            [make_line("Crue", "saumon de 50 kg et treuil")],
            [make_line("Etiage", "a gue")],
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
            [[Paragraph("<font size='7'><b>1/Fiche de renseignements de la station:</b></font>", getSampleStyleSheet()["BodyText"])], 
             [Table([[left_table, right_table]], colWidths=[8.0*cm, 8.1*cm])]],
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

    def _extremes_lines(self, stats):
        if not stats:
            return None

        def fmt_debit(value):
            if value is None or pd.isna(value):
                return "-"
            try:
                return f"{float(value):.2f}".replace(".", ",")
            except:
                return str(value)

        def fmt_date_jour(value):
            if value is None or pd.isna(value):
                return ""
            try:
                return pd.to_datetime(value).strftime("%d/%m/%Y")
            except:
                return str(value)

        def fmt_date_heure(value):
            if value is None or pd.isna(value):
                return ""
            try:
                ts = pd.to_datetime(value)
                return f"{ts.strftime('%d/%m/%Y')} {ts.strftime('%H:%M')}"
            except:
                return str(value)

        lignes = [
            f"Max journalier = {fmt_debit(stats.get('debit_max_jour'))} m³/s le {fmt_date_jour(stats.get('date_max_jour'))}",
            f"Min journalier = {fmt_debit(stats.get('debit_min_jour'))} m³/s le {fmt_date_jour(stats.get('date_min_jour'))}",
            f"Mini Instantane = {fmt_debit(stats.get('debit_min_inst'))} m³/s --> {fmt_date_heure(stats.get('date_min_inst'))}",
            f"Max Instantane = {fmt_debit(stats.get('debit_max_inst'))} m³/s --> {fmt_date_heure(stats.get('date_max_inst'))}",
        ]

        style = getSampleStyleSheet()["BodyText"]
        return [Paragraph(f"<font size='7'>{ligne}</font>", style) for ligne in lignes]

    def _section_table(self, title, rows, col_widths=(5.3*cm, 10.1*cm), font_size=7):
        data = [[Paragraph(f"<b>{title}</b>", getSampleStyleSheet()["BodyText"]), ""]]
        for label, value in rows:
            if isinstance(value, (float, np.floating)):
                data.append([label, self._format_value(value, decimals=3)])
            else:
                data.append([label, self._format_value(value)])

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
        ax.set_title("Courbe d'etalonnage", fontsize=8)
        ax.set_xlabel("Hauteur (cm)", fontsize=7)
        ax.set_ylabel("Debit (m³/s)", fontsize=7)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=6)
        plt.tight_layout()

        filename = f"output/graphs/etalonnage_{code_station}_{self.annee}.png"
        fig.savefig(filename, dpi=250, bbox_inches="tight")
        plt.close(fig)
        return filename

    def _plot_hydrogramme_crue_principale(self, crues_df, code_station, nom_station):
        if crues_df is None or crues_df.empty:
            return None
        
        crues_df = crues_df.copy()
        crues_df['debit_max_m3s'] = pd.to_numeric(crues_df['debit_max_m3s'], errors='coerce')
        crue_max = crues_df.loc[crues_df['debit_max_m3s'].idxmax()]
        
        date_debut = pd.to_datetime(crue_max.get("date_debut"), errors="coerce")
        date_fin = pd.to_datetime(crue_max.get("date_fin"), errors="coerce")
        
        if pd.isna(date_debut) or pd.isna(date_fin):
            return None
        
        duree = date_fin - date_debut
        marge_avant = duree if duree > pd.Timedelta(0) else pd.Timedelta(hours=48)
        marge_apres = duree / 4 if duree > pd.Timedelta(0) else pd.Timedelta(hours=12)
        
        fenetre_debut = date_debut - marge_avant
        fenetre_fin = date_fin + marge_apres
        
        serie = self.get_debits_instantanes(code_station, fenetre_debut, fenetre_fin)
        if serie.empty:
            return None
        
        fig, ax = plt.subplots(figsize=(4.8, 3.1))
        ax.plot(serie["date_heure"], serie["debit_m3s"], color="#2e5aac", linewidth=1.0)
        
        date_pic = serie.loc[serie['debit_m3s'].idxmax(), 'date_heure']
        debit_pic = serie['debit_m3s'].max()
        ax.axvline(date_pic, color="#c0392b", linestyle="--", linewidth=0.8)
        ax.annotate(f'Qmax={debit_pic:.1f} m³/s', 
                   xy=(date_pic, debit_pic),
                   xytext=(5, 5), textcoords='offset points',
                   fontsize=6, color='#c0392b')
        
        ax.set_title(f"Hydrogramme de crue - {nom_station}", fontsize=8)
        ax.set_xlabel("Date", fontsize=7)
        ax.set_ylabel("Debit (m³/s)", fontsize=7)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=6)
        fig.autofmt_xdate(rotation=25)
        plt.tight_layout()
        
        filename = f"output/graphs/crue_principale_{code_station}_{self.annee}.png"
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
            ("Date Debut", "date_debut"),
            ("Date Fin", "date_fin"),
            ("Tps Base\n(mn)", "temps_base_min"),
            ("Tps Montee\n(mn)", "temps_montee_min"),
            ("Val Debut\n(m³/s)", "debit_debut"),
            ("Val Fin\n(m³/s)", "debit_fin"),
            ("Val Maxi\n(m³/s)", "debit_max_m3s"),
            ("V Ecou\n(Hm³)", "volume_ecoule_hm3"),
            ("V Ruiss\n(Hm³)", "volume_ruiss_hm3"),
            ("L Ecou\n(mm)", "lame_ecoulee_mm"),
            ("L Ruiss\n(mm)", "lame_ruiss_mm"),
        ]

        FONT_SIZE = 4.0
        LEADING = 4.5

        data = [[
            Paragraph(f"<font size='{FONT_SIZE}'><b>{label}</b></font>", getSampleStyleSheet()["BodyText"])
            for label, _ in columns
        ]]

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

                row_values.append(Paragraph(f"<font size='{FONT_SIZE}'>{value}</font>", getSampleStyleSheet()["BodyText"]))
            data.append(row_values)

        width = 16.1 * cm
        col_width = width / len(columns)
        table = Table(data, colWidths=[col_width] * len(columns), repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), FONT_SIZE),
            ("LEADING", (0, 0), (-1, -1), LEADING),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
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
        if not crues.empty:
            hydrogramme_crue_path = self._plot_hydrogramme_crue_principale(crues, code_station, nom_station)

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

    def generer_hydrogramme_annuel(self, df_debits, code_station, nom_station):
        if df_debits.empty:
            return None
        
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(df_debits['jour'], df_debits['debit_moyen'], color='#1a5276', linewidth=1.5)
        
        moyenne = df_debits['debit_moyen'].mean()
        ax.axhline(y=moyenne, color='#27ae60', linestyle='--', label=f'Moyenne: {moyenne:.2f} m³/s')
        
        ax.set_xlabel('Mois')
        ax.set_ylabel('Debit (m³/s)')
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
        print("\nGENERATION DE L'ANNUAIRE PDF")
        
        # Récupérer les stations avec leur gouvernorat
        df_stations = self.get_stations_with_gouvernorat()
        print(f"{len(df_stations)} stations a traiter")
        
        # Grouper par gouvernorat
        stations_by_gouv = {}
        for _, row in df_stations.iterrows():
            gouv = row.get('gouvernorat', 'Inconnu')
            if gouv and gouv != 'Inconnu':
                # Nettoyer le nom du gouvernorat
                gouv = gouv.upper().strip()
                # Standardiser les noms
                if "ARIANA" in gouv:
                    gouv = "L'ARIANA"
                elif "MANOUBA" in gouv:
                    gouv = "MANOUBA"
                elif "BIZERTE" in gouv:
                    gouv = "BIZERTE"
                elif "BEJA" in gouv:
                    gouv = "BEJA"
                elif "JENDOUBA" in gouv:
                    gouv = "JENDOUBA"
                elif "KEF" in gouv:
                    gouv = "KEF"
                elif "SILIANA" in gouv:
                    gouv = "SILIANA"
                elif "BEN AROUS" in gouv:
                    gouv = "BEN AROUS"
                elif "NABEUL" in gouv:
                    gouv = "NABEUL"
                elif "ZAGHOUAN" in gouv:
                    gouv = "ZAGHOUAN"
                elif "KAIROUAN" in gouv:
                    gouv = "KAIROUAN"
                elif "KASSERINE" in gouv:
                    gouv = "KASSERINE"
                elif "SIDI BOUZID" in gouv:
                    gouv = "SIDI BOUZID"
                elif "SOUSSE" in gouv:
                    gouv = "SOUSSE"
                elif "MONASTIR" in gouv:
                    gouv = "MONASTIR"
                elif "MAHDIA" in gouv:
                    gouv = "MAHDIA"
                elif "SFAX" in gouv:
                    gouv = "SFAX"
                elif "GAFSA" in gouv:
                    gouv = "GAFSA"
                elif "GABES" in gouv:
                    gouv = "GABES"
                elif "KEBILI" in gouv:
                    gouv = "KEBILI"
                elif "TOZEUR" in gouv:
                    gouv = "TOZEUR"
                elif "MEDENINE" in gouv:
                    gouv = "MEDENINE"
                elif "TATAOUINE" in gouv:
                    gouv = "TATAOUINE"
                
                if gouv not in stations_by_gouv:
                    stations_by_gouv[gouv] = []
                stations_by_gouv[gouv].append(row)
        
        # Si des stations n'ont pas de gouvernorat, les mettre dans "AUTRES"
        if df_stations[df_stations['gouvernorat'].isna() | (df_stations['gouvernorat'] == '')].shape[0] > 0:
            stations_by_gouv["AUTRES"] = []
            for _, row in df_stations[df_stations['gouvernorat'].isna() | (df_stations['gouvernorat'] == '')].iterrows():
                stations_by_gouv["AUTRES"].append(row)
        
        # Trier les gouvernorats selon l'ordre défini
        gouv_order = [g for g in GOUVERNORATS_ORDER if g in stations_by_gouv]
        # Ajouter les gouvernorats non listés à la fin
        for g in sorted(stations_by_gouv.keys()):
            if g not in gouv_order and g != "AUTRES":
                gouv_order.append(g)
        if "AUTRES" in stations_by_gouv:
            gouv_order.append("AUTRES")
        
        filename = os.path.join(self.output_dir, f"annuaire_hydrometrique_{self.annee}.pdf")
        
        doc = HeaderFooterDocTemplate(
            filename,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2.8*cm,
            bottomMargin=2.2*cm
        )
        doc.annee = f"{self.annee}-{self.annee+1}"
        
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='CustomTitle', parent=styles['Title'], 
                                  fontSize=18, alignment=TA_CENTER, spaceAfter=30))
        styles.add(ParagraphStyle(name='CustomHeading', parent=styles['Heading2'], 
                                  fontSize=14, spaceBefore=20, spaceAfter=10))
        styles.add(ParagraphStyle(name='CustomBody', parent=styles['Normal'], 
                                  fontSize=10, spaceAfter=6))
        styles.add(ParagraphStyle(name='SectionTitle', parent=styles['Normal'], fontSize=9, leading=10, spaceAfter=2))
        styles.add(ParagraphStyle(name='GouvTitle', parent=styles['Heading1'], 
                                  fontSize=16, alignment=TA_CENTER, spaceBefore=30, spaceAfter=20))
        
        elements = []
        
        # Page de garde
        elements.append(Paragraph("REPUBLIQUE TUNISIENNE", styles['CustomTitle']))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph("Ministere de l'Agriculture, des Ressources Hydrauliques et de la Peche", styles['CustomTitle']))
        elements.append(Paragraph("Direction Generale des Ressources en Eau", styles['CustomTitle']))
        elements.append(Spacer(1, 2*cm))
        elements.append(Paragraph(f"ANNUAIRE HYDROMETRIQUE {self.annee}-{self.annee+1}", styles['CustomTitle']))
        elements.append(Spacer(1, 1*cm))
        elements.append(Paragraph(f"Genere le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['CustomBody']))
        elements.append(PageBreak())
        
        # Introduction
        elements.append(Paragraph("INTRODUCTION", styles['CustomHeading']))
        elements.append(Paragraph(
            f"Le present annuaire presente les resultats des observations hydrometriques "
            f"de l'annee hydrologique {self.annee}-{self.annee+1}. Il a ete genere "
            f"automatiquement par la plateforme Agentic AI de la DGRE.",
            styles['CustomBody']
        ))
        elements.append(Paragraph(
            "Les stations sont organisees par gouvernorat conformement a la structure "
            "de l'annuaire hydrologique officiel.",
            styles['CustomBody']
        ))
        elements.append(PageBreak())
        
        # Traiter chaque gouvernorat
        total_stations = 0
        for gouv_idx, gouv in enumerate(gouv_order):
            stations = stations_by_gouv[gouv]
            print(f"\nGouvernorat: {gouv} ({len(stations)} stations)")
            
            # Page de présentation du gouvernorat
            doc.gouvernorat = gouv
            doc.station_name = ""
            
            gouv_title = Paragraph(f"GOUVERNORAT DE {gouv}", styles['GouvTitle'])
            elements.append(gouv_title)
            elements.append(Spacer(1, 0.5*cm))
            
            # Liste des stations du gouvernorat
            station_list = []
            for i, station in enumerate(stations, 1):
                code = station['code_station']
                nom = station['nom']
                station_list.append(Paragraph(f"{i}. {nom} - {code}", styles['CustomBody']))
            
            for item in station_list:
                elements.append(item)
            
            elements.append(PageBreak())
            
            # Traiter chaque station du gouvernorat
            for station in stations:
                code = station['code_station']
                nom = station['nom']
                total_stations += 1
                
                print(f"  Station: {nom} ({code})")
                
                # Réinitialiser le nom de la station pour l'en-tête
                doc.station_name = f"Station : {nom} - {code}"
                doc.gouvernorat = gouv
                
                report_data = self.build_station_report_data(code, nom)
                stats = report_data["caracteristiques_hydrometriques"]
                tableau_debits = report_data["tableau_debits_moyens_journaliers"]
                crues = report_data["crues"]
                etalonnage_path = report_data["etalonnage_path"]
                hydrogramme_crue_path = report_data["hydrogramme_crue_path"]
                img_path = report_data["hydrogramme_path"]
                
                if not stats:
                    print(f"     Statistiques manquantes")
                    continue
                
                # ===== PAGE DE LA STATION =====
                station_title = Paragraph(f"<b>Station : {nom} - {code}</b>", styles['CustomHeading'])
                section_1 = self._station_info_table(code, nom, font_size=6)

                # Etalonnage (gauche)
                etalonnage_elements = [
                    Paragraph("<b>2/ Etalonnage de la station :</b>", styles['SectionTitle']),
                    Paragraph("Valide du 01/01/2012 jusqu'a nos jours", styles['SectionTitle'])
                ]
                if etalonnage_path:
                    etalonnage_img = self._safe_image(etalonnage_path, width=5.8*cm, height=4.2*cm)
                    if etalonnage_img:
                        etalonnage_elements.append(etalonnage_img)
                else:
                    etalonnage_elements.append(Paragraph("Courbe d'etalonnage non disponible", styles['SectionTitle']))
                section_2 = Table([[item] for item in etalonnage_elements], colWidths=[5.9*cm])
                section_2.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

                # Débits journaliers (droite)
                # section_3's outer box must match the top_panel column width
                # below (this mismatch -- 10.8cm here vs 10.1cm in top_panel --
                # was the cause of the LayoutError).
                SECTION_3_WIDTH = 10.1 * cm
                tableau_debits_display = self._daily_table_with_summary(tableau_debits)
                section_3_table = self.dataframe_to_table(
                    tableau_debits_display, font_size=4.5, total_width=SECTION_3_WIDTH - 0.2 * cm
                )
                if section_3_table is None:
                    section_3_table = Paragraph("Tableau des debits moyens journaliers non disponible", styles['SectionTitle'])

                section_3_content = [Paragraph("<b>3/ Debits moyens journaliers :</b>", styles['SectionTitle']), section_3_table]
                extremes_lines = self._extremes_lines(stats)
                if extremes_lines:
                    section_3_content.append(Spacer(1, 0.1 * cm))
                    section_3_content.extend(extremes_lines)

                section_3 = Table([[item] for item in section_3_content], colWidths=[SECTION_3_WIDTH])
                section_3.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

                top_panel = Table([[section_2, section_3]], colWidths=[6.2*cm, SECTION_3_WIDTH], hAlign="LEFT")
                top_panel.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    # Zero out the default 6pt cell padding: section_2/section_3
                    # are declared at exactly this column's width, so any
                    # leftover padding here would make them wider than the
                    # space actually available and re-trigger the LayoutError.
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))

                # Caracteristiques
                caracs_rows = [
                    ["Debit moyen annuel", f"{stats['debit_moyen']:.2f} m³/s" if pd.notna(stats.get('debit_moyen')) else ""],
                    ["Volume Total ecoule a la station", f"{stats['volume_total_hm3']:.2f} Hm³" if pd.notna(stats.get('volume_total_hm3')) else ""],
                    ["Hauteur de la lame d'eau ecoulee", f"{stats['lame_ecoulee_mm']:.1f} mm" if pd.notna(stats.get('lame_ecoulee_mm')) else ""],
                ]
                section_4 = self._section_table("4/Caracteristiques hydrometriques de la station:", caracs_rows, col_widths=(7.2*cm, 8.7*cm), font_size=8)

                page1 = [
                    station_title, 
                    Spacer(1, 0.1*cm), 
                    section_1,
                    Spacer(1, 0.1*cm), 
                    top_panel,
                    Spacer(1, 0.1*cm), 
                    section_4
                ]
                elements.extend(page1)
                elements.append(PageBreak())

                # ===== PAGE 2 =====
                crues_table = self._crues_table(crues)
                section_5_title = Paragraph("<b>5/Caracteristiques des crues</b>", styles['SectionTitle'])
                if crues_table is None:
                    crues_table = Paragraph("Aucune crue detectee", styles['SectionTitle'])

                hydro_crue_img = self._safe_image(hydrogramme_crue_path, width=8.7*cm, height=6.0*cm)
                if hydro_crue_img is None:
                    hydro_crue_img = Paragraph("Hydrogramme de crue non disponible", styles['SectionTitle'])

                hydro_annuel_img = self._safe_image(img_path, width=14.7*cm, height=7.2*cm)
                if hydro_annuel_img is None:
                    hydro_annuel_img = Paragraph("Hydrogramme annuel non disponible", styles['SectionTitle'])

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
                
                # Ajouter une page de séparation entre les stations (sauf la dernière)
                if total_stations < len(df_stations):
                    elements.append(PageBreak())
        
        doc.build(elements)
        print(f"\nPDF genere : {filename}")
        print(f"Total: {total_stations} stations traitees sur {len(df_stations)}")
        return filename


if __name__ == "__main__":
    agent = AgentEdition(annee=2019)
    try:
        agent.generer_pdf()
    finally:
        agent.close()