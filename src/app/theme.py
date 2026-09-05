"""
src/app/theme.py
Identite visuelle "hydrologie tunisienne" de l'application Streamlit :
bleu eau (Mediterranee / barrages) + terracotta/ocre (paysages du Sud),
motif de vague en bas du bandeau d'en-tete. Centralise ici pour que
main.py reste focalise sur la logique applicative.

Design volontairement sans emoji (registre institutionnel/DGRE) : les
icones sont de petits SVG traits fins (style "line icon"), pas des
pictogrammes colores.
"""

import streamlit as st

# ============================================================
# PALETTE
# ============================================================
COLOR_DEEP = "#0b4f6c"        # bleu eau profond (bandeau, titres)
COLOR_PRIMARY = "#136e8b"     # bleu principal (boutons, liens, accents)
COLOR_TEAL = "#159895"        # turquoise (degrade bandeau, graphiques)
COLOR_TERRACOTTA = "#c1673b"  # terracotta saharien (accent chaud)
COLOR_OCRE = "#e0a458"        # ocre sable (accent secondaire, alertes douces)
COLOR_SAND = "#f7f2e9"        # fond de page (sable clair)
COLOR_CARD = "#ffffff"        # fond des cartes
COLOR_TEXT = "#122b33"        # texte principal
COLOR_MUTED = "#5b7480"       # texte secondaire

CHART_PALETTE = [COLOR_TEAL, COLOR_TERRACOTTA, COLOR_PRIMARY, COLOR_OCRE, COLOR_DEEP]


# ============================================================
# ICONES (SVG traits fins, remplacent les emojis)
# ============================================================
_ICON_PATHS = {
    "pin": '<circle cx="12" cy="10" r="3"/><path d="M12 21s7-7.5 7-12a7 7 0 1 0-14 0c0 4.5 7 12 7 12z"/>',
    "building": '<path d="M12 3l9 5H3l9-5z"/><path d="M4 10h16M5 10v9M9 10v9M15 10v9M19 10v9M3 21h18"/>',
    "droplet": '<path d="M12 2s7 8.8 7 13.2A7 7 0 1 1 5 15.2C5 10.8 12 2 12 2z"/>',
    "wave": '<path d="M2 12c1.4-2.8 3.4-2.8 4.8 0s3.4 2.8 4.8 0 3.4-2.8 4.8 0 3.4 2.8 4.8 0"/><path d="M2 18c1.4-2.8 3.4-2.8 4.8 0s3.4 2.8 4.8 0 3.4-2.8 4.8 0 3.4 2.8 4.8 0"/>',
    "bucket": '<path d="M5 7h14l-1.6 12.2A2 2 0 0 1 15.4 21H8.6a2 2 0 0 1-2-1.8L5 7z"/><path d="M4 7l2-3.5h12L20 7"/>',
    "trophy": '<path d="M7 4h10v4a5 5 0 0 1-10 0V4z"/><path d="M7 5H3v1a4 4 0 0 0 4 4M17 5h4v1a4 4 0 0 1-4 4"/><path d="M12 14v3M8 21h8M10 17h4v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-2z"/>',
    "alert": '<path d="M10.3 4.1 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 4.1a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
    "map": '<path d="M3 6.5l6-2 6 2 6-2v14l-6 2-6-2-6 2v-14z"/><path d="M9 4.5v14M15 6.5v14"/>',
    "lightbulb": '<path d="M9 18h6M10 22h4M12 2a6.5 6.5 0 0 0-4.2 11.5c.7.6 1.2 1.5 1.2 2.5h6c0-1 .5-1.9 1.2-2.5A6.5 6.5 0 0 0 12 2z"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "info": '<circle cx="12" cy="12" r="9.5"/><path d="M12 11v5.5M12 7.7v.1"/>',
    "flag": '<path d="M5 21V4"/><path d="M5 4h13l-2.5 4L18 12H5"/>',
}


def icon_svg(name, size=20, color="currentColor", stroke_width=1.7):
    """Petit SVG en ligne (24x24) — remplace les emojis dans l'UI."""
    inner = _ICON_PATHS.get(name, "")
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round" style="vertical-align:middle;flex-shrink:0">{inner}</svg>'
    )


def apply_theme(bg_image_b64=None, bg_image_mime="image/jpeg"):
    """Injecte le CSS du theme dans la page Streamlit courante.

    Si `bg_image_b64` est fourni, la photo sert de fond a l'ensemble de la
    plateforme (pas seulement au bandeau d'en-tete), attenuee par un voile
    sable pour garder le contenu (cartes, tableaux, texte) parfaitement
    lisible.
    """
    if bg_image_b64:
        app_background = (
            f"background-color: {COLOR_SAND};"
            "background-image: linear-gradient(rgba(247,242,233,0.92), rgba(247,242,233,0.96)), "
            f"url('data:{bg_image_mime};base64,{bg_image_b64}');"
            "background-size: cover;"
            "background-position: center top;"
            "background-attachment: fixed;"
            "background-repeat: no-repeat;"
        )
    else:
        app_background = f"background: {COLOR_SAND};"

    st.markdown(
        f"""
        <style>
        .main .block-container {{
            max-width: 1320px;
            padding-top: 1.5rem;
            padding-bottom: 2.5rem;
        }}

        .stApp {{
            {app_background}
            color: {COLOR_TEXT};
        }}

        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {COLOR_DEEP} 0%, #0d3a4d 55%, #0f5165 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }}
        section[data-testid="stSidebar"] * {{
            color: #eaf4f6 !important;
        }}
        section[data-testid="stSidebar"] hr {{
            border-color: rgba(255,255,255,0.18);
        }}
        section[data-testid="stSidebar"] .stRadio [role="radiogroup"] {{
            gap: 0.45rem;
        }}
        section[data-testid="stSidebar"] .stRadio label {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            padding: 0.35rem 0.6rem;
        }}

        .feature-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
            margin: 1rem 0 0.35rem 0;
        }}
        .feature-card, .health-card, .status-chip {{
            position: relative;
            overflow: hidden;
        }}
        .feature-card::before, .health-card::before, .status-chip::before {{
            content: "";
            position: absolute;
            inset: 0 auto auto 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, {COLOR_TEAL}, {COLOR_TERRACOTTA});
            opacity: 0.85;
        }}
        .feature-card {{
            background: rgba(255,255,255,0.78);
            border: 1px solid rgba(19,110,139,0.12);
            border-radius: 18px;
            padding: 1rem 1rem 0.95rem 1rem;
            box-shadow: 0 10px 30px rgba(11,79,108,0.08);
            backdrop-filter: blur(8px);
            height: 100%;
        }}
        .feature-card strong {{
            display: block;
            font-size: 0.98rem;
            color: {COLOR_DEEP};
            margin-bottom: 0.35rem;
        }}
        .feature-card p {{
            margin: 0;
            color: {COLOR_MUTED};
            line-height: 1.5;
            font-size: 0.92rem;
        }}

        .status-strip {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.9rem 0 0.2rem 0;
        }}
        .status-chip {{
            background: rgba(255,255,255,0.84);
            border: 1px solid rgba(19,110,139,0.1);
            border-radius: 999px;
            padding: 0.75rem 0.95rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            box-shadow: 0 8px 20px rgba(11,79,108,0.07);
        }}
        .status-chip strong {{
            font-size: 0.82rem;
            color: {COLOR_DEEP};
        }}
        .status-chip span {{
            font-size: 0.82rem;
            font-weight: 700;
            color: {COLOR_MUTED};
        }}
        .status-chip.ok span {{ color: {COLOR_TEAL}; }}
        .status-chip.warn span {{ color: {COLOR_OCRE}; }}
        .status-chip.error span {{ color: {COLOR_TERRACOTTA}; }}

        .quick-launch {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.9rem 0 0.3rem 0;
        }}
        .quick-launch .stButton > button {{
            width: 100%;
            padding: 0.7rem 0.9rem;
            min-height: 2.7rem;
        }}

        .hero-banner .hero-tag {{
            box-shadow: 0 10px 22px rgba(0,0,0,0.08);
        }}

        .hero-banner .hero-subtitle {{
            text-shadow: 0 1px 0 rgba(0,0,0,0.05);
        }}

        .health-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.8rem;
            margin: 0.2rem 0 0.2rem 0;
        }}
        .health-card {{
            background: rgba(255,255,255,0.86);
            border: 1px solid rgba(19,110,139,0.1);
            border-radius: 16px;
            padding: 0.95rem 1rem;
            box-shadow: 0 10px 24px rgba(11,79,108,0.08);
        }}
        .health-label {{
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.55px;
            color: {COLOR_MUTED};
            margin-bottom: 0.35rem;
        }}
        .health-value {{
            font-weight: 700;
            font-size: 0.98rem;
            color: {COLOR_DEEP};
            margin-bottom: 0.2rem;
        }}
        .health-detail {{
            color: {COLOR_MUTED};
            font-size: 0.86rem;
            line-height: 1.4;
        }}
        .health-pill {{
            display: inline-block;
            margin-top: 0.55rem;
            padding: 0.22rem 0.68rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.35px;
        }}
        .health-pill.ok {{ background: rgba(21,152,149,0.12); color: {COLOR_TEAL}; }}
        .health-pill.warn {{ background: rgba(224,164,88,0.16); color: {COLOR_OCRE}; }}
        .health-pill.error {{ background: rgba(193,103,59,0.14); color: {COLOR_TERRACOTTA}; }}

        /* Bandeau d'en-tete avec vague */
        .hero-banner {{
            position: relative;
            background:
                radial-gradient(circle at top left, rgba(255,255,255,0.16), transparent 30%),
                linear-gradient(120deg, {COLOR_DEEP} 0%, {COLOR_TEAL} 100%);
            border-radius: 26px;
            padding: 2.5rem 2.5rem 3.7rem 2.5rem;
            color: #ffffff;
            overflow: hidden;
            margin-bottom: 1.6rem;
            box-shadow: 0 20px 42px rgba(11,79,108,0.22);
            min-height: 9.5rem;
        }}
        .hero-banner.with-photo {{
            background: linear-gradient(120deg, rgba(8,54,74,0.94) 0%, rgba(17,110,113,0.84) 100%);
        }}
        .hero-photo {{
            position: absolute;
            inset: 0;
            background-size: cover;
            background-position: center 40%;
            z-index: 0;
            filter: saturate(0.95) contrast(0.95);
        }}
        .hero-banner::after {{
            content: "";
            position: absolute; left: 0; right: 0; bottom: -2px; height: 42px;
            background-repeat: repeat-x;
            background-size: 1200px 42px;
            background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 120' preserveAspectRatio='none'><path d='M0,40 C300,100 900,0 1200,50 L1200,120 L0,120 Z' fill='%23f7f2e9'/></svg>");
            z-index: 2;
        }}
        .hero-content {{
            position: relative;
            z-index: 1;
        }}
        .hero-title {{
            font-size: 2.05rem;
            font-weight: 700;
            margin: 0 0 0.35rem 0;
            letter-spacing: 0.2px;
        }}
        .hero-subtitle {{
            font-size: 1.04rem;
            opacity: 0.94;
            margin: 0;
            max-width: 68ch;
            line-height: 1.5;
        }}
        .hero-tag {{
            display: inline-block;
            background: rgba(255,255,255,0.15);
            border: 1px solid rgba(255,255,255,0.38);
            padding: 0.34rem 0.82rem;
            border-radius: 999px;
            font-size: 0.72rem;
            margin-top: 0.9rem;
            letter-spacing: 0.6px;
            text-transform: uppercase;
        }}

        /* Cartes KPI */
        .kpi-card {{
            background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(255,255,255,0.88) 100%);
            border-radius: 18px;
            padding: 1rem 1.05rem 1.05rem 1.05rem;
            border: 1px solid rgba(19,110,139,0.1);
            border-top: 3px solid {COLOR_TEAL};
            box-shadow: 0 8px 24px rgba(11,79,108,0.08);
            height: 100%;
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 14px 28px rgba(11,79,108,0.12);
        }}
        .kpi-card.accent {{ border-top-color: {COLOR_TERRACOTTA}; }}
        .kpi-icon {{ color: {COLOR_TEAL}; margin-bottom: 0.35rem; }}
        .kpi-card.accent .kpi-icon {{ color: {COLOR_TERRACOTTA}; }}
        .kpi-label {{
            font-size: 0.76rem;
            color: {COLOR_MUTED};
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 0.2rem;
        }}
        .kpi-value {{
            font-size: 1.65rem;
            font-weight: 700;
            color: {COLOR_DEEP};
            line-height: 1.2;
        }}

        .section-title {{
            color: {COLOR_DEEP};
            font-weight: 700;
            font-size: 1.08rem;
            margin: 1.4rem 0 0.6rem 0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .section-title svg {{ color: {COLOR_TEAL}; }}

        /* Boutons */
        .stButton > button, .stDownloadButton > button {{
            background: linear-gradient(135deg, {COLOR_PRIMARY} 0%, {COLOR_TEAL} 100%);
            color: #ffffff;
            border: none;
            border-radius: 999px;
            font-weight: 600;
            transition: transform 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
            box-shadow: 0 8px 20px rgba(19,110,139,0.22);
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            background: linear-gradient(135deg, {COLOR_TERRACOTTA} 0%, {COLOR_OCRE} 100%);
            color: #ffffff;
            transform: translateY(-1px);
            box-shadow: 0 12px 24px rgba(193,103,59,0.22);
        }}
        .stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
            outline: 3px solid rgba(21,152,149,0.28);
            outline-offset: 2px;
        }}

        /* Onglets / radio de navigation */
        div[role="radiogroup"] label {{
            border-radius: 6px;
        }}

        [data-testid="stChatMessage"] {{
            background: {COLOR_CARD};
            border-radius: 18px;
            box-shadow: 0 8px 24px rgba(11,79,108,0.08);
            border: 1px solid rgba(19,110,139,0.08);
        }}

        [data-testid="stChatInput"] {{
            background: rgba(255,255,255,0.9);
            border-radius: 18px;
            box-shadow: 0 10px 28px rgba(11,79,108,0.08);
            border: 1px solid rgba(19,110,139,0.1);
            backdrop-filter: blur(8px);
        }}

        [data-testid="stDataFrame"] {{
            border-radius: 16px;
            overflow: hidden;
        }}

        footer, #MainMenu {{ visibility: hidden; }}

        @media (max-width: 1100px) {{
            .health-grid,
            .feature-grid,
            .status-strip,
            .quick-launch {{
                grid-template-columns: 1fr;
            }}
            .main .block-container {{
                max-width: 100%;
                padding-left: 1rem;
                padding-right: 1rem;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero_banner(title, subtitle, tag=None, background_image_b64=None, image_mime="image/jpeg"):
    tag_html = f'<div class="hero-tag">{tag}</div>' if tag else ""
    photo_html = ""
    extra_class = ""
    if background_image_b64:
        extra_class = " with-photo"
        photo_html = (
            f'<div class="hero-photo" '
            f'style="background-image:url(\'data:{image_mime};base64,{background_image_b64}\')"></div>'
        )
    st.markdown(
        f"""
        <div class="hero-banner{extra_class}">
            {photo_html}
            <div class="hero-content">
                <div class="hero-title">{title}</div>
                <p class="hero-subtitle">{subtitle}</p>
                {tag_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(icon_name, text):
    st.markdown(
        f'<div class="section-title">{icon_svg(icon_name, 19)}<span>{text}</span></div>',
        unsafe_allow_html=True,
    )


def kpi_card(icon_name, label, value, accent=False):
    css_class = "kpi-card accent" if accent else "kpi-card"
    st.markdown(
        f"""
        <div class="{css_class}">
            <div class="kpi-icon">{icon_svg(icon_name, 22)}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def feature_cards(items):
    columns = st.columns(len(items))
    for col, item in zip(columns, items):
        with col:
            st.markdown(
                f'''<div class="feature-card"><strong>{item["title"]}</strong><p>{item["text"]}</p></div>''',
                unsafe_allow_html=True,
            )


def health_cards(items):
    columns = st.columns(len(items))
    for col, item in zip(columns, items):
        pill_class = item.get("state", "warn")
        with col:
            st.markdown(
                f'''<div class="health-card"><div class="health-label">{item["label"]}</div><div class="health-value">{item["value"]}</div><div class="health-detail">{item["detail"]}</div><span class="health-pill {pill_class}">{item["state_label"]}</span></div>''',
                unsafe_allow_html=True,
            )
