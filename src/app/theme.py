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


# ============================================================
# STARFIELD (Uiverse.io by amir_6539, adapte - 3 couches)
# ============================================================
# Trois couches de points (box-shadow) :
# - fine et dense (etoiles lointaines)
# - moyenne (etoiles intermediaires)
# - rare et grosse (etoiles proches)
# Coordonnees reprises du composant d'origine.
_STARS_SMALL = "501px 811px #fff,1450px 1324px #fff,1093px 1780px #fff,1469px 678px #fff,904px 741px #fff,1160px 781px #fff,1841px 1962px #fff,1630px 1667px #fff,1788px 676px #fff,367px 1734px #fff,1343px 156px #fff,1283px 1142px #fff,1062px 378px #fff,1395px 467px #fff,1017px 1891px #fff,137px 1114px #fff,1767px 1403px #fff,1543px 11px #fff,1078px 181px #fff,1189px 1574px #fff,1697px 1551px #fff,439px 472px #fff,1491px 677px #fff,1364px 599px #fff,34px 382px #fff,1221px 1584px #fff,1266px 1499px #fff,169px 1907px #fff,1219px 1125px #fff,659px 18px #fff,1731px 1959px #fff,332px 1216px #fff,1913px 788px #fff,80px 712px #fff,326px 1605px #fff,574px 1502px #fff,473px 1653px #fff,404px 975px #fff,322px 1797px #fff,425px 1321px #fff,1121px 1797px #fff,731px 647px #fff,891px 1584px #fff,1523px 109px #fff,1379px 244px #fff,865px 1064px #fff,493px 956px #fff,624px 1380px #fff,440px 619px #fff,1630px 767px #fff,955px 1196px #fff,62px 729px #fff,126px 946px #fff,1256px 896px #fff,1444px 256px #fff,661px 1628px #fff,1078px 1716px #fff,300px 737px #fff,1734px 413px #fff,1296px 129px #fff,1771px 1678px #fff,977px 1764px #fff,1879px 549px #fff,665px 1531px #fff,89px 701px #fff,1084px 1183px #fff,1597px 1576px #fff,1354px 1774px #fff,554px 1471px #fff,1469px 287px #fff,887px 106px #fff,1962px 766px #fff,638px 805px #fff,1651px 741px #fff,1517px 1826px #fff,24px 1152px #fff,507px 558px #fff,1262px 652px #fff,246px 1048px #fff,1077px 421px #fff,1866px 1847px #fff,1986px 1561px #fff,704px 632px #fff,1991px 1875px #fff,1227px 395px #fff,45px 1116px #fff,247px 786px #fff,890px 607px #fff,787px 1235px #fff,557px 524px #fff,1582px 1285px #fff,1725px 1366px #fff,952px 747px #fff,251px 458px #fff,1500px 1250px #fff,1999px 1734px #fff,1336px 1955px #fff,1705px 1464px #fff,728px 697px #fff,594px 510px #fff,1345px 1990px #fff,1919px 1803px #fff,1117px 966px #fff,1629px 97px #fff,1046px 1196px #fff,810px 1092px #fff,722px 976px #fff,406px 18px #fff,1665px 1860px #fff,1758px 1628px #fff,1183px 463px #fff,564px 239px #fff,13px 1767px #fff,1482px 1472px #fff,1700px 347px #fff,1362px 244px #fff,1141px 1708px #fff,22px 885px #fff,374px 1309px #fff,1034px 1037px #fff,1725px 1086px #fff,1343px 1921px #fff,596px 903px #fff,1061px 478px #fff,18px 1409px #fff,729px 1364px #fff,264px 911px #fff,677px 1442px #fff,123px 33px #fff,1303px 646px #fff,1945px 792px #fff,1305px 938px #fff,918px 1536px #fff,620px 948px #fff,183px 646px #fff,695px 687px #fff,881px 272px #fff"
_STARS_MEDIUM = "1925px 1320px #fff,693px 1778px #fff,1016px 711px #fff,1171px 563px #fff,661px 1919px #fff,1610px 44px #fff,1275px 140px #fff,1208px 1802px #fff,1473px 1587px #fff,11px 1117px #fff,853px 1757px #fff,1149px 937px #fff,1353px 428px #fff,270px 279px #fff,258px 1404px #fff,417px 1188px #fff,286px 561px #fff,393px 1765px #fff,147px 881px #fff,666px 1097px #fff,1425px 1278px #fff,806px 156px #fff,1252px 561px #fff,218px 52px #fff,1371px 1980px #fff,171px 745px #fff,1424px 89px #fff,137px 244px #fff,939px 1922px #fff,137px 1080px #fff,1757px 50px #fff,904px 536px #fff,1938px 1001px #fff,1172px 440px #fff,72px 1475px #fff,102px 121px #fff,804px 1671px #fff,1314px 270px #fff,440px 1341px #fff,1216px 511px #fff,1061px 1523px #fff,97px 274px #fff,704px 1318px #fff,52px 1872px #fff,1962px 296px #fff,111px 289px #fff,1157px 1236px #fff,1347px 1451px #fff,820px 286px #fff,1389px 1169px #fff,644px 841px #fff"
_STARS_LARGE = "200px 981px #fff,1731px 521px #fff,132px 1039px #fff,1888px 1547px #fff,899px 1226px #fff,1887px 580px #fff,1548px 1092px #fff,1626px 689px #fff,254px 1072px #fff,1684px 1211px #fff,672px 1267px #fff,939px 668px #fff,1969px 645px #fff,1126px 983px #fff,457px 568px #fff,476px 876px #fff,829px 1896px #fff,1364px 1846px #fff,1507px 1120px #fff,936px 1948px #fff,1833px 832px #fff,1424px 285px #fff,1377px 1596px #fff,432px 153px #fff,1348px 1410px #fff,1529px 954px #fff,1102px 387px #fff,264px 297px #fff,811px 977px #fff,1931px 673px #fff,1734px 978px #fff,1772px 1567px #fff,1197px 1400px #fff,764px 282px #fff,1103px 822px #fff,872px 1803px #fff,1057px 1763px #fff,52px 1299px #fff,1312px 1236px #fff,235px 1082px #fff,299px 1086px #fff,1017px 1602px #fff,1950px 626px #fff,1306px 132px #fff,1358px 1618px #fff,1873px 1718px #fff,1447px 940px #fff,1888px 1195px #fff,1704px 1765px #fff,872px 1357px #fff,1555px 1120px #fff,250px 1415px #fff,450px 415px #fff,492px 901px #fff,170px 1641px #fff,56px 1129px #fff,627px 1514px #fff,1221px 500px #fff,324px 1895px #fff,1397px 1775px #fff,1966px 598px #fff,1550px 763px #fff,326px 1605px #fff,261px 969px #fff,890px 281px #fff,736px 544px #fff,589px 1262px #fff,1581px 368px #fff,1900px 1132px #fff,1914px 585px #fff,1864px 1517px #fff,241px 217px #fff,859px 787px #fff,996px 1729px #fff,741px 121px #fff,418px 414px #fff,142px 967px #fff,387px 896px #fff,703px 562px #fff,968px 1136px #fff,1682px 332px #fff,1287px 846px #fff,256px 1427px #fff,1885px 432px #fff,1739px 1458px #fff,345px 1769px #fff,1140px 1612px #fff,192px 1921px #fff,920px 471px #fff,834px 881px #fff,917px 1803px #fff,466px 1266px #fff,483px 1108px #fff,689px 986px #fff,1279px 786px #fff,458px 910px #fff,1250px 870px #fff,785px 1654px #fff,1543px 1757px #fff,287px 1272px #fff"

STAR_CSS = f"""
        section[data-testid="stSidebar"] {{
            position: relative;
            isolation: isolate;
            overflow: hidden;
        }}
        /* Couche 1 : etoiles fines (lointaines) */
        section[data-testid="stSidebar"]::before {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            clip-path: inset(0 calc(100vw - 22rem) 0 0);
            pointer-events: none;
            z-index: 0;
            width: 1px;
            height: 1px;
            background: transparent;
            box-shadow: {_STARS_SMALL};
            opacity: 0.6;
            animation: starfield-drift-slow 70s linear infinite;
        }}
        /* Couche 2 : etoiles moyennes */
        section[data-testid="stSidebar"]::after {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            clip-path: inset(0 calc(100vw - 22rem) 0 0);
            pointer-events: none;
            z-index: 0;
            width: 2px;
            height: 2px;
            background: transparent;
            box-shadow: {_STARS_MEDIUM};
            opacity: 0.5;
            animation: starfield-drift-medium 130s linear infinite;
        }}
        /* Couche 3 : etoiles grosses (proches) */
        section[data-testid="stSidebar"] .stars-layer {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            clip-path: inset(0 calc(100vw - 22rem) 0 0);
            pointer-events: none;
            z-index: 0;
            width: 3px;
            height: 3px;
            background: transparent;
            box-shadow: {_STARS_LARGE};
            opacity: 0.35;
            animation: starfield-drift-fast 180s linear infinite;
        }}
        /* Conteneur pour la 3eme couche */
        .stars-layer-wrapper {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 0;
            overflow: hidden;
        }}
        @keyframes starfield-drift-slow {{
            from {{ transform: translateY(0); }}
            to {{ transform: translateY(-2000px); }}
        }}
        @keyframes starfield-drift-medium {{
            from {{ transform: translateY(0); }}
            to {{ transform: translateY(-2000px); }}
        }}
        @keyframes starfield-drift-fast {{
            from {{ transform: translateY(0); }}
            to {{ transform: translateY(-2000px); }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            section[data-testid="stSidebar"]::before,
            section[data-testid="stSidebar"]::after,
            section[data-testid="stSidebar"] .stars-layer {{
                animation: none;
            }}
        }}
"""


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
            filter: blur(10px) saturate(0.9);
            opacity: 0.55;
        }}
        .stApp::after {{
            content: "";
            position: fixed;
            inset: 0;
            z-index: -1;
            background-image: linear-gradient(160deg, rgba(207,217,221,0.88) 0%, rgba(233,239,241,0.92) 45%, rgba(207,217,221,0.94) 100%);
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
        }}

        html, body, [class*="css"] {{
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        .main .block-container {{
            max-width: 1320px;
            padding-top: 1.4rem;
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

        /* ---------- Sidebar (restee sombre : contraste et ancrage) ---------- */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(195deg, #16232d 0%, {COLOR_DEEP} 55%, #223546 100%);
            border-right: 1px solid rgba(255,255,255,0.06);
        }}
        section[data-testid="stSidebar"] * {{
            color: #eef3f5 !important;
            position: relative;
            z-index: 1;
        }}
        section[data-testid="stSidebar"] hr {{
            border-color: rgba(255,255,255,0.14);
        }}
        section[data-testid="stSidebar"] .stRadio [role="radiogroup"] {{
            gap: 0.45rem;
        }}
        section[data-testid="stSidebar"] .stRadio label {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 0.4rem 0.65rem;
            transition: background 0.15s ease, border-color 0.15s ease;
        }}
        section[data-testid="stSidebar"] .stRadio label:hover {{
            background: rgba(31,111,214,0.22);
            border-color: rgba(31,111,214,0.4);
        }}

        /* ---------- Starfield (V3.3 - 3 couches) ---------- */
        {STAR_CSS}

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
        .stButton > button, .stDownloadButton > button {{
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, {COLOR_PRIMARY} 0%, {COLOR_PRIMARY_DARK} 100%);
            color: #ffffff;
            border: none;
            border-radius: 999px;
            font-weight: 600;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
            box-shadow: 0 10px 24px rgba(31,111,214,0.28);
        }}
        .stButton > button::before, .stDownloadButton > button::before {{
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
        .stButton > button:hover::before, .stDownloadButton > button:hover::before {{
            left: 130%;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            background: linear-gradient(135deg, {COLOR_TERRACOTTA} 0%, {COLOR_OCRE} 100%);
            color: #ffffff;
            transform: translateY(-1px);
            box-shadow: 0 14px 30px rgba(193,103,59,0.3);
        }}
        .stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
            outline: 3px solid rgba(31,111,214,0.35);
            outline-offset: 2px;
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

        /* ---------- Chat & inputs ---------- */
        [data-testid="stChatMessage"] {{
            border-radius: 18px;
        }}

        [data-testid="stBottom"],
        [data-testid="stBottom"] > div,
        [data-testid="stBottomBlockContainer"],
        div.stChatFloatingInputContainer {{
            background: transparent !important;
            box-shadow: none !important;
            border: none !important;
        }}
        [data-testid="stBottom"]::before,
        [data-testid="stBottom"] *::before {{
            background: transparent !important;
        }}
        [data-testid="stChatInput"],
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] textarea,
        [data-testid="stChatInput"] [data-baseweb="textarea"],
        [data-testid="stChatInput"] [data-baseweb="base-input"] {{
            background: var(--card-bg-strong) !important;
            border: 1px solid var(--card-border) !important;
            backdrop-filter: blur(14px) saturate(150%);
            -webkit-backdrop-filter: blur(14px) saturate(150%);
            box-shadow: var(--card-shadow) !important;
            border-radius: 18px !important;
        }}
        [data-testid="stChatInput"] textarea {{
            color: {COLOR_TEXT} !important;
            box-shadow: none !important;
        }}
        [data-testid="stChatInput"] *:focus,
        [data-testid="stChatInput"] *:focus-within,
        [data-testid="stChatInput"] [data-baseweb="base-input"]:focus-within {{
            border-color: rgba(31,111,214,0.55) !important;
            box-shadow: 0 0 0 2px rgba(31,111,214,0.25) !important;
            outline: none !important;
        }}
        [data-testid="stBottomBlockContainer"] {{
            padding-bottom: 1.2rem;
        }}

        [data-testid="stDataFrame"] {{
            border-radius: 16px;
            overflow: hidden;
        }}
        [data-testid="stExpander"] {{
            border-radius: 16px;
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

    # Element HTML pour la 3eme couche d'etoiles (starfield)
    st.markdown(
        """
        <div class="stars-layer-wrapper">
            <div class="stars-layer"></div>
        </div>
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