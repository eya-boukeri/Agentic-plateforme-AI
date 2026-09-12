"""
src/app/main.py
Plateforme Agentic AI - Annuaire Hydrometrique de la Tunisie (DGRE)

Deux espaces :
  - Tableau de bord : vue d'ensemble du reseau hydrometrique national
    (KPI, meilleures stations, crues recentes, carte du pays)
  - Assistant : chat en langage naturel qui pilote l'AgentOrchestrator
    (generation d'annuaire/cartes, recalcul de statistiques, questions
    sur les donnees, graphiques personnalises)

Design institutionnel/DGRE : pas d'emoji dans l'interface (icones SVG
sobres via theme.py) ; les messages renvoyes par l'orchestrateur/les
agents (qui contiennent des emojis, utiles cote console) sont nettoyes
avant affichage via strip_emoji().
"""

import base64
import os
import re
import socket
import sys
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_orchestrator import AgentOrchestrator
from theme import (
    apply_theme, hero_banner, section_title, kpi_card, feature_cards,
    COLOR_TEAL, COLOR_TERRACOTTA, COLOR_MUTED, icon_svg,
    render_floating_nav, render_sidebar_stars,
)
from utils.upload_importer import build_default_report

RACINE_PROJET = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# CONFIGURATION
# ============================================================

def get_db_config():
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'hydrometry'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
    }


st.set_page_config(
    page_title="Annuaire Hydrométrique - DGRE Tunisie",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner=False)
def _hero_image():
    """Cherche une photo de fond dans data/ (voir README de la charte
    graphique) ; retourne (base64, mime) ou (None, None) si absente - le
    theme reste alors en degrade uni, sans erreur."""
    candidats = [
        ("hero_barrage.jpg", "image/jpeg"),
        ("hero_barrage.jpeg", "image/jpeg"),
        ("hero_barrage.png", "image/png"),
        ("hero.jpg", "image/jpeg"),
        ("hero.jpeg", "image/jpeg"),
        ("hero.png", "image/png"),
    ]
    for nom, mime in candidats:
        chemin = os.path.join(RACINE_PROJET, "data", nom)
        if os.path.exists(chemin):
            with open(chemin, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii"), mime
    return None, None


_IMG_B64, _IMG_MIME = _hero_image()
apply_theme(_IMG_B64, _IMG_MIME)


@st.cache_resource(show_spinner=False)
def get_orchestrator():
    return AgentOrchestrator(get_db_config())


orchestrator = get_orchestrator()


# ============================================================
# UTILITAIRES D'AFFICHAGE
# ============================================================

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002100-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0001F1E6-\U0001F1FF"
    "️‍"
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(texte):
    """Retire les emojis des textes renvoyes par les agents (utiles cote
    console/logs, mais hors charte graphique institutionnelle de l'UI)."""
    if not texte:
        return texte
    nettoye = _EMOJI_PATTERN.sub("", texte)
    nettoye = re.sub(r'[ \t]{2,}', ' ', nettoye)
    nettoye = re.sub(r'\n[ \t]+', '\n', nettoye)
    nettoye = re.sub(r'^[ \t]+', '', nettoye, flags=re.MULTILINE)
    return nettoye.strip()


def fmt_nombre(valeur, decimales=1, defaut="—"):
    if valeur is None:
        return defaut
    try:
        valeur = float(valeur)
    except (TypeError, ValueError):
        return defaut
    if valeur != valeur:  # NaN (les agrégats SQL sur des colonnes NULL remontent en NaN, pas None)
        return defaut
    texte = f"{valeur:,.{decimales}f}"
    return texte.replace(",", " ").replace(".", ",") if decimales else texte.replace(",", " ")


def _hero(title, subtitle, tag=None):
    hero_banner(title, subtitle, tag=tag, background_image_b64=_IMG_B64, image_mime=_IMG_MIME or "image/jpeg")


def _tcp_check(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} joignable"
    except Exception as exc:
        return False, str(exc)


@st.cache_data(show_spinner=False, ttl=20)
def _health_snapshot():
    db = get_db_config()
    db_ok, db_detail = _tcp_check(db["host"], db["port"])

    try:
        llm = orchestrator._get_llm()
        llm_status = llm.get_status() if hasattr(llm, "get_status") else {}
    except Exception as exc:
        llm_status = {
            "available": False,
            "model_loaded": False,
            "model": os.getenv("LLM_MODEL", "hydrometrie"),
            "host": os.getenv("LLM_HOST", "http://localhost:11434"),
            "status_message": f"Erreur d'initialisation: {exc}",
            "last_check": None,
        }

    loaded_agents = []
    for name, agent in orchestrator.agents.items():
        loaded_agents.append(name)

    return {
        "db": {
            "ok": db_ok,
            "value": "OK" if db_ok else "KO",
            "detail": db_detail,
            "state": "ok" if db_ok else "error",
            "state_label": "Opérationnel" if db_ok else "Indisponible",
        },
        "llm": {
            "ok": bool(llm_status.get("available")),
            "value": "OK" if llm_status.get("available") else "KO",
            "detail": llm_status.get("status_message", ""),
            "state": "ok" if llm_status.get("available") else "warn",
            "state_label": "Disponible" if llm_status.get("available") else "À vérifier",
        },
        "model": {
            "ok": bool(llm_status.get("model_loaded")),
            "value": llm_status.get("model", "hydrometrie"),
            "detail": f"Hôte: {llm_status.get('host', '')}",
            "state": "ok" if llm_status.get("model_loaded") else "warn",
            "state_label": "Chargé" if llm_status.get("model_loaded") else "Absent",
        },
        "agents": {
            "ok": True,
            "value": str(len(loaded_agents)),
            "detail": ", ".join(loaded_agents) if loaded_agents else "Aucun agent chargé pour l'instant",
            "state": "ok",
            "state_label": "En mémoire",
        },
        "checked_at": datetime.now().strftime("%H:%M:%S"),
    }


def render_health_panel():
    snapshot = _health_snapshot()
    st.caption(f"État contrôlé à {snapshot['checked_at']}")


def render_status_strip():
    snapshot = _health_snapshot()
    st.markdown(
        f'''
        <div class="status-strip">
            <div class="status-chip {snapshot["db"]["state"]}"><strong>Base</strong><span>{snapshot["db"]["state_label"]}</span></div>
            <div class="status-chip {snapshot["llm"]["state"]}"><strong>Ollama</strong><span>{snapshot["llm"]["state_label"]}</span></div>
            <div class="status-chip {snapshot["model"]["state"]}"><strong>Modèle</strong><span>{snapshot["model"]["state_label"]}</span></div>
            <div class="status-chip ok"><strong>Agents</strong><span>{snapshot["agents"]["value"]} chargés</span></div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_quick_launch():
    cols = st.columns(4)
    actions = [
        "Génère-moi l'annuaire 2019",
        "Recalculer les statistiques 2024",
        "Carte hydrométrique de Béja",
        "Crues les plus importantes",
    ]
    for col, action in zip(cols, actions):
        with col:
            if st.button(action, width="stretch", key=f"quick_{action}"):
                _executer_requete(action)


# ============================================================
# IMPORT DE FICHIERS (bouton bien visible, panneau depliable)
# ============================================================

def render_import_section():
    """Bloc d'import affiché comme un vrai bouton d'action plutôt qu'un
    simple expander discret. Un clic ouvre un panneau dédié avec le
    file_uploader (taille max définie dans .streamlit/config.toml)."""
    if "show_import_panel" not in st.session_state:
        st.session_state.show_import_panel = False

    st.markdown('<div class="import-launch-btn">', unsafe_allow_html=True)
    label = (
        "Fermer l'import de fichiers"
        if st.session_state.show_import_panel
        else "Importer des fichiers de débits (.xls, .xlsx, .csv)"
    )
    if st.button(label, width="stretch", key="toggle_import_panel"):
        st.session_state.show_import_panel = not st.session_state.show_import_panel
    st.markdown('</div>', unsafe_allow_html=True)

    if not st.session_state.show_import_panel:
        return

    st.markdown('<div class="import-panel">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="import-panel-title">{icon_svg("upload", 20)}'
        f'<span>Actualiser la base de données depuis des fichiers</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Déposez un ou plusieurs fichiers .xls, .xlsx ou .csv contenant des débits. "
        "Le système essaye de faire la correspondance des stations puis insère seulement les nouvelles lignes."
    )
    fichiers_uploades = st.file_uploader(
        "Joindre des fichiers",
        type=["xls", "xlsx", "csv"],
        accept_multiple_files=True,
        label_visibility="visible",
    )
    confirmer = st.checkbox("Je confirme l'import dans la base", value=False)
    lancer_import = st.button("Lancer l'import", width="stretch", disabled=not fichiers_uploades)

    if lancer_import:
        if not fichiers_uploades:
            st.warning("Ajoutez au moins un fichier avant de lancer l'import.")
        elif not confirmer:
            st.warning("Cochez la confirmation avant d'écrire dans la base.")
        else:
            with st.spinner("Analyse et import en cours…"):
                fichiers_temp = []
                upload_dir = os.path.join(RACINE_PROJET, "data", "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                for fichier in fichiers_uploades:
                    cible = os.path.join(upload_dir, fichier.name)
                    with open(cible, "wb") as f:
                        f.write(fichier.getbuffer())
                    fichiers_temp.append(cible)

                try:
                    rapport = build_default_report(fichiers=fichiers_temp, confirmer=True)
                    if rapport["statut"] == "importe":
                        st.success(
                            f"Import réussi: {rapport['lignes_inserees']} lignes insérées, "
                            f"{rapport['lignes_ignorees']} déjà présentes ignorées."
                        )
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.rerun()
                    elif rapport["statut"] == "aucune_nouvelle_donnee":
                        st.info("Aucune nouvelle donnée à insérer, tout est déjà en base.")
                    elif rapport["statut"] == "bloque":
                        st.error("L'import a été bloqué à cause de correspondances douteuses.")
                        for entree in rapport["douteuses"][:10]:
                            st.write(f"- {entree['nom_excel']} -> {entree['code_station']} ({entree['nom_db']}) [score={entree['score']:.2f}]")
                    else:
                        st.warning(f"Import non terminé: {rapport['statut']}")
                except Exception as exc:
                    st.error(f"Erreur pendant l'import: {exc}")
    st.markdown('</div>', unsafe_allow_html=True)


# ============================================================
# TABLEAU DE BORD
# ============================================================

@st.cache_data(show_spinner=False, ttl=30)
def _charger_donnees_dashboard():
    rag = orchestrator.get_agent('rag').rag
    stats = rag.get_global_stats()
    meilleures = rag.get_best_stations(critere="debit_moyen", limit=10)
    crues = rag.get_crues(limit=6)
    gouvernorats = rag.get_gouvernorats_list()
    return {
        'stats': stats[0] if stats else {},
        'meilleures': meilleures or [],
        'crues': crues or [],
        'nb_gouvernorats_liste': len(gouvernorats or []),
    }


@st.cache_resource(show_spinner="Génération de la carte du réseau national…")
def _carte_pays():
    try:
        from agents.agent_cartographie import AgentCartographie
        carto = AgentCartographie()
        return carto.carte_pays()
    except Exception:
        return None


def render_dashboard():
    _hero(
        "Annuaire Hydrométrique de Tunisie",
        "Vue d'ensemble du réseau hydrométrique national — débits, crues et "
        "ressources en eau de surface, gouvernorat par gouvernorat.",
        tag="Direction Générale des Ressources en Eau",
    )

    try:
        donnees = _charger_donnees_dashboard()
    except Exception as e:
        st.error(f"Impossible de charger les données du tableau de bord : {e}")
        return

    stats = donnees['stats']

    render_status_strip()

    col_ref, _ = st.columns([2, 5])
    with col_ref:
        if st.button("🔄 Actualiser les données", key="btn_refresh_dashboard"):
            st.cache_data.clear()
            st.rerun()

    render_import_section()

    if not stats:
        st.info("Aucune donnée statistique disponible pour le moment. "
                "Importez des données puis lancez un recalcul depuis l'Assistant.")
        return

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        kpi_card("pin", "Stations", int(stats.get('nb_stations') or 0))
    with col2:
        kpi_card("building", "Gouvernorats", int(stats.get('nb_gouvernorats') or 0))
    with col3:
        kpi_card("droplet", "Débit moyen (m³/s)", fmt_nombre(stats.get('debit_moyen_global')), accent=True)
    with col4:
        kpi_card("wave", "Débit max (m³/s)", fmt_nombre(stats.get('debit_max_global')), accent=True)
    with col5:
        kpi_card("bucket", "Volume total (Hm³)", fmt_nombre(stats.get('volume_total_global'), 0))

    annee_min, annee_max = stats.get('annee_min'), stats.get('annee_max')
    if annee_min and annee_max:
        st.caption(f"Période couverte : {int(annee_min)} – {int(annee_max)} · "
                    f"Taux de remplissage moyen : {fmt_nombre(stats.get('taux_remplissage_moyen'))}%")

    left, right = st.columns([3, 2])

    with left:
        section_title("trophy", "Meilleures stations (débit moyen)")
        if donnees['meilleures']:
            df = pd.DataFrame(donnees['meilleures']).head(10)
            _bar_chart_stations(df)
        else:
            st.caption("Aucune donnée de débit disponible.")

    with right:
        section_title("alert", "Crues les plus importantes")
        if donnees['crues']:
            df_crues = pd.DataFrame(donnees['crues'])
            colonnes = [c for c in ['station', 'gouvernorat', 'annee', 'debit_max_m3s'] if c in df_crues.columns]
            df_crues = df_crues[colonnes].copy()
            if 'annee' in df_crues.columns:
                df_crues['annee'] = df_crues['annee'].apply(
                    lambda v: str(int(v)) if pd.notna(v) else "—"
                )
            if 'debit_max_m3s' in df_crues.columns:
                df_crues['debit_max_m3s'] = df_crues['debit_max_m3s'].apply(lambda v: fmt_nombre(v, 2))
            st.dataframe(
                df_crues.rename(columns={
                    'station': 'Station', 'gouvernorat': 'Gouvernorat',
                    'annee': 'Année', 'debit_max_m3s': 'Débit max (m³/s)'
                }),
                hide_index=True, width="stretch", height=300,
            )
        else:
            st.caption("Aucune crue enregistrée.")

    section_title("map", "Réseau hydrométrique national")
    carte = _carte_pays()
    if carte and os.path.exists(carte):
        st.image(carte, width="stretch",
                  caption="Découpage administratif, régions hydrographiques et cours d'eau de Tunisie")
    else:
        st.caption("Carte indisponible (données SIG manquantes).")


def _bar_chart_stations(df):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    valeurs = df['debit_moyen'].astype(float)
    couleurs = [COLOR_TERRACOTTA if v == valeurs.max() else COLOR_TEAL for v in valeurs]
    ax.barh(df['nom'], valeurs, color=couleurs, height=0.6)
    ax.invert_yaxis()
    ax.set_xlabel("Débit moyen (m³/s)", color=COLOR_MUTED, fontsize=9)
    ax.tick_params(colors=COLOR_MUTED, labelsize=8)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_MUTED)
    ax.grid(axis="x", linewidth=0.4, alpha=0.35)
    fig.tight_layout()
    st.pyplot(fig, width="stretch")


# ============================================================
# ASSISTANT (CHAT)
# ============================================================

SUGGESTIONS = [
    "Génère-moi l'annuaire 2019",
    "Quel gouvernorat a le plus grand débit ?",
    "Génère-moi la carte hydrométrique de Béja",
    "Donne-moi les informations sur les crues",
]

MESSAGE_BIENVENUE = (
    "Bonjour, je suis l'assistant hydrométrique de la DGRE.\n\n"
    "Je peux générer l'annuaire PDF, produire des cartes du réseau, recalculer des "
    "statistiques ou répondre à vos questions sur les débits, crues et stations. "
    "Posez votre question en langage naturel ci-dessous."
)


def _executer_requete(texte):
    st.session_state.messages.append({"role": "user", "content": texte})
    with st.spinner("Traitement de votre demande…"):
        try:
            resultat = orchestrator.execute(texte)
        except Exception as e:
            resultat = {"status": "error", "message": f"Erreur inattendue : {e}"}

    contenu = strip_emoji(
        resultat.get("message") or resultat.get("answer") or "Je n'ai pas de réponse à fournir."
    )
    message_assistant = {"role": "assistant", "content": contenu}
    if resultat.get("image_path"):
        message_assistant["image_path"] = resultat["image_path"]
    if resultat.get("pdf_path"):
        message_assistant["pdf_path"] = resultat["pdf_path"]
    st.session_state.messages.append(message_assistant)


def render_chat():
    _hero(
        "Assistant Hydrométrique",
        "Générez l'annuaire, des cartes ou des graphiques, recalculez des "
        "statistiques ou posez vos questions — en langage naturel.",
        tag="Orchestrateur agentic DGRE",
    )

    feature_cards([
        {
            "title": "Questions en langage naturel",
            "text": "Interrogez la plateforme comme un expert métier, sans apprendre une syntaxe particulière.",
        },
        {
            "title": "Génération documentaire",
            "text": "Produisez l’annuaire hydrométrique, des exports PDF et des éléments utiles à la diffusion interne.",
        },
        {
            "title": "Cartographie et calculs",
            "text": "Lancez la production de cartes, les recalculs et les analyses directement depuis ce panneau.",
        },
    ])

    render_status_strip()

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": MESSAGE_BIENVENUE}]

    section_title("lightbulb", "Suggestions")
    cols = st.columns(len(SUGGESTIONS))
    for col, suggestion in zip(cols, SUGGESTIONS):
        if col.button(suggestion, width="stretch", key=f"sugg_{suggestion}"):
            _executer_requete(suggestion)

    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            image_path = message.get("image_path")
            if image_path and os.path.exists(image_path):
                st.image(image_path, width="stretch")
            pdf_path = message.get("pdf_path")
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "Télécharger le PDF", data=f.read(),
                        file_name=os.path.basename(pdf_path), mime="application/pdf",
                        key=f"dl_{i}",
                    )

    prompt = st.chat_input("Écrivez votre question ou votre demande…")
    if prompt:
        _executer_requete(prompt)
        st.rerun()


# ============================================================
# NAVIGATION
# ============================================================

PAGE_DASHBOARD = "Tableau de bord"
PAGE_ASSISTANT = "Assistant"

# Synchronisation bidirectionnelle fluide avec query_params (menu flottant et liens)
query_page = st.query_params.get("page", None)
if query_page:
    if query_page.lower() == "assistant":
        st.session_state["selected_page"] = PAGE_ASSISTANT
    elif query_page.lower() == "dashboard":
        st.session_state["selected_page"] = PAGE_DASHBOARD

if "selected_page" not in st.session_state:
    st.session_state["selected_page"] = PAGE_DASHBOARD

# Action de synchronisation / rafraîchissement depuis le menu flottant
if st.query_params.get("refresh") == "1":
    st.cache_data.clear()
    st.query_params.pop("refresh", None)
    st.toast("Données hydrométriques synchronisées avec la base !", icon="🌊")

with st.sidebar:
    render_sidebar_stars()
    st.markdown("## DGRE — Tunisie")
    st.caption("Plateforme Agentic AI · Ressources en eau")
    st.markdown("---")
    st.caption("Vue d'état")
    try:
        health = _health_snapshot()
        st.success("Services principaux accessibles" if health["db"]["ok"] and health["llm"]["ok"] else "Certains services demandent vérification")
        st.caption(f"DB: {health['db']['state_label']} · LLM: {health['llm']['state_label']} · Modèle: {health['model']['state_label']}")
    except Exception:
        st.warning("Impossible de calculer l'état de la plateforme")

    current_idx = 0 if st.session_state["selected_page"] == PAGE_DASHBOARD else 1
    page = st.radio(
        "Navigation", [PAGE_DASHBOARD, PAGE_ASSISTANT],
        index=current_idx,
        key="sidebar_nav_radio",
        label_visibility="collapsed",
    )
    if page != st.session_state["selected_page"]:
        st.session_state["selected_page"] = page
        st.query_params["page"] = "dashboard" if page == PAGE_DASHBOARD else "assistant"
        st.rerun()

    st.markdown("---")
    st.caption(
        "Cette plateforme génère automatiquement l'annuaire hydrométrique "
        "de la DGRE et répond aux questions sur le réseau national : débits, "
        "crues, stations et ressources en eau de surface."
    )
    st.markdown("---")
    st.caption("République Tunisienne · Direction Générale des Ressources en Eau")

current_page = st.session_state["selected_page"]

# Affichage du menu pilule glassmorphic flottant (Uiverse.io by mymiamo)
render_floating_nav(current_page)

if current_page == PAGE_DASHBOARD:
    render_dashboard()
else:
    render_chat()