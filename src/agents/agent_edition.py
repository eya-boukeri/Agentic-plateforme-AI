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

        if doc.page == 1:
            # Pas d'en-tete/pied de page sur la page de garde.
            canvas.restoreState()
            return

        # En-tete : 2 colonnes sur 2 lignes, comme l'annuaire officiel
        # (pas de bandeau "REPUBLIQUE TUNISIENNE" ni de titre centre ici).
        canvas.setFont('Helvetica-Bold', 8)
        canvas.drawString(doc.leftMargin, A4[1] - 1.6*cm, "Ministère de l'Agriculture,")
        canvas.drawString(doc.leftMargin, A4[1] - 1.95*cm, "des Ressources Hydrauliques et de la Pêche")
        canvas.drawRightString(A4[0] - doc.rightMargin, A4[1] - 1.6*cm, "Direction Générale des Ressources en Eau")
        canvas.drawRightString(A4[0] - doc.rightMargin, A4[1] - 1.95*cm, "Direction des Eaux de Surface")
        canvas.line(doc.leftMargin, A4[1] - 2.15*cm, A4[0] - doc.rightMargin, A4[1] - 2.15*cm)

        # Pied de page : 3 zones (titre / numero de page / gouvernorat)
        canvas.setFont('Helvetica', 7)
        canvas.line(doc.leftMargin, doc.bottomMargin - 0.4*cm, A4[0] - doc.rightMargin, doc.bottomMargin - 0.4*cm)
        canvas.drawString(doc.leftMargin, doc.bottomMargin - 0.7*cm, f"Annuaire Hydrologique de la Tunisie, {doc.annee}")
        canvas.drawCentredString(A4[0]/2, doc.bottomMargin - 0.7*cm, str(doc.page))
        if doc.gouvernorat:
            canvas.drawRightString(A4[0] - doc.rightMargin, doc.bottomMargin - 0.7*cm, f"Gouvernorat de {doc.gouvernorat}")

        canvas.restoreState()

    # NOTE : pas de surcharge de afterFlowable() ici. BaseDocTemplate
    # incremente deja doc.page correctement a chaque saut de page ;
    # le faire en plus dans afterFlowable() (appele apres CHAQUE flowable,
    # pas juste a chaque page) faussait completement la numerotation.


def normaliser_gouvernorat(gouv):
    """Normalise un libelle brut de gouvernorat (ex: 'beja', 'Béja') vers le
    code standard utilise dans GOUVERNORATS_ORDER (ex: 'BEJA'). Retourne
    None si `gouv` est vide/absent."""
    if not gouv:
        return None
    gouv = str(gouv).upper().strip()
    correspondances = [
        "ARIANA", "MANOUBA", "BIZERTE", "BEJA", "JENDOUBA", "KEF", "SILIANA",
        "BEN AROUS", "NABEUL", "ZAGHOUAN", "KAIROUAN", "KASSERINE",
        "SIDI BOUZID", "SOUSSE", "MONASTIR", "MAHDIA", "SFAX", "GAFSA",
        "GABES", "KEBILI", "TOZEUR", "MEDENINE", "TATAOUINE",
    ]
    for cle in correspondances:
        if cle in gouv:
            return "L'ARIANA" if cle == "ARIANA" else cle
    return gouv


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
        """Récupère les stations avec leur gouvernorat depuis la table
        `station` (donnees propres, confirmees par capture d'ecran :
        code_station, nom, cours_eau, x_utm, y_utm, altitude,
        superficie_km2, bassin, region, gouvernorat). La table
        `stations_base` (import Access brut) a le meme type d'info mais
        avec un encodage corrompu sur les colonnes texte (valeurs "?")."""
        query = """
            SELECT DISTINCT
                s.code_station,
                s.nom,
                s.gouvernorat
            FROM station s
            INNER JOIN statistiques_annuelles st ON s.code_station = st.code_station
            WHERE st.annee = %s
            ORDER BY s.gouvernorat, s.nom
        """
        df = pd.read_sql(query, self.engine, params=(self.annee,))
        if df.empty:
            print("Aucune station trouvee dans 'station' pour cette annee. "
                  "Verifiez que scripts/import_stations_from_manual.py a bien ete execute.")
        return df

    def get_stations_reseau_gouvernorat(self, gouv_cible):
        """Liste TOUTES les stations enregistrees dans `station` pour un
        gouvernorat normalise donne (ex: 'BEJA'), y compris celles qui
        n'ont pas de statistiques_annuelles cette annee-la. C'est la liste
        utilisee par le tableau manuel 'Identification des stations du
        reseau' (Tableau 8 dans l'annuaire officiel) : le reseau est plus
        large que les seules stations exploitables une annee donnee."""
        query = "SELECT code_station, nom, cours_eau, x_utm, y_utm, altitude, superficie_km2, bassin, region, gouvernorat FROM station"
        df = pd.read_sql(query, self.engine)
        if df.empty:
            return df
        df["gouvernorat_norm"] = df["gouvernorat"].apply(normaliser_gouvernorat)
        return df[df["gouvernorat_norm"] == gouv_cible].reset_index(drop=True)

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
        """Champs specifiques uniquement disponibles dans l'import Access
        brut (date de mise en service, equipement, echelle, crue max
        observee...). Pour coordonnees/cours d'eau/gouvernorat, voir
        get_station_metadata() qui privilegie la table `station`."""
        query = """
            SELECT *
            FROM stations_base
            WHERE "Id_Station" = %s
            LIMIT 1
        """
        df = pd.read_sql(query, self.engine, params=(code_station,))
        return df.iloc[0].to_dict() if not df.empty else {}

    def get_station_metadata(self, code_station):
        """Fusionne les caracteristiques de la station depuis la table
        `station` (fiable : coordonnees, cours d'eau, bassin, region,
        gouvernorat, superficie) et `stations_base` (pour les champs qui
        n'existent que la : date de mise en service, equipement, crue
        maximale observee...). `station` est prioritaire en cas de doublon."""
        details = dict(self.get_station_details(code_station))  # stations_base, best-effort

        try:
            query = """
                SELECT cours_eau, x_utm, y_utm, altitude, superficie_km2,
                       bassin, region, gouvernorat
                FROM station
                WHERE code_station = %s
                LIMIT 1
            """
            df = pd.read_sql(query, self.engine, params=(code_station,))
            if not df.empty:
                station_row = df.iloc[0].to_dict()
                details["Cours d'eau"] = station_row.get("cours_eau") or details.get("Cours d'eau")
                details["X_UTM"] = station_row.get("x_utm") or details.get("X_UTM")
                details["Y_UTM"] = station_row.get("y_utm") or details.get("Y_UTM")
                details["Altitude"] = station_row.get("altitude") or details.get("Altitude")
                details["Superficie"] = station_row.get("superficie_km2") or details.get("Superficie")
                details["Gouvernorat"] = station_row.get("gouvernorat") or details.get("Gouvernorat")
                # Meilleure correspondance disponible pour ces deux champs du
                # rapport manuel (a confirmer visuellement sur une vraie fiche) :
                details["Secteur hydrographique"] = station_row.get("bassin") or details.get("Secteur hydrographique")
                details["Sous-Secteur"] = station_row.get("region") or details.get("Sous-Secteur")
        except Exception as e:
            print(f"Impossible de lire les metadonnees de 'station' pour {code_station} : {e}")

        return details
    
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
        details = self.get_station_metadata(code_station)

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
        
        ax.set_title(f"hydrogramme de crue du {date_debut.strftime('%d/%m/%Y')}", fontsize=8)
        ax.set_xlabel("Date", fontsize=7)
        ax.set_ylabel("Débits instantanés (m³/s)", fontsize=7)
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

    def _tableau_identification_stations(self, stations, gouv):
        """Tableau d'identification des stations hydrometriques du
        gouvernorat (equivalent du 'Tableau 8' de l'annuaire manuel) :
        BV (bassin + code secteur), N°, N° Station, Station, Cours d'eau,
        XUTM, YUTM, Alt, Sup. Les colonnes "Mesures effectuees"
        (DMJ/JC/JE/RS/TP) du manuel ne sont pas incluses : cette donnee
        n'existe dans aucune table de la base actuelle (a fournir si vous
        voulez les completer plutot que d'afficher des valeurs inventees)."""
        header_row1 = ["BV", "N°", "N° Station", "Station", "Cours d'eau",
                        "XUTM (m)", "YUTM (m)", "Alt (m)", "Sup (Km²)"]
        data = [header_row1]

        # Trie par BV pour permettre le regroupement visuel (comme le
        # manuel), en preservant un ordre stable a l'interieur d'un meme BV.
        stations_triees = sorted(
            stations,
            key=lambda s: (str(s.get('bassin') or s.get('region') or ''), str(s.get('nom') or ''))
        )

        bv_spans = []  # (ligne_debut, nb_lignes) pour fusionner la colonne BV
        ligne_courante = 1
        bv_precedent = None
        debut_span = 1

        for i, station in enumerate(stations_triees, 1):
            bassin = station.get('bassin') or ""
            region = station.get('region') or ""
            bv_libelle = f"{bassin}\n{region}".strip() if (bassin or region) else ""

            cours_eau = station.get('cours_eau') or ""
            x_utm = station.get('x_utm')
            y_utm = station.get('y_utm')
            alt = station.get('altitude')
            sup = station.get('superficie_km2')

            data.append([
                bv_libelle, str(i), str(station.get('code_station', '')), str(station.get('nom', '')),
                str(cours_eau), self._format_value(x_utm), self._format_value(y_utm),
                self._format_value(alt), self._format_value(sup)
            ])

            if bv_libelle != bv_precedent:
                if bv_precedent is not None:
                    bv_spans.append((debut_span, ligne_courante - debut_span))
                debut_span = ligne_courante
                bv_precedent = bv_libelle
            ligne_courante += 1
        if stations_triees:
            bv_spans.append((debut_span, ligne_courante - debut_span))

        table = Table(data, repeatRows=1,
                       colWidths=[1.6*cm, 0.8*cm, 2.2*cm, 3.0*cm, 2.2*cm, 1.8*cm, 1.8*cm, 1.2*cm, 1.5*cm])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a5276")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ]
        # Fusionne les cellules de la colonne BV pour les stations
        # consecutives du meme bassin/secteur (comme le manuel).
        for start_row, span_len in bv_spans:
            if span_len > 1:
                style_cmds.append(("SPAN", (0, start_row), (0, start_row + span_len - 1)))
        table.setStyle(TableStyle(style_cmds))
        return table

    def _carte_stations_gouvernorat(self, stations, gouv):
        """Carte simplifiee de situation des stations, a partir des
        coordonnees UTM deja en base (pas de fond de carte officiel/SIG,
        juste la position relative des stations et leurs noms)."""
        points = []
        for station in stations:
            nom = station.get('nom', '')
            try:
                x = float(station.get('x_utm'))
                y = float(station.get('y_utm'))
                points.append((x, y, nom))
            except (TypeError, ValueError):
                continue

        if not points:
            return None

        fig, ax = plt.subplots(figsize=(6.5, 5.5))
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        ax.scatter(xs, ys, color="#1a5276", s=35, zorder=3)
        for x, y, nom in points:
            ax.annotate(nom, (x, y), fontsize=6, xytext=(4, 4), textcoords="offset points")

        ax.set_title(f"Carte de situation des stations - Gouvernorat de {gouv}", fontsize=9)
        ax.set_xlabel("X UTM (m)", fontsize=7)
        ax.set_ylabel("Y UTM (m)", fontsize=7)
        ax.tick_params(labelsize=6)
        ax.grid(True, alpha=0.3)
        ax.set_aspect("equal", adjustable="datalim")
        plt.tight_layout()

        filename = f"output/graphs/carte_{gouv.replace(chr(39), '').replace(' ', '_')}_{self.annee}.png"
        fig.savefig(filename, dpi=200, bbox_inches="tight")
        plt.close(fig)
        return filename

    def _situation_geographique_text(self, stations, gouv):
        """Texte synthetique de situation geographique du gouvernorat,
        genere a partir des donnees reellement disponibles (nombre de
        stations, cours d'eau, secteurs hydrographiques concernes)."""
        cours_eau_set = set()
        secteurs_set = set()
        for station in stations:
            cours_eau = station.get('cours_eau')
            secteur = station.get('bassin')
            if cours_eau and str(cours_eau) not in ("None", ""):
                cours_eau_set.add(str(cours_eau))
            if secteur and str(secteur) not in ("None", ""):
                secteurs_set.add(str(secteur))

        phrases = [
            f"Le gouvernorat de {gouv} compte {len(stations)} station(s) hydrométrique(s) "
            f"suivies dans le présent annuaire."
        ]
        if cours_eau_set:
            phrases.append("Les cours d'eau concernés sont : " + ", ".join(sorted(cours_eau_set)) + ".")
        if secteurs_set:
            phrases.append("Secteur(s) hydrographique(s) : " + ", ".join(sorted(secteurs_set)) + ".")

        return " ".join(phrases)

    def _section_precipitations(self, gouv):
        """Placeholder : necessite une source de donnees de precipitations
        (non presente dans la base actuelle). Retourne None tant que cette
        donnee n'est pas disponible."""
        return None

    def _section_ressources_surface(self, gouv):
        """Placeholder : necessite une source de donnees de barrages /
        ressources de surface (non presente dans la base actuelle)."""
        return None

    def build_station_report_data(self, code_station, nom_station):
        """Construit le rapport complet d'une station"""
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

        if df_stations.empty:
            raise RuntimeError(
                "Aucune station a traiter (table 'station' vide ou aucune "
                "statistique_annuelle pour cette annee). Verifiez l'import "
                "des donnees avant de regenerer le PDF."
            )
        
        # Grouper par gouvernorat (normalisation factorisee dans
        # normaliser_gouvernorat(), reutilisee aussi par
        # get_stations_reseau_gouvernorat pour rester cohérent)
        stations_by_gouv = {}
        for _, row in df_stations.iterrows():
            gouv = normaliser_gouvernorat(row.get('gouvernorat'))
            if gouv:
                stations_by_gouv.setdefault(gouv, []).append(row)

        # Si des stations n'ont pas de gouvernorat, les mettre dans "AUTRES"
        sans_gouv = df_stations[df_stations['gouvernorat'].isna() | (df_stations['gouvernorat'] == '')]
        if not sans_gouv.empty:
            stations_by_gouv["AUTRES"] = [row for _, row in sans_gouv.iterrows()]
        
        # Trier les gouvernorats selon l'ordre défini
        gouv_order = [g for g in GOUVERNORATS_ORDER if g in stations_by_gouv]
        # Ajouter les gouvernorats non listés à la fin
        for g in sorted(stations_by_gouv.keys()):
            if g not in gouv_order and g != "AUTRES":
                gouv_order.append(g)
        if "AUTRES" in stations_by_gouv:
            gouv_order.append("AUTRES")

        if not gouv_order:
            raise RuntimeError(
                "Aucun gouvernorat determine pour les stations trouvees. "
                "Verifiez la colonne 'gouvernorat' de la table 'station'."
            )
        
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
        
        # Page de garde (pas d'en-tete/pied de page dessus, voir _header_footer)
        elements.append(Paragraph("REPUBLIQUE TUNISIENNE", styles['CustomTitle']))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph("Ministère de l'Agriculture, des Ressources Hydrauliques et de la Pêche", styles['CustomTitle']))
        elements.append(Paragraph("Direction Générale des Ressources en Eau", styles['CustomTitle']))
        elements.append(Spacer(1, 2*cm))
        elements.append(Paragraph(f"ANNUAIRE HYDROMÉTRIQUE {self.annee}-{self.annee+1}", styles['CustomTitle']))
        elements.append(Spacer(1, 1*cm))
        elements.append(Paragraph(f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['CustomBody']))
        elements.append(PageBreak())
        
        # Introduction
        elements.append(Paragraph("INTRODUCTION", styles['CustomHeading']))
        elements.append(Paragraph(
            f"Le présent annuaire présente les résultats des observations hydrométriques "
            f"de l'année hydrologique {self.annee}-{self.annee+1}. Il a été généré "
            f"automatiquement par la plateforme Agentic AI de la DGRE.",
            styles['CustomBody']
        ))
        elements.append(Paragraph(
            "Les stations sont organisées par gouvernorat conformément à la structure "
            "de l'annuaire hydrologique officiel.",
            styles['CustomBody']
        ))
        elements.append(PageBreak())
        
        # Traiter chaque gouvernorat
        total_stations = 0
        for gouv_idx, gouv in enumerate(gouv_order):
            stations = stations_by_gouv[gouv]
            # Liste complete du reseau (toutes les stations du gouvernorat,
            # meme sans statistiques cette annee) pour les sections 1/4/5 -
            # differente de `stations` qui ne sert qu'a generer les fiches
            # individuelles (celles-la ont besoin de donnees exploitables).
            df_reseau = self.get_stations_reseau_gouvernorat(gouv)
            stations_reseau = [row for _, row in df_reseau.iterrows()] if not df_reseau.empty else stations
            print(f"\nGouvernorat: {gouv} ({len(stations)} stations)")
            
            # Page de présentation du gouvernorat
            doc.gouvernorat = gouv
            doc.station_name = ""
            
            gouv_title = Paragraph(f"GOUVERNORAT DE {gouv}", styles['GouvTitle'])
            elements.append(gouv_title)
            elements.append(Spacer(1, 0.3*cm))

            # 1/ Situation geographique
            elements.append(Paragraph("1/ Situation géographique", styles['CustomHeading']))
            elements.append(Paragraph(self._situation_geographique_text(stations_reseau, gouv), styles['CustomBody']))

            # 2/ Precipitations de l'annee hydrologique
            precip_section = self._section_precipitations(gouv)
            elements.append(Paragraph("2/ Précipitations de l'année hydrologique", styles['CustomHeading']))
            if precip_section:
                elements.append(precip_section)
            else:
                elements.append(Paragraph(
                    "Données de précipitations non disponibles dans la base actuelle.",
                    styles['CustomBody']
                ))

            # 3/ Ressources de surface
            ressources_section = self._section_ressources_surface(gouv)
            elements.append(Paragraph("3/ Ressources de surface", styles['CustomHeading']))
            if ressources_section:
                elements.append(ressources_section)
            else:
                elements.append(Paragraph(
                    "Données de barrages / ressources de surface non disponibles dans la base actuelle.",
                    styles['CustomBody']
                ))
            elements.append(PageBreak())

            # 4/ Carte de situation des stations
            elements.append(Paragraph("4/ Carte de situation des stations", styles['CustomHeading']))
            carte_path = self._carte_stations_gouvernorat(stations_reseau, gouv)
            carte_img = self._safe_image(carte_path, width=14*cm, height=11*cm)
            if carte_img:
                elements.append(carte_img)
            else:
                elements.append(Paragraph("Carte non disponible (coordonnées manquantes).", styles['CustomBody']))
            elements.append(PageBreak())

            # 5/ Tableau d'identification des stations
            elements.append(Paragraph(
                f"5/ Identification des stations hydrométriques du gouvernorat de {gouv}",
                styles['CustomHeading']
            ))
            elements.append(self._tableau_identification_stations(stations_reseau, gouv))
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(
                "<i>Note : les colonnes \"Mesures effectuées\" (DMJ, JC, JE, RS, TP) du tableau "
                "manuel ne sont pas incluses ici, cette donnée n'étant disponible dans aucune "
                "table de la base actuelle.</i>",
                styles['SectionTitle']
            ))

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
                    Paragraph("<b>2/ Étalonnage de la station :</b>", styles['SectionTitle']),
                    Paragraph("Valide du 01/01/2012 jusqu'à nos jours", styles['SectionTitle'])
                ]
                if etalonnage_path:
                    etalonnage_img = self._safe_image(etalonnage_path, width=5.8*cm, height=4.2*cm)
                    if etalonnage_img:
                        etalonnage_elements.append(etalonnage_img)
                else:
                    etalonnage_elements.append(Paragraph("Courbe d'étalonnage non disponible", styles['SectionTitle']))
                section_2 = Table([[item] for item in etalonnage_elements], colWidths=[5.9*cm])
                section_2.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

                # Débits journaliers (droite)
                SECTION_3_WIDTH = 10.1 * cm
                tableau_debits_display = self._daily_table_with_summary(tableau_debits)
                section_3_table = self.dataframe_to_table(
                    tableau_debits_display, font_size=4.5, total_width=SECTION_3_WIDTH - 0.2 * cm
                )
                if section_3_table is None:
                    section_3_table = Paragraph("Tableau des débits moyens journaliers non disponible", styles['SectionTitle'])

                section_3_content = [Paragraph("<b>3/ Débits moyens journaliers :</b>", styles['SectionTitle']), section_3_table]
                extremes_lines = self._extremes_lines(stats)
                if extremes_lines:
                    section_3_content.append(Spacer(1, 0.1 * cm))
                    section_3_content.extend(extremes_lines)

                section_3 = Table([[item] for item in section_3_content], colWidths=[SECTION_3_WIDTH])
                section_3.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

                top_panel = Table([[section_2, section_3]], colWidths=[6.2*cm, SECTION_3_WIDTH], hAlign="LEFT")
                top_panel.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))

                # Caracteristiques
                caracs_rows = [
                    ["Débit moyen annuel", f"{stats['debit_moyen']:.2f} m³/s" if pd.notna(stats.get('debit_moyen')) else ""],
                    ["Volume Total écoulé à la station", f"{stats['volume_total_hm3']:.2f} Hm³" if pd.notna(stats.get('volume_total_hm3')) else ""],
                    ["Hauteur de la lame d'eau écoulée", f"{stats['lame_ecoulee_mm']:.1f} mm" if pd.notna(stats.get('lame_ecoulee_mm')) else ""],
                ]
                section_4 = self._section_table("4/Caractéristiques hydrométriques de la station:", caracs_rows, col_widths=(7.2*cm, 8.7*cm), font_size=8)

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
                section_5_title = Paragraph("<b>5/Caractéristiques des crues</b>", styles['SectionTitle'])
                if crues_table is None:
                    crues_table = Paragraph("Aucune crue détectée", styles['SectionTitle'])

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