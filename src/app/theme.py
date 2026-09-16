"""
src/app/theme.py
Identite visuelle "hydrologie tunisienne" de l'application Streamlit — V3,
registre clair et chic : fond gris-bleu poudre (doux, "charmant") au lieu
du bleu-nuit profond, accent bleu vif signature, touches terracotta/cuivre
pour la chaleur, sidebar sombre pour le contraste (look SaaS premium).

Design volontairement sans emoji (registre institutionnel/DGRE) : les
icones sont de petits SVG traits fins (style "line icon"), pas des
pictogrammes colores.

V3 — refonte claire :
  - fond principal clair, gris-bleu poudre doux (plutot que le bleu-nuit
    quasi-noir de la V2), avec la photo (si fournie) en lavis tres clair ;
  - accent signature bleu vif (boutons, liens, icones) + terracotta/ocre
    en second accent chaud pour la chaleur et le contraste "chic" ;
  - sidebar restee sombre : contraste marque, lisibilite, ancrage visuel ;
  - cartes "editoriales" : fond quasi-blanc, ombre douce, liseret fin
    plutot que le glassmorphism appuye de la V2 (garde uniquement sur le
    champ de chat, ou il a du sens visuellement) ;
  - couple typographique inchange (Fraunces / Inter).

V3.1 — ajustements demandes :
  - bloc d'import de fichiers transforme en vrai bouton, tres visible ;
  - cartes KPI allegees / plus fines (moins de padding, chiffres plus
    compacts) tout en gardant le liseret colore caracteristique.

V3.2 — effet "starfield" (Uiverse.io by amir_6539) applique a la sidebar :
  - le composant original est pense pour un fond plein ecran quasi noir ;
    ici seule la sidebar est de ce registre, donc les deux couches
    d'etoiles (::before / ::after) y sont scopees plutot que sur .stApp,
    pour eviter un semis de points blancs sur le fond clair du corps de
    page (aucun contraste, effet casse) ;
  - `clip-path` borne les etoiles a la largeur de la sidebar, meme si le
    canevas de coordonnees d'origine (jusqu'a ~2000px) suppose un ecran
    plein ; `isolation: isolate` sur la sidebar reproduit la meme
    correction d'empilement que sur .stApp (sinon son propre degrade se
    peint par-dessus les etoiles en z-index negatif).

V3.3 — starfield 3 couches :
  - ajout d'une troisieme couche d'etoiles (grosses, proches) pour
    renforcer l'effet de profondeur spatiale ;
  - vitesses de defilement differentes pour chaque couche (parallaxe) ;
  - element HTML dedie pour la 3eme couche.
"""

import streamlit as st

# ============================================================
# PALETTE
# ============================================================
COLOR_BG_SOFT = "#cfd9dd"      # gris-bleu poudre — fond principal ("charmant")
COLOR_BG_SOFT_LIGHT = "#e9eff1"  # variante plus claire (haut de degrade / cartes alt)
COLOR_DEEP = "#1c2b38"          # charbon-marine fonce — sidebar, titres forts, texte
COLOR_PRIMARY = "#1f6fd6"       # bleu vif signature (boutons, liens, accents) — logo Avilli
COLOR_PRIMARY_DARK = "#144f9e"  # bleu vif, variante foncee (degrades, hover)
COLOR_TEAL = "#159895"          # turquoise (graphiques, variete de palette)
COLOR_TERRACOTTA = "#c1673b"    # terracotta — accent chaud, contraste chic avec le bleu
COLOR_OCRE = "#e0a458"          # ocre sable — accent secondaire, alertes douces
COLOR_SAND = "#f4efe4"          # ton sable (liseres, fonds alternes)
COLOR_CARD = "#ffffff"          # fond plein des cartes (registre "editorial")
COLOR_TEXT = "#28343f"          # texte principal (charbon-marine)
COLOR_MUTED = "#61727d"         # texte secondaire

CHART_PALETTE = [COLOR_PRIMARY, COLOR_TERRACOTTA, COLOR_TEAL, COLOR_OCRE, COLOR_DEEP]


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
    "upload": '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
}


def icon_svg(name, size=20, color="currentColor", stroke_width=1.7):
    """Petit SVG en ligne (24x24) — remplace les emojis dans l'UI."""
    inner = _ICON_PATHS.get(name, "")
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round" style="vertical-align:middle;flex-shrink:0">{inner}</svg>'
    )


try:
    from star_data import STARS_1, STARS_2, STARS_3, SIDEBAR_LOOP_STARS_1, SIDEBAR_LOOP_STARS_2, SIDEBAR_LOOP_STARS_3
except ImportError:
    from app.star_data import STARS_1, STARS_2, STARS_3, SIDEBAR_LOOP_STARS_1, SIDEBAR_LOOP_STARS_2, SIDEBAR_LOOP_STARS_3

# ============================================================
# STARFIELD (Uiverse.io by amir_6539 - 3 couches cosmiques)
# ============================================================
STAR_CSS = ""



def apply_theme(bg_image_b64=None, bg_image_mime="image/jpeg"):
    """Injecte le CSS du theme dans la page Streamlit courante.

    Registre clair et chic : fond gris-bleu poudre en continu sur toute la
    plateforme (au lieu du bleu-nuit V2). La photo (si fournie) devient un
    lavis tres doux, presque une texture, plutot qu'un fond sombre — pour
    garder la legerete de la palette Avilli tout en restant raccordee a
    l'identite "hydrologie" (bleu + terracotta). La sidebar, seule zone
    sombre restante, porte un semis d'etoiles animees en 3 couches (V3.3).
    """
    if bg_image_b64:
        background_layers_css = f"""
.stApp::before {{
    content: "";
    position: fixed;
    inset: -30px;
    z-index: -2;
    background-image: url('data:{bg_image_mime};base64,{bg_image_b64}');
    background-size: cover;
    background-position: center center;
    background-repeat: no-repeat;
    filter: blur(6px) saturate(1.0);
    opacity: 0.85;               /* était 0.55 */
}}
.stApp::after {{
    content: "";
    position: fixed;
    inset: 0;
    z-index: -1;
    background-image: linear-gradient(
        160deg,
        rgba(207,217,221,0.55) 0%,   /* était 0.88 */
        rgba(233,239,241,0.6) 45%,   /* était 0.92 */
        rgba(207,217,221,0.65) 100%  /* était 0.94 */
    );
}}
.stApp {{
    background-color: {COLOR_BG_SOFT};
}}
"""
    else:
        background_layers_css = f"""
        .stApp {{
            background-color: {COLOR_BG_SOFT};
            background-image: radial-gradient(circle at 15% 0%, rgba(31,111,214,0.10), transparent 45%),
                linear-gradient(165deg, {COLOR_BG_SOFT_LIGHT} 0%, {COLOR_BG_SOFT} 55%, #c3ced3 100%);
            background-attachment: fixed;
        }}
        """

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,500&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap');

        :root {{
            --bg-soft: {COLOR_BG_SOFT};
            --deep: {COLOR_DEEP};
            --primary: {COLOR_PRIMARY};
            --primary-dark: {COLOR_PRIMARY_DARK};
            --teal: {COLOR_TEAL};
            --terracotta: {COLOR_TERRACOTTA};
            --ocre: {COLOR_OCRE};
            --sand: {COLOR_SAND};
            --text: {COLOR_TEXT};
            --muted: {COLOR_MUTED};
            --card-bg: rgba(255,255,255,0.9);
            --card-bg-strong: rgba(255,255,255,0.97);
            --card-border: rgba(28,43,56,0.09);
            --card-border-hover: rgba(28,43,56,0.09);
            --card-shadow: 0 4px 14px rgba(28,43,56,0.06);
            --card-shadow-hover: 0 22px 42px rgba(28,43,56,0.20);
            --glass-border: rgba(255, 255, 255, 0.22);
            --ease-spring: cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }}

        html, body, [class*="css"] {{
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
            overflow-anchor: none !important;
        }}

        .main, .stApp, [data-testid="stAppViewContainer"] {{
            overflow-anchor: none !important;
        }}

        .main .block-container {{
            max-width: 1320px;
            padding-top: 1.2rem;
            padding-bottom: 3rem;
        }}

        /* ---------- Fond continu (gris-bleu poudre + photo optionnelle tres claire) ---------- */
        {background_layers_css}
        .stApp {{
            color: {COLOR_TEXT};
            isolation: isolate;
        }}

        [data-testid="stHeader"] {{
            background: transparent;
        }}

        h1, h2, h3, .hero-title {{
            font-family: "Fraunces", Georgia, serif;
            letter-spacing: 0.1px;
        }}

        /* ---------- Masquage complet et definitif de la sidebar ---------- */
        section[data-testid="stSidebar"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"],
        button[data-testid="stSidebarCollapseButton"],
        header [data-testid="stSidebarCollapsedControl"],
        div[data-testid="stSidebarCollapseButton"] {{
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            pointer-events: none !important;
        }}

        /* ---------- Starfield (V3.3 - 3 couches) ---------- */
        {STAR_CSS}

        /* ---------- Menu Glassmorphic Flottant (Uiverse.io by mymiamo) ---------- */
        div[data-testid="stElementContainer"]:has(.menu-nav-wrapper) {{
            position: sticky !important;
            top: 10px !important;
            z-index: 999999 !important;
            width: 100% !important;
            display: flex !important;
            justify-content: center !important;
            pointer-events: none !important;
            margin-bottom: 0.6rem !important;
        }}

        .menu-nav-wrapper {{
            position: relative !important;
            width: 100% !important;
            display: flex !important;
            justify-content: center !important;
            pointer-events: none !important;
        }}

        .menu {{
            position: relative;
            width: min(920px, calc(100% - 32px));
            max-width: 920px;
            backdrop-filter: blur(18px) saturate(180%) contrast(140%);
            -webkit-backdrop-filter: blur(18px) saturate(180%) contrast(140%);
            background: rgba(16, 43, 70, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.28);
            box-shadow: 0 12px 36px rgba(0, 0, 0, 0.20), 0 0 28px rgba(31, 111, 214, 0.25);
            padding: 8px 12px;
            border-radius: 999px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            pointer-events: auto;
            transition: box-shadow 0.3s ease, border-color 0.3s ease, width 0.3s ease;
        }}

        .menu:hover {{
            box-shadow: 0 16px 42px rgba(0, 0, 0, 0.26), 0 0 38px rgba(31, 111, 214, 0.35);
            border-color: rgba(255, 255, 255, 0.42);
        }}

        .menu::after {{
            content: "";
            position: absolute;
            inset: 0;
            border-radius: inherit;
            box-shadow:
                inset 1px 1px 3px rgba(255, 255, 255, 0.4),
                inset -1px -1px 3px rgba(255, 255, 255, 0.2);
            pointer-events: none;
            z-index: -1;
        }}

        .menu a {{
            display: flex;
            flex-direction: row;
            align-items: center;
            justify-content: center;
            gap: 10px;
            flex: 1 1 0;
            min-width: 0;
            color: rgba(255, 255, 255, 0.92);
            text-decoration: none !important;
            padding: 10px 22px;
            border-radius: 999px;
            white-space: nowrap;
            -webkit-tap-highlight-color: transparent;
            transition:
                background 0.2s ease,
                color 0.2s ease,
                transform 0.18s ease,
                box-shadow 0.25s ease;
            cursor: pointer;
            user-select: none;
        }}

        .menu a:hover {{
            background-color: rgba(255, 255, 255, 0.18);
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.14);
            transform: translateY(-1px);
            color: #ffffff;
        }}

        .menu a svg {{
            width: 1.25rem;
            height: 1.25rem;
            font-size: 1.25rem;
            stroke: currentColor;
            flex-shrink: 0;
            transition: transform 0.2s ease;
        }}

        .menu a:hover svg {{
            transform: scale(1.1);
        }}

        .menu a span {{
            font-size: 0.92rem;
            font-weight: 600;
            line-height: 1.2;
            margin-top: 0;
            letter-spacing: 0.2px;
            white-space: nowrap;
        }}

        .menu a.active {{
            background: #ffffff;
            color: #144f9e !important;
            box-shadow: 0 6px 20px rgba(0, 40, 110, 0.28), inset 0 1px 1px rgba(255, 255, 255, 0.9);
            font-weight: 700;
        }}

        .menu a.active svg {{
            stroke: #144f9e;
        }}

        .menu a:active {{
            transform: scale(0.97);
        }}

        @media (max-width: 860px) {{
            .menu {{
                width: calc(100% - 16px);
                max-width: 100%;
                gap: 6px;
                padding: 6px 8px;
            }}
            .menu a {{
                padding: 8px 12px;
                gap: 6px;
            }}
            .menu a span {{
                font-size: 0.82rem;
            }}
            .menu a svg {{
                width: 1.1rem;
                height: 1.1rem;
            }}
        }}

        /* ---------- En-tête Institutionnel Officiel (Style data.gouv.fr / DSFR) ---------- */
        .dsfr-header-container {{
            width: 100%;
            background: rgba(255, 255, 255, 0.96);
            border-bottom: 2px solid rgba(28, 43, 56, 0.08);
            border-radius: 18px;
            padding: 0.9rem 1.6rem;
            margin-top: 0.4rem;
            margin-bottom: 1.2rem;
            box-shadow: 0 4px 22px rgba(16, 35, 49, 0.06);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1.5rem;
            position: relative;
            z-index: 50;
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            border: 1px solid rgba(28, 43, 56, 0.07);
        }}

        .dsfr-header-left {{
            display: flex;
            align-items: center;
            gap: 1.5rem;
            flex-wrap: wrap;
        }}

        /* Bloc Marque République Tunisienne (exact style Marianne data.gouv.fr) */
        .marianne-brand-block {{
            display: flex;
            flex-direction: column;
            gap: 2px;
            user-select: none;
            padding-right: 0.2rem;
        }}

        .marianne-flag-box {{
            display: inline-flex;
            align-items: center;
            margin-bottom: 2px;
        }}

        .marianne-flag-img {{
            width: 38px;
            height: 25px;
            object-fit: cover;
            border-radius: 3px;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(0, 0, 0, 0.1);
        }}

        .marianne-title {{
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
            font-weight: 800;
            font-size: 0.74rem;
            line-height: 1.15;
            letter-spacing: 0.2px;
            color: #121820;
            text-transform: uppercase;
        }}

        .marianne-motto {{
            font-family: "Fraunces", Georgia, serif;
            font-size: 0.63rem;
            font-style: italic;
            line-height: 1.25;
            color: #5c6873;
            margin-top: 1px;
        }}

        /* Trait de séparation vertical */
        .dsfr-divider {{
            width: 1.5px;
            height: 56px;
            background: linear-gradient(180deg, transparent 0%, rgba(28, 43, 56, 0.18) 15%, rgba(28, 43, 56, 0.18) 85%, transparent 100%);
            flex-shrink: 0;
        }}

        /* Bloc Service DGRE (style datagouv avec logo) */
        .dgre-brand-block {{
            display: flex;
            align-items: center;
            gap: 1.1rem;
        }}

        .dgre-logo-img {{
            height: 56px;
            width: auto;
            max-width: 95px;
            object-fit: contain;
            filter: drop-shadow(0 2px 5px rgba(0,0,0,0.06));
        }}

        .dgre-title-group {{
            display: flex;
            flex-direction: column;
        }}

        .dgre-wordmark {{
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
            font-weight: 800;
            font-size: 1.85rem;
            line-height: 1.05;
            letter-spacing: -0.02em;
            color: #000091; /* Bleu Marianne data.gouv.fr */
        }}

        .dgre-entity {{
            font-size: 0.84rem;
            font-weight: 600;
            color: #243342;
            margin-top: 3px;
            letter-spacing: -0.01em;
        }}

        /* Badge d'autorité à droite */
        .dsfr-header-right {{
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 0.35rem;
        }}

        .dsfr-status-tag {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            color: #166534;
            padding: 0.35rem 0.8rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}

        .dsfr-status-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #22c55e;
            box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.2);
            animation: dsfrPulseGreen 2s infinite;
        }}

        @keyframes dsfrPulseGreen {{
            0% {{ box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5); }}
            70% {{ box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }}
        }}

        .dsfr-portal-name {{
            font-size: 0.73rem;
            color: #5c6873;
            font-weight: 500;
        }}

        @media (max-width: 900px) {{
            .dsfr-header-container {{
                flex-direction: column;
                align-items: flex-start;
                padding: 0.8rem 1rem;
            }}
            .dsfr-header-right {{
                align-items: flex-start;
                margin-top: 0.3rem;
            }}
            .dsfr-divider {{
                display: none;
            }}
        }}


        /* ---------- Langage commun "carte editoriale" ---------- */
        .feature-card, .kpi-card, .status-chip,
        [data-testid="stChatMessage"],
        [data-testid="stExpander"], [data-testid="stDataFrame"],
        div[data-testid="stFileUploader"] section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            box-shadow: var(--card-shadow);
            transition: transform 0.32s cubic-bezier(0.16, 1, 0.3, 1),
                        box-shadow 0.32s cubic-bezier(0.16, 1, 0.3, 1),
                        border-color 0.32s ease;
            will-change: transform;
        }}
        .feature-card:hover, .kpi-card:hover, .status-chip:hover,
        [data-testid="stExpander"]:hover, [data-testid="stDataFrame"]:hover,
        div[data-testid="stFileUploader"] section:hover {{
            transform: translateY(-6px) scale(1.012);
            box-shadow: var(--card-shadow-hover);
            border-color: var(--card-border-hover);
            cursor: pointer;
        }}

        .feature-card, .status-chip {{
            position: relative;
            overflow: hidden;
        }}
        .feature-card::before, .status-chip::before {{
            content: "";
            position: absolute;
            inset: 0 auto auto 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, {COLOR_PRIMARY}, {COLOR_TERRACOTTA});
            opacity: 0.9;
        }}

        .feature-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
            margin: 1rem 0 0.35rem 0;
        }}
        .feature-card {{
            border-radius: 18px;
            padding: 1.05rem 1.1rem 1rem 1.1rem;
            height: 100%;
        }}
        .feature-card strong {{
            display: block;
            font-family: "Fraunces", Georgia, serif;
            font-weight: 600;
            font-size: 1.02rem;
            color: {COLOR_DEEP};
            margin-bottom: 0.35rem;
        }}
        .feature-card p {{
            margin: 0;
            color: {COLOR_MUTED};
            line-height: 1.55;
            font-size: 0.92rem;
        }}

        .status-strip {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.9rem 0 0.2rem 0;
        }}
        .status-chip {{
            border-radius: 999px;
            padding: 0.75rem 1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
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
        .status-chip.ok span {{ color: #0e7c72; }}
        .status-chip.warn span {{ color: #b5791f; }}
        .status-chip.error span {{ color: #a3502c; }}

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

        /* ---------- Bandeau d'en-tete ---------- */
        .hero-banner {{
            position: relative;
            background: linear-gradient(120deg, {COLOR_DEEP} 0%, {COLOR_PRIMARY} 100%);
            border-radius: 0;
            padding: 4.2rem 0.2rem 5.5rem 0.2rem;
            color: #ffffff;
            overflow: hidden;
            margin: -1.4rem -0.2rem 0.4rem -0.2rem;
            min-height: 15rem;
            display: flex;
            align-items: flex-end;
        }}
        .hero-banner.with-photo {{
            background: linear-gradient(180deg, rgba(16,35,49,0.32) 0%, rgba(16,35,49,0.5) 60%, rgba(20,79,158,0.96) 100%);
        }}
        .hero-photo {{
            position: absolute;
            inset: 0;
            background-size: cover;
            background-position: center 38%;
            z-index: 0;
            filter: saturate(1.05) contrast(1.0);
        }}
        .hero-banner::after {{
            content: "";
            position: absolute; left: 0; right: 0; bottom: 0; height: 55%;
            background: linear-gradient(180deg, transparent 0%, rgba(20,79,158,0.9) 100%);
            z-index: 1;
            pointer-events: none;
        }}
        .hero-content {{
            position: relative;
            z-index: 2;
            animation: hero-rise 0.7s cubic-bezier(0.16, 1, 0.3, 1) both;
        }}
        .hero-title {{
            font-size: clamp(2.4rem, 4vw, 3.6rem);
            font-weight: 500;
            margin: 0 0 0.5rem 0;
            letter-spacing: -0.01em;
            line-height: 1.04;
            color: #ffffff;
            text-shadow: 0 2px 18px rgba(16,35,49,0.45);
        }}
        .hero-subtitle {{
            font-size: 1.08rem;
            opacity: 1;
            color: rgba(255,255,255,0.96);
            margin: 0;
            max-width: 58ch;
            line-height: 1.55;
            text-shadow: 0 1px 12px rgba(16,35,49,0.4);
        }}
        .hero-tag {{
            display: inline-block;
            border-top: 1px solid rgba(255,255,255,0.7);
            padding: 0.5rem 0 0 0;
            margin-top: 1.3rem;
            font-family: "JetBrains Mono", ui-monospace, monospace;
            font-weight: 500;
            font-size: 0.7rem;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: rgba(255,255,255,0.92);
        }}
        .hero-title em {{
            font-style: italic;
            font-weight: 500;
            color: {COLOR_OCRE};
        }}
        @keyframes hero-rise {{
            from {{ opacity: 0; transform: translateY(14px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* ---------- Cartes KPI (allegees / plus fines) ---------- */
        .kpi-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            box-shadow: var(--card-shadow);
            border-radius: 14px;
            border-left: 2px solid {COLOR_PRIMARY};
            padding: 0.65rem 0.9rem;
            height: 100%;
            animation: kpi-rise 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
        }}
        .kpi-card:hover {{
            border-left-width: 3px;
        }}
        .kpi-icon {{ color: {COLOR_PRIMARY}; margin-bottom: 0.25rem; opacity: 0.9; }}
        .kpi-card.accent {{ border-left-color: {COLOR_TERRACOTTA}; }}
        .kpi-card.accent .kpi-icon {{ color: {COLOR_TERRACOTTA}; }}
        .kpi-label {{
            font-size: 0.72rem;
            color: {COLOR_MUTED};
            letter-spacing: 0.2px;
            margin-top: 0.15rem;
        }}
        .kpi-value {{
            font-family: "Fraunces", Georgia, serif;
            font-optical-sizing: auto;
            font-size: clamp(1.5rem, 1.8vw, 1.9rem);
            font-weight: 500;
            color: {COLOR_DEEP};
            line-height: 1.05;
            letter-spacing: -0.01em;
        }}
        @keyframes kpi-rise {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        div[data-testid="column"]:nth-child(1) .kpi-card {{ animation-delay: 0.02s; }}
        div[data-testid="column"]:nth-child(2) .kpi-card {{ animation-delay: 0.09s; }}
        div[data-testid="column"]:nth-child(3) .kpi-card {{ animation-delay: 0.16s; }}
        div[data-testid="column"]:nth-child(4) .kpi-card {{ animation-delay: 0.23s; }}
        div[data-testid="column"]:nth-child(5) .kpi-card {{ animation-delay: 0.3s; }}

        .section-title {{
            font-family: "Fraunces", Georgia, serif;
            color: {COLOR_DEEP};
            font-weight: 600;
            font-size: 1.14rem;
            margin: 1.5rem 0 0.65rem 0;
            display: flex;
            align-items: center;
            gap: 0.55rem;
        }}
        .section-title svg {{ color: {COLOR_PRIMARY}; }}

        /* ---------- Boutons ---------- */
        .stButton > button,
        .stDownloadButton > button,
        div[data-testid="stDownloadButton"] button {{
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, {COLOR_PRIMARY} 0%, {COLOR_PRIMARY_DARK} 100%) !important;
            color: #ffffff !important;
            border: 1px solid rgba(255, 255, 255, 0.22) !important;
            border-radius: 12px !important;
            font-weight: 600 !important;
            font-size: 0.93rem !important;
            padding: 0.6rem 1.3rem !important;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease !important;
            box-shadow: 0 6px 20px rgba(31,111,214,0.35) !important;
            display: inline-flex !important;
            align-items: center !important;
            gap: 0.5rem !important;
            margin-top: 0.4rem !important;
        }}
        .stButton > button *,
        .stDownloadButton > button *,
        div[data-testid="stDownloadButton"] button * {{
            color: #ffffff !important;
            font-weight: 600 !important;
        }}
        .stButton > button::before,
        .stDownloadButton > button::before,
        div[data-testid="stDownloadButton"] button::before {{
            content: "";
            position: absolute;
            top: 0;
            left: -75%;
            width: 45%;
            height: 100%;
            background: linear-gradient(115deg, transparent 0%, rgba(255,255,255,0.4) 50%, transparent 100%);
            transform: skewX(-20deg);
            transition: left 0.65s cubic-bezier(0.16, 1, 0.3, 1);
            pointer-events: none;
        }}
        .stButton > button:hover::before,
        .stDownloadButton > button:hover::before,
        div[data-testid="stDownloadButton"] button:hover::before {{
            left: 130%;
        }}
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        div[data-testid="stDownloadButton"] button:hover {{
            background: linear-gradient(135deg, {COLOR_TERRACOTTA} 0%, {COLOR_OCRE} 100%) !important;
            color: #ffffff !important;
            border-color: rgba(255, 255, 255, 0.35) !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 10px 26px rgba(193,103,59,0.42) !important;
        }}
        .stButton > button:focus-visible,
        .stDownloadButton > button:focus-visible,
        div[data-testid="stDownloadButton"] button:focus-visible {{
            outline: 3px solid rgba(31,111,214,0.4) !important;
            outline-offset: 2px !important;
        }}

        /* ---------- Bouton d'import : tres visible, grand, dedie ---------- */
        .import-launch-btn .stButton > button {{
            width: 100%;
            min-height: 3.6rem;
            font-size: 1.02rem;
            border-radius: 16px;
            background: linear-gradient(135deg, {COLOR_TERRACOTTA} 0%, {COLOR_OCRE} 100%);
            box-shadow: 0 14px 30px rgba(193,103,59,0.32);
            border: 1px solid rgba(255,255,255,0.25);
        }}
        .import-launch-btn .stButton > button:hover {{
            background: linear-gradient(135deg, {COLOR_PRIMARY} 0%, {COLOR_PRIMARY_DARK} 100%);
            box-shadow: 0 16px 34px rgba(31,111,214,0.34);
            transform: translateY(-2px);
        }}

        .import-panel {{
            background: var(--card-bg-strong);
            border: 1px solid rgba(28,43,56,0.09);
            border-radius: 18px;
            padding: 1.2rem 1.3rem 1.4rem 1.3rem;
            box-shadow: var(--card-shadow);
            margin-top: 0.6rem;
            margin-bottom: 1rem;
            transition: box-shadow 0.32s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .import-panel:hover {{
            box-shadow: var(--card-shadow-hover);
        }}
        .import-panel-title {{
            font-family: "Fraunces", Georgia, serif;
            font-weight: 600;
            font-size: 1.05rem;
            color: {COLOR_DEEP};
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.3rem;
        }}
        .import-panel-title svg {{ color: {COLOR_PRIMARY}; }}

        /* ---------- Chat & inputs (Adaptation Uiverse.io & Haute Visibilité) ---------- */
        [data-testid="stChatMessage"] {{
            border-radius: 18px !important;
            padding: 1.15rem 1.4rem !important;
            margin-bottom: 1.1rem !important;
            backdrop-filter: blur(14px) !important;
            -webkit-backdrop-filter: blur(14px) !important;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18) !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
        }}

        /* Bulle Assistant : Carte sombre style console/cockpit avec texte 100% lisible */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]),
        div[data-testid="stChatMessage"]:nth-child(odd) {{
            background: linear-gradient(145deg, rgba(16, 35, 49, 0.94) 0%, rgba(24, 48, 68, 0.97) 100%) !important;
            border-left: 4px solid #1f6fd6 !important;
            border-top: 1px solid rgba(255, 255, 255, 0.16) !important;
        }}

        /* Tous les textes du message Assistant forcés en BLANC ÉCLATANT */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) p,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) span,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) li,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) strong,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) em,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) div,
        div[data-testid="stChatMessage"]:nth-child(odd) p,
        div[data-testid="stChatMessage"]:nth-child(odd) span,
        div[data-testid="stChatMessage"]:nth-child(odd) div {{
            color: #f8fafc !important;
            line-height: 1.65 !important;
            font-size: 0.96rem !important;
        }}

        /* Bulle Utilisateur : Teinte bleue semi-transparente élégante */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
        div[data-testid="stChatMessage"]:nth-child(even) {{
            background: linear-gradient(135deg, rgba(31, 111, 214, 0.18) 0%, rgba(20, 79, 158, 0.28) 100%) !important;
            border-right: 4px solid #159895 !important;
            border: 1px solid rgba(31, 111, 214, 0.4) !important;
        }}

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) span,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) div,
        div[data-testid="stChatMessage"]:nth-child(even) p,
        div[data-testid="stChatMessage"]:nth-child(even) span {{
            color: #0f172a !important;
            font-weight: 500 !important;
            line-height: 1.6 !important;
            font-size: 0.96rem !important;
        }}

        /* Conteneurs flottants d'input en bas de page */
        [data-testid="stBottom"],
        [data-testid="stBottom"] > div,
        div.stChatFloatingInputContainer {{
            background: transparent !important;
            box-shadow: none !important;
            border: none !important;
        }}
        [data-testid="stBottom"]::before,
        [data-testid="stBottom"] *::before {{
            background: transparent !important;
        }}

        [data-testid="stBottomBlockContainer"] {{
            background: transparent !important;
            padding-bottom: 1.4rem !important;
            max-width: 960px !important;
            margin: 0 auto !important;
        }}

        /* Conteneur Chat Input (exact style Uiverse .container-chat-options) */
        [data-testid="stChatInput"] {{
            position: relative !important;
            display: flex !important;
            background: linear-gradient(
                to bottom right,
                #7e7e7e,
                #363636,
                #282828,
                #1e293b,
                #1e293b
            ) !important;
            border-radius: 20px !important;
            padding: 2px !important;
            overflow: hidden !important;
            box-shadow: 0 12px 34px rgba(0, 0, 0, 0.35), 0 0 24px rgba(31, 111, 214, 0.2) !important;
        }}

        /* Reflet radial dans l'angle (Uiverse ::after) */
        [data-testid="stChatInput"]::after {{
            position: absolute !important;
            content: "" !important;
            top: -10px !important;
            left: -10px !important;
            background: radial-gradient(
                ellipse at center,
                #ffffff,
                rgba(255, 255, 255, 0.35),
                rgba(255, 255, 255, 0.1),
                rgba(0, 0, 0, 0) 70%
            ) !important;
            width: 45px !important;
            height: 45px !important;
            filter: blur(1px) !important;
            pointer-events: none !important;
            z-index: 10 !important;
        }}

        /* Boîte intérieure (Uiverse .chat) */
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] [data-baseweb="base-input"] {{
            background: rgba(10, 16, 26, 0.88) !important;
            border-radius: 18px !important;
            width: 100% !important;
            backdrop-filter: blur(16px) !important;
            -webkit-backdrop-filter: blur(16px) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            padding: 4px 10px !important;
            display: flex !important;
            align-items: center !important;
        }}

        /* Zone de texte (Uiverse textarea) */
        [data-testid="stChatInput"] textarea {{
            background: transparent !important;
            color: #ffffff !important;
            font-family: "Inter", -apple-system, sans-serif !important;
            font-size: 0.95rem !important;
            font-weight: 400 !important;
            padding: 10px 14px !important;
            resize: none !important;
            outline: none !important;
            border: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stChatInput"] textarea::placeholder {{
            color: #cbd5e1 !important;
            opacity: 0.85 !important;
            transition: all 0.3s ease !important;
        }}

        [data-testid="stChatInput"] textarea:focus::placeholder {{
            color: #475569 !important;
        }}

        /* Bouton d'envoi (Uiverse .btn-submit) */
        [data-testid="stChatInput"] button,
        [data-testid="stChatInputSubmitButton"] button {{
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 2px !important;
            background-image: linear-gradient(to top, #144f9e, #1f6fd6, #3b82f6) !important;
            border-radius: 12px !important;
            box-shadow: inset 0 4px 2px -2px rgba(255, 255, 255, 0.6), 0 4px 14px rgba(31, 111, 214, 0.4) !important;
            cursor: pointer !important;
            border: none !important;
            outline: none !important;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
            width: 36px !important;
            height: 36px !important;
        }}

        [data-testid="stChatInput"] button:hover,
        [data-testid="stChatInputSubmitButton"] button:hover {{
            transform: scale(1.08) !important;
            background-image: linear-gradient(to top, #1d4ed8, #2563eb, #60a5fa) !important;
            box-shadow: inset 0 4px 2px -2px rgba(255, 255, 255, 0.8), 0 0 18px rgba(37, 99, 235, 0.6) !important;
        }}

        [data-testid="stChatInput"] button:hover svg,
        [data-testid="stChatInputSubmitButton"] button:hover svg {{
            color: #ffffff !important;
            filter: drop-shadow(0 0 6px #ffffff) !important;
        }}

        [data-testid="stChatInput"] button:active,
        [data-testid="stChatInputSubmitButton"] button:active {{
            transform: scale(0.92) !important;
        }}

        [data-testid="stChatInput"] button svg,
        [data-testid="stChatInputSubmitButton"] button svg {{
            color: #f3f6fd !important;
            width: 17px !important;
            height: 17px !important;
            transition: all 0.3s ease !important;
        }}

        /* Tags de suggestions (Uiverse .tags span) */
        .chat-tags-wrapper .stButton > button {{
            background: #1b1b1b !important;
            border: 1.5px solid #363636 !important;
            border-radius: 12px !important;
            color: #ffffff !important;
            font-size: 0.84rem !important;
            font-weight: 500 !important;
            padding: 8px 14px !important;
            min-height: auto !important;
            box-shadow: 0 3px 10px rgba(0, 0, 0, 0.2) !important;
            transition: all 0.25s ease !important;
        }}

        .chat-tags-wrapper .stButton > button:hover {{
            background: #262626 !important;
            border-color: #1f6fd6 !important;
            color: #60a5fa !important;
            transform: translateY(-3px) !important;
            box-shadow: 0 6px 18px rgba(31, 111, 214, 0.35) !important;
        }}

        [data-testid="stDataFrame"] {{
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(16, 35, 49, 0.06);
            border: 1px solid rgba(28, 43, 56, 0.08);
        }}
        [data-testid="stExpander"] {{
            border-radius: 16px;
        }}
        [data-testid="stPlot"],
        [data-testid="stImage"] img {{
            border-radius: 16px !important;
            box-shadow: 0 4px 20px rgba(16, 35, 49, 0.06) !important;
            border: 1px solid rgba(28, 43, 56, 0.08) !important;
        }}

        /* ---------- Tableau Haute Lisibilité des Crues (Dashboard) ---------- */
        .crue-card-container {{
            width: 100%;
            background: #ffffff;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(16, 35, 49, 0.06);
            border: 1px solid rgba(28, 43, 56, 0.08);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            margin-bottom: 1rem;
        }}

        .crue-scroll-wrapper {{
            width: 100%;
            max-height: 380px;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: #cbd5e1 transparent;
        }}

        .crue-scroll-wrapper::-webkit-scrollbar {{
            width: 6px;
        }}

        .crue-scroll-wrapper::-webkit-scrollbar-track {{
            background: transparent;
        }}

        .crue-scroll-wrapper::-webkit-scrollbar-thumb {{
            background-color: #cbd5e1;
            border-radius: 6px;
        }}

        .crue-custom-table {{
            width: 100%;
            border-collapse: collapse;
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
            text-align: left;
        }}

        .crue-custom-table thead {{
            position: sticky;
            top: 0;
            z-index: 5;
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
            border-bottom: 1.5px solid #e2e8f0;
        }}

        .crue-custom-table th {{
            padding: 12px 14px;
            font-size: 0.74rem;
            font-weight: 700;
            color: #475569;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }}

        .crue-th-station {{
            text-align: left;
            padding-left: 18px !important;
        }}

        .crue-th-center {{
            text-align: center;
        }}

        .crue-th-right {{
            text-align: right;
            padding-right: 18px !important;
        }}

        .crue-custom-table tbody tr {{
            border-bottom: 1px solid #f1f5f9;
            transition: background 0.15s ease;
        }}

        .crue-custom-table tbody tr:last-child {{
            border-bottom: none;
        }}

        .crue-custom-table tbody tr:hover {{
            background: #f8fafc;
        }}

        .crue-custom-table td {{
            padding: 11px 14px;
            vertical-align: middle;
        }}

        .crue-td-station {{
            text-align: left;
            padding-left: 18px !important;
        }}

        .crue-station-name {{
            font-weight: 700;
            color: #0f172a;
            font-size: 0.88rem;
            display: block;
        }}

        .crue-td-center {{
            text-align: center;
        }}

        .crue-gouv-badge {{
            display: inline-block;
            padding: 2.5px 8px;
            border-radius: 6px;
            font-size: 0.74rem;
            font-weight: 700;
            background: rgba(31, 111, 214, 0.08);
            color: #1e40af;
            border: 1px solid rgba(31, 111, 214, 0.18);
            letter-spacing: 0.3px;
        }}

        .crue-annee-pill {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.76rem;
            font-weight: 600;
            background: #f1f5f9;
            color: #334155;
            border: 1px solid #e2e8f0;
        }}

        .crue-td-right {{
            text-align: right;
            padding-right: 18px !important;
        }}

        .crue-debit-badge {{
            display: inline-flex;
            align-items: baseline;
            gap: 3px;
            padding: 3px 10px;
            border-radius: 8px;
            font-size: 0.88rem;
            font-weight: 700;
            white-space: nowrap;
        }}

        .crue-unit {{
            font-size: 0.7rem;
            font-weight: 600;
            opacity: 0.8;
        }}

        /* Crue record / exceptionnelle (> 650 m³/s) */
        .debit-badge-extreme {{
            background: #fef2f2;
            color: #dc2626;
            border: 1px solid #fecaca;
            box-shadow: 0 1px 4px rgba(220, 38, 38, 0.08);
        }}

        /* Crue majeure (> 500 m³/s) */
        .debit-badge-high {{
            background: #fff7ed;
            color: #c2410c;
            border: 1px solid #fed7aa;
        }}

        /* Crue standard */
        .debit-badge-normal {{
            background: #eff6ff;
            color: #1d4ed8;
            border: 1px solid #bfdbfe;
        }}

        /* ---------- Ticker (bandeau vivant) ---------- */
        .ticker-wrap {{
            position: relative;
            overflow: hidden;
            border-top: 1px solid rgba(28,43,56,0.12);
            border-bottom: 1px solid rgba(28,43,56,0.12);
            padding: 0.7rem 0;
            margin: 0.2rem 0 1.6rem 0;
            -webkit-mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent);
            mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent);
        }}
        .ticker-track {{
            display: flex;
            width: max-content;
            gap: 3.5rem;
            animation: ticker-scroll 32s linear infinite;
        }}
        .ticker-wrap:hover .ticker-track {{
            animation-play-state: paused;
        }}
        .ticker-item {{
            display: inline-flex;
            align-items: center;
            gap: 0.6rem;
            color: {COLOR_DEEP};
            font-size: 0.92rem;
            white-space: nowrap;
        }}
        .ticker-item .ticker-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: {COLOR_TERRACOTTA};
            flex-shrink: 0;
        }}
        @keyframes ticker-scroll {{
            from {{ transform: translateX(0); }}
            to {{ transform: translateX(-50%); }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            .ticker-track {{ animation: none; }}
            .hero-content, .kpi-card {{ animation: none; }}
        }}

        .main p, .main label, .main span, .main .stMarkdown {{
            color: {COLOR_TEXT};
        }}
        .stCaption {{
            color: {COLOR_MUTED};
        }}

        footer, #MainMenu {{ visibility: hidden; }}

        @media (max-width: 1100px) {{
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
    """`title` accepte du HTML simple : entourez un mot de <em>...</em> pour
    l'afficher en italique accentuee (ex. "Annuaire <em>Hydrometrique</em>
    de Tunisie"), a la maniere d'un titre editorial."""
    tag_html = f'<div class="hero-tag">/ {tag}</div>' if tag else ""
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
            <div class="kpi-icon">{icon_svg(icon_name, 20)}</div>
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


def alert_ticker(items):
    """Bandeau defilant en continu (dernieres crues, alertes, evenements).

    `items` : liste de chaines deja formatees, ex.
        ["Béja — crue du 12/03/2024 (48 m³/s)", "Jendouba — ..."]
    Dupliquee une fois en interne pour boucler sans coupure visible.
    """
    if not items:
        return
    contenu = "".join(
        f'<span class="ticker-item"><span class="ticker-dot"></span>{texte}</span>'
        for texte in items
    )
    st.markdown(
        f'<div class="ticker-wrap"><div class="ticker-track">{contenu}{contenu}</div></div>',
        unsafe_allow_html=True,
    )


def render_floating_nav(active_page: str):
    """Affiche la barre de navigation flottante glassmorphic (Uiverse.io by mymiamo)."""
    is_dash = (active_page == "Tableau de bord")
    is_chat = (active_page == "Assistant")

    active_dash = "active" if is_dash else ""
    active_chat = "active" if is_chat else ""

    icon_dashboard = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="3" width="7" height="9" rx="1"></rect>'
        '<rect x="14" y="3" width="7" height="5" rx="1"></rect>'
        '<rect x="14" y="12" width="7" height="9" rx="1"></rect>'
        '<rect x="3" y="16" width="7" height="5" rx="1"></rect>'
        '</svg>'
    )
    icon_assistant = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 2a3 3 0 0 0-3 3v1a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>'
        '<path d="M19 11v2a7 7 0 0 1-14 0v-2"></path>'
        '<circle cx="9" cy="9" r="1"></circle>'
        '<circle cx="15" cy="9" r="1"></circle>'
        '<path d="M12 18v4"></path>'
        '<path d="M8 22h8"></path>'
        '</svg>'
    )
    icon_refresh = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21.5 2v6h-6"></path>'
        '<path d="M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>'
        '</svg>'
    )

    current_query = "dashboard" if is_dash else "assistant"

    html = f"""
    <div class="menu-nav-wrapper">
        <nav class="menu" id="uiverse-menu">
            <a href="/?page=dashboard" target="_self" class="{active_dash}" title="Tableau de bord national">
                {icon_dashboard}
                <span>Tableau de bord</span>
            </a>
            <a href="/?page=assistant" target="_self" class="{active_chat}" title="Assistant IA Hydrologique">
                {icon_assistant}
                <span>Assistant IA</span>
            </a>
            <a href="/?page={current_query}&refresh=1" target="_self" title="Synchroniser et rafraîchir les données">
                {icon_refresh}
                <span>Actualiser</span>
            </a>
        </nav>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_sidebar_stars():
    """Injecte le ciel etoile cosmique (Uiverse.io by amir_6539) directement dans la barre laterale."""
    st.markdown(
        """
        <div class="sidebar-stars-portal">
            <div class="sidebar-stars-1"></div>
            <div class="sidebar-stars-2"></div>
            <div class="sidebar-stars-3"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_INSTITUTIONAL_CACHE = {}

def _institutional_assets():
    import os
    import base64
    racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(racine, "data")

    # Logo DGRE officiel (transparent de preference, sinon normal)
    p_dgre_trans = os.path.join(data_dir, "logo_dgre_transparent.png")
    p_dgre = os.path.join(data_dir, "logo_dgre.png")
    target_dgre = p_dgre_trans if os.path.exists(p_dgre_trans) else (p_dgre if os.path.exists(p_dgre) else None)
    dgre_mtime = os.path.getmtime(target_dgre) if target_dgre else None

    if target_dgre and _INSTITUTIONAL_CACHE.get("dgre_mtime") == dgre_mtime:
        dgre_b64 = _INSTITUTIONAL_CACHE.get("dgre_b64")
    else:
        dgre_b64 = None
        if target_dgre:
            with open(target_dgre, "rb") as f:
                dgre_b64 = base64.b64encode(f.read()).decode("ascii")
            _INSTITUTIONAL_CACHE["dgre_mtime"] = dgre_mtime
            _INSTITUTIONAL_CACHE["dgre_b64"] = dgre_b64

    # Drapeau de la Tunisie
    p_flag = os.path.join(data_dir, "drapeau_tunisie.png")
    flag_mtime = os.path.getmtime(p_flag) if os.path.exists(p_flag) else None
    if os.path.exists(p_flag) and _INSTITUTIONAL_CACHE.get("flag_mtime") == flag_mtime:
        flag_b64 = _INSTITUTIONAL_CACHE.get("flag_b64")
    else:
        flag_b64 = None
        if os.path.exists(p_flag):
            with open(p_flag, "rb") as f:
                flag_b64 = base64.b64encode(f.read()).decode("ascii")
            _INSTITUTIONAL_CACHE["flag_mtime"] = flag_mtime
            _INSTITUTIONAL_CACHE["flag_b64"] = flag_b64

    return dgre_b64, flag_b64


def render_institutional_header():
    """Affiche le bandeau institutionnel officiel (Drapeau Tunisie + Logo DGRE)
    dans le style exact du bloc-marque officiel data.gouv.fr / DSFR."""
    dgre_b64, flag_b64 = _institutional_assets()

    flag_html = (
        f'<img src="data:image/png;base64,{flag_b64}" alt="Drapeau de la République Tunisienne" class="marianne-flag-img" />'
        if flag_b64 else
        '<svg class="marianne-flag-img" viewBox="0 0 120 80"><rect width="120" height="80" fill="#E70013"/><circle cx="60" cy="40" r="20" fill="#fff"/><circle cx="60" cy="40" r="16" fill="#E70013"/><circle cx="64" cy="40" r="13" fill="#fff"/><polygon points="61.5,33.5 63,38 67.5,38 64,41 65.5,45.5 61.5,43 57.5,45.5 59,41 55.5,38 60,38" fill="#E70013"/></svg>'
    )

    dgre_html = (
        f'<img src="data:image/png;base64,{dgre_b64}" alt="Logo DGRE Tunisie" class="dgre-logo-img" />'
        if dgre_b64 else
        icon_svg("droplet", 46, color="#000091")
    )

    html = (
        '<div class="dsfr-header-container">'
        '<div class="dsfr-header-left">'
        '<div class="marianne-brand-block">'
        f'<div class="marianne-flag-box">{flag_html}</div>'
        '<div class="marianne-title">RÉPUBLIQUE<br>TUNISIENNE</div>'
        '<div class="marianne-motto">Liberté · Ordre · Justice</div>'
        '</div>'
        '<div class="dsfr-divider"></div>'
        '<div class="dgre-brand-block">'
        f'{dgre_html}'
        '<div class="dgre-title-group">'
        '<div class="dgre-wordmark">DGRE</div>'
        '<div class="dgre-entity">Direction Générale des Ressources en Eau</div>'
        '</div>'
        '</div>'
        '</div>'
        '<div class="dsfr-header-right">'
        '<div class="dsfr-status-tag"><span class="dsfr-status-dot"></span><span>Plateforme Officielle</span></div>'
        '<div class="dsfr-portal-name">Annuaire Hydrométrique National</div>'
        '</div>'
        '</div>'
    )
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)