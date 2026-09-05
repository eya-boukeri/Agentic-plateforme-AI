"""
src/agents/agent_cartographie.py
Agent Cartographie - genere toutes les cartes de l'annuaire (situation du
gouvernorat, situation des stations, reseau hydrometrique avec relief) a
partir des donnees SIG du projet :
  - data/gouvernorats_tunisie.geojson   (limites administratives)
  - data/cours_deau_tunisie.geojson     (cours d'eau, segments >= 1500 m)
  - data/regions_hydrographiques.geojson (7 grandes regions hydro. de Tunisie)
  - data/mnt_tunisie.tif                (modele numerique de terrain, reduit)

Separe de agent_edition.py pour isoler les dependances SIG (geopandas,
rasterio) : agent_edition.py n'a besoin de connaitre que le chemin d'image
resultant, pas la logique de rendu cartographique elle-meme.
"""

import os

try:
    import geopandas as gpd
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.lines as mlines
    from matplotlib.colors import LinearSegmentedColormap
    GEOPANDAS_DISPONIBLE = True
except ImportError:
    GEOPANDAS_DISPONIBLE = False

try:
    import rasterio
    RASTERIO_DISPONIBLE = True
except ImportError:
    RASTERIO_DISPONIBLE = False

import numpy as np


# Correspondance entre les codes normalises (GOUVERNORATS_ORDER dans
# agent_edition.py) et les noms exacts utilises dans
# data/gouvernorats_tunisie.geojson.
GOUVERNORAT_GEOJSON_NAME = {
    "L'ARIANA": "Ariana", "MANOUBA": "Manouba", "BIZERTE": "Bizerte",
    "BEJA": "Beja", "JENDOUBA": "Jendouba", "KEF": "El Kef",
    "SILIANA": "Siliana", "BEN AROUS": "Ben Arous", "NABEUL": "Nabeul",
    "ZAGHOUAN": "Zaghouan", "KAIROUAN": "Kairouan", "KASSERINE": "Kasserine",
    "SIDI BOUZID": "Sidi Bou Zid", "SOUSSE": "Sousse", "MONASTIR": "Monastir",
    "MAHDIA": "Mahdia", "SFAX": "Sfax", "GAFSA": "Gafsa", "GABES": "Gabés",
    "KEBILI": "Kebeli", "TOZEUR": "Tozeur", "MEDENINE": "Medenine",
    "TATAOUINE": "Tataouine",
}

# Formulation grammaticale correcte ("de l'Ariana", "de la Manouba", "du
# Kef") pour les quelques gouvernorats dont le nom ne se construit pas
# simplement avec "de {nom}" - utilisee dans les titres/legendes de carte.
_PHRASE_GOUVERNORAT_SPECIALE = {
    "L'ARIANA": "de l'Ariana",
    "MANOUBA": "de la Manouba",
    "KEF": "du Kef",
}


def _phrase_gouvernorat(gouv, nom_geo):
    return _PHRASE_GOUVERNORAT_SPECIALE.get(gouv, f"de {nom_geo}")

# Rampe de couleurs "relief" (vert en bas -> jaune -> brun/rouge en haut),
# dans le meme esprit que les cartes MNT de l'annuaire manuel.
# Rampe de couleurs "relief" : brun/beige en bas -> jaune -> vert en haut.
# C'est l'inverse de la convention "naturelle" (vert=bas/vegetation,
# brun=haut/rocheux), mais ca correspond exactement a la legende MNT de
# l'annuaire manuel (Value High = vert fonce, Low = brun/beige).
_COULEURS_MNT = ["#7a3b1e", "#c9862b", "#f5e050", "#8bc34a", "#1a7a3c"]


class AgentCartographie:
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "data"
            )
        self.data_dir = os.path.normpath(data_dir)
        self.output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "output", "graphs"
        )
        self.output_dir = os.path.normpath(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        self._gdf_gouvernorats = None
        self._gdf_cours_deau = None
        self._gdf_regions = None
        self._mnt_array = None
        self._mnt_extent = None
        self._mnt_charge = False
        self._pays_union = None

    # ------------------------------------------------------------------
    # Chargement (mis en cache) des couches SIG
    # ------------------------------------------------------------------
    def _chemin(self, nom_fichier):
        return os.path.join(self.data_dir, nom_fichier)

    def gouvernorats(self):
        if not GEOPANDAS_DISPONIBLE:
            return None
        if self._gdf_gouvernorats is None:
            chemin = self._chemin("gouvernorats_tunisie.geojson")
            if not os.path.exists(chemin):
                print(f"[AgentCartographie] fond de carte introuvable : {chemin}")
                return None
            self._gdf_gouvernorats = gpd.read_file(chemin)
        return self._gdf_gouvernorats

    def cours_deau(self):
        if not GEOPANDAS_DISPONIBLE:
            return None
        if self._gdf_cours_deau is None:
            chemin = self._chemin("cours_deau_tunisie.geojson")
            if not os.path.exists(chemin):
                print(f"[AgentCartographie] cours d'eau introuvables : {chemin}")
                self._gdf_cours_deau = False  # marque "tente, absent"
            else:
                self._gdf_cours_deau = gpd.read_file(chemin)
        return self._gdf_cours_deau if self._gdf_cours_deau is not False else None

    def regions_hydrographiques(self):
        if not GEOPANDAS_DISPONIBLE:
            return None
        if self._gdf_regions is None:
            chemin = self._chemin("regions_hydrographiques.geojson")
            if not os.path.exists(chemin):
                self._gdf_regions = False
            else:
                self._gdf_regions = gpd.read_file(chemin)
        return self._gdf_regions if self._gdf_regions is not False else None

    def secteur_hydrographique_pour_point(self, x_utm, y_utm):
        """Retourne le nom officiel (LIB_FR) de la region hydrographique
        (parmi les 7 grandes regions de Tunisie) qui contient le point
        donne (coordonnees UTM, meme CRS EPSG:22332 que le fichier), via
        une vraie jointure spatiale - plus fiable que le champ texte
        `bassin` de la table `station` (saisie manuelle, parfois
        approximative ou incoherente)."""
        regions = self.regions_hydrographiques()
        if regions is None:
            return None
        try:
            x_utm = float(x_utm)
            y_utm = float(y_utm)
        except (TypeError, ValueError):
            return None

        from shapely.geometry import Point
        point = Point(x_utm, y_utm)
        correspondance = regions[regions.geometry.contains(point)]
        if correspondance.empty:
            # Le point peut tomber juste en dehors d'un polygone simplifie
            # (bordure) : on reessaie avec une petite tolerance.
            correspondance = regions[regions.geometry.distance(point) < 200]
        if correspondance.empty:
            return None
        return str(correspondance.iloc[0]["LIB_FR"]).strip()

    def _mnt(self):
        """Charge (une seule fois) le MNT reduit en memoire, avec son
        etendue geographique (extent) pour l'affichage via imshow."""
        if not RASTERIO_DISPONIBLE:
            return None, None
        if self._mnt_charge:
            return self._mnt_array, self._mnt_extent

        self._mnt_charge = True
        chemin = self._chemin("mnt_tunisie.tif")
        if not os.path.exists(chemin):
            print(f"[AgentCartographie] MNT introuvable : {chemin}")
            return None, None

        with rasterio.open(chemin) as src:
            data = src.read(1).astype(float)
            data[data <= 0] = np.nan  # mer / no-data
            bounds = src.bounds
            self._mnt_extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
            self._mnt_array = data

        return self._mnt_array, self._mnt_extent

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------
    def _voisins(self, gdf, cible):
        """Gouvernorats dont la geometrie touche (avec une petite marge,
        pour tolerer les micro-espaces issus de la simplification) celle
        du gouvernorat cible."""
        cible_bufferisee = cible.geometry.iloc[0].buffer(500)  # 500 m
        return gdf[(gdf["gouvernorat"] != cible["gouvernorat"].iloc[0])
                   & gdf.geometry.intersects(cible_bufferisee)]

    def _dessiner_cours_deau(self, ax, bounds, marge_relative=0.35):
        """Superpose les cours d'eau visibles dans l'emprise donnee."""
        cours_deau = self.cours_deau()
        if cours_deau is None:
            return
        minx, miny, maxx, maxy = bounds
        mx = (maxx - minx) * marge_relative
        my = (maxy - miny) * marge_relative
        zone = cours_deau.cx[minx - mx:maxx + mx, miny - my:maxy + my]
        if not zone.empty:
            zone.plot(ax=ax, color="#3a7ebf", linewidth=0.6, zorder=2)

    def _masque_geometrie(self, geometrie, sous_extent, shape):
        """Masque booleen (True = a l'interieur de `geometrie`) pour la
        fenetre raster donnee - rasterisation generique reutilisee par
        `_masque_pays` (territoire national) et par les cartes MNT par
        gouvernorat (pour ne garder que le gouvernorat cible)."""
        if not RASTERIO_DISPONIBLE or geometrie is None:
            return None

        from rasterio.features import rasterize
        from rasterio.transform import from_bounds

        left, right, bottom, top = sous_extent
        n_lignes, n_cols = shape
        transform = from_bounds(left, bottom, right, top, n_cols, n_lignes)
        masque = rasterize([(geometrie, 1)], out_shape=shape,
                            transform=transform, fill=0, dtype="uint8")
        return masque.astype(bool)

    def _masque_pays(self, sous_extent, shape):
        """Masque booleen (True = a l'interieur du territoire tunisien),
        pour la fenetre MNT donnee. Sert a ne teinter en bleu que les vrais
        lacs/lagunes interieurs, et laisser la mer au-dela du littoral
        transparente (blanche) - comme dans l'annuaire manuel, ou la carte
        MNT ne colore pas la mer, contrairement a la carte de localisation."""
        gdf = self.gouvernorats()
        if gdf is None or not RASTERIO_DISPONIBLE:
            return None
        if self._pays_union is None:
            try:
                self._pays_union = gdf.geometry.union_all()
            except AttributeError:
                self._pays_union = gdf.unary_union

        return self._masque_geometrie(self._pays_union, sous_extent, shape)

    def _image_rgba_mnt(self, sous_array, masque_pays, vmin=None, vmax=None):
        """Construit une image RGBA a partir du MNT : lacs/lagunes internes
        en bleu clair opaque, mer au-dela du littoral en transparent.
        `vmin`/`vmax` permettent de normaliser la rampe de couleurs sur une
        zone precise (ex: un seul gouvernorat) plutot que sur toute la
        fenetre raster chargee - sinon le relief de gouvernorats voisins,
        potentiellement plus eleve, ecrase le contraste local."""
        cmap = LinearSegmentedColormap.from_list("mnt_tunisie", _COULEURS_MNT)
        if vmin is None or vmax is None:
            valeurs_valides = sous_array[~np.isnan(sous_array)]
            vmin = float(valeurs_valides.min()) if valeurs_valides.size else 0.0
            vmax = float(valeurs_valides.max()) if valeurs_valides.size else 1.0
        if vmax <= vmin:
            vmax = vmin + 1.0

        normalise = np.clip((np.nan_to_num(sous_array, nan=vmin) - vmin) / (vmax - vmin), 0, 1)
        rgba = cmap(normalise)

        est_nan = np.isnan(sous_array)
        couleur_eau = (0.75, 0.88, 0.94, 1.0)
        if masque_pays is not None:
            rgba[est_nan & masque_pays] = couleur_eau
            rgba[est_nan & ~masque_pays] = (0, 0, 0, 0)
        else:
            rgba[est_nan] = couleur_eau
        return rgba


        cmap = LinearSegmentedColormap.from_list("mnt_tunisie", _COULEURS_MNT)
        # Les pixels "nodata" du MNT correspondent en general a des plans
        # d'eau (lacs, lagunes, sebkhas) plutot qu'a une vraie absence de
        # donnee exploitable : un bleu clair est plus lisible qu'un blanc
        # pur qui ressemble a un trou dans la carte.
        cmap.set_bad(color="#bfe0f0")
        return cmap

    def _mnt_fenetre(self, bounds, marge_relative=0.15):
        """Retourne la sous-fenetre du MNT (array + extent) correspondant a
        l'emprise demandee, en decoupant le tableau deja charge en memoire
        (pas de re-lecture disque a chaque appel)."""
        array, extent = self._mnt()
        if array is None:
            return None, None

        left, right, bottom, top = extent
        minx, miny, maxx, maxy = bounds
        mx = (maxx - minx) * marge_relative
        my = (maxy - miny) * marge_relative
        minx, maxx = minx - mx, maxx + mx
        miny, maxy = miny - my, maxy + my

        n_lignes, n_cols = array.shape
        res_x = (right - left) / n_cols
        res_y = (top - bottom) / n_lignes

        col_debut = max(0, int((minx - left) / res_x))
        col_fin = min(n_cols, int((maxx - left) / res_x))
        ligne_debut = max(0, int((top - maxy) / res_y))
        ligne_fin = min(n_lignes, int((top - miny) / res_y))

        if col_fin <= col_debut or ligne_fin <= ligne_debut:
            return None, None

        sous_array = array[ligne_debut:ligne_fin, col_debut:col_fin]
        sous_extent = (
            left + col_debut * res_x, left + col_fin * res_x,
            top - ligne_fin * res_y, top - ligne_debut * res_y,
        )
        return sous_array, sous_extent

    # ------------------------------------------------------------------
    # Cartes publiques
    # ------------------------------------------------------------------
    def carte_pays(self):
        """Carte d'ensemble de la Tunisie (reseau hydrographique et limites
        des gouvernorats), pour la section Introduction de l'annuaire -
        equivalent de la "Figure 1: Carte du decoupage administratif" du
        modele manuel."""
        gdf = self.gouvernorats()
        if gdf is None:
            return None

        fig, ax = plt.subplots(figsize=(6.5, 8.5))

        regions = self.regions_hydrographiques()
        if regions is not None and not regions.empty:
            palette = plt.get_cmap("Set3")
            couleurs = [palette(i % palette.N) for i in range(len(regions))]
            regions.plot(ax=ax, color=couleurs, edgecolor="#5a5a5a", linewidth=0.4,
                         alpha=0.75, zorder=1)
        else:
            palette = plt.get_cmap("tab20")
            couleurs = [palette(i % palette.N) for i in range(len(gdf))]
            gdf.plot(ax=ax, color=couleurs, edgecolor="#5a5a5a", linewidth=0.4,
                      alpha=0.75, zorder=1)

        gdf.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=2)

        bounds = gdf.total_bounds
        self._dessiner_cours_deau(ax, bounds, marge_relative=0.02)

        for _, row in gdf.iterrows():
            c = row.geometry.representative_point()
            ax.annotate(str(row["gouvernorat"]).upper(), (c.x, c.y), fontsize=5.5,
                        fontweight="bold", ha="center", va="center", color="#1a1a1a", zorder=3)

        minx, miny, maxx, maxy = bounds
        marge_x = (maxx - minx) * 0.04
        marge_y = (maxy - miny) * 0.04
        ax.set_xlim(minx - marge_x, maxx + marge_x)
        ax.set_ylim(miny - marge_y, maxy + marge_y)

        # Grille/cadre gradue sur les 4 cotes, comme le cadre de l'annuaire
        # manuel (plutot que des axes nus).
        ax.tick_params(labelsize=5, length=2, top=True, right=True,
                        labeltop=True, labelright=True)
        ax.ticklabel_format(style="plain")
        ax.grid(True, linewidth=0.3, color="#999999", alpha=0.5, zorder=0)
        for spine in ax.spines.values():
            spine.set_linewidth(0.6)

        # Rose des vents (memes proportions que carte_gouvernorat)
        cx, cy = 0.88, 0.93
        rayon_long, rayon_court = 0.028, 0.011
        import math
        points = []
        for i in range(16):
            angle = math.radians(90 - i * 22.5)
            rayon = rayon_long if i % 2 == 0 else rayon_court
            points.append((cx + math.cos(angle) * rayon, cy + math.sin(angle) * rayon))
        etoile = mpatches.Polygon(points, closed=True, facecolor="black",
                                   edgecolor="black", linewidth=0.5,
                                   transform=ax.transAxes, zorder=10)
        ax.add_patch(etoile)
        for angle_deg, lettre in [(90, "N"), (0, "E"), (270, "S"), (180, "W")]:
            rad = math.radians(angle_deg)
            dx, dy = math.cos(rad) * (rayon_long + 0.02), math.sin(rad) * (rayon_long + 0.02)
            ax.annotate(lettre, (cx + dx, cy + dy), xycoords="axes fraction",
                        fontsize=6, fontweight="bold", ha="center", va="center", zorder=11)

        # Echelle en 4 segments alternes noir/blanc
        largeur_totale = 100000  # 100 km, en 4 segments de 25 km
        x0 = minx - marge_x + (maxx - minx) * 0.03
        y0 = miny - marge_y + (maxy - miny) * 0.03
        segment = largeur_totale / 4
        for i in range(4):
            couleur = "black" if i % 2 == 0 else "white"
            ax.add_patch(mpatches.Rectangle(
                (x0 + i * segment, y0), segment, (maxy - miny) * 0.006,
                facecolor=couleur, edgecolor="black", linewidth=0.5, zorder=6
            ))
        for i, label in enumerate(["0", "25", "50", "75", "100 km"]):
            pos = x0 + (i * segment if i < 4 else largeur_totale)
            ax.annotate(label, (pos, y0), fontsize=5, ha="center", va="top", zorder=6)

        filename = os.path.join(self.output_dir, "carte_tunisie_decoupage_administratif.png")
        fig.savefig(filename, dpi=220, bbox_inches="tight")
        plt.close(fig)
        return filename

    def carte_gouvernorat(self, gouv, stations=None, avec_mnt=False, annee=""):
        """Carte de situation d'un gouvernorat (avec ses voisins, une
        rose des vents, une mini-carte de localisation et les cours
        d'eau). Si `stations` est fourni, elles sont superposees. Si
        `avec_mnt=True`, le fond est colore selon le relief (MNT) plutot
        qu'en aplat de couleur uni - pour la section "Reseaux
        hydrometriques du gouvernorat" de l'annuaire manuel."""
        gdf = self.gouvernorats()
        if gdf is None:
            return None, None

        nom_geo = GOUVERNORAT_GEOJSON_NAME.get(gouv)
        if nom_geo is None or nom_geo not in gdf["gouvernorat"].values:
            return None, None

        cible = gdf[gdf["gouvernorat"] == nom_geo]
        voisins = self._voisins(gdf, cible)
        bounds = cible.total_bounds

        fig, ax = plt.subplots(figsize=(6.2, 7.2))

        mnt_min, mnt_max = None, None
        eau_visible = False
        if avec_mnt:
            sous_array, sous_extent = self._mnt_fenetre(bounds)
            if sous_array is not None:
                masque_pays = self._masque_pays(sous_extent, sous_array.shape)
                masque_gouv = self._masque_geometrie(cible.geometry.iloc[0], sous_extent, sous_array.shape)
                # Normaliser la rampe de couleurs sur le relief du seul
                # gouvernorat cible (pas toute la fenetre raster, qui deborde
                # sur les voisins et fausserait l'echelle High/Low).
                if masque_gouv is not None:
                    valeurs_gouv = sous_array[masque_gouv & ~np.isnan(sous_array)]
                else:
                    valeurs_gouv = sous_array[~np.isnan(sous_array)]
                vmin = float(valeurs_gouv.min()) if valeurs_gouv.size else None
                vmax = float(valeurs_gouv.max()) if valeurs_gouv.size else None
                if valeurs_gouv.size:
                    mnt_min = int(round(vmin))
                    mnt_max = int(round(vmax))

                image_rgba = self._image_rgba_mnt(sous_array, masque_pays, vmin=vmin, vmax=vmax)
                if masque_gouv is not None:
                    # Masquer (transparent) tout ce qui est hors du
                    # gouvernorat cible, pour ne pas afficher le relief -
                    # ni d'eventuelles lagunes/plans d'eau - des gouvernorats
                    # voisins qui tombent dans la fenetre raster.
                    image_rgba[~masque_gouv] = (0, 0, 0, 0)
                    eau_visible = bool(np.any(masque_gouv & np.isnan(sous_array) & (masque_pays if masque_pays is not None else True)))
                ax.imshow(image_rgba, extent=sous_extent, origin="upper", zorder=1, aspect="auto")
            cible.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=1.4, zorder=3)
        else:
            gdf.plot(ax=ax, color="white", edgecolor="#888888", linewidth=0.5, zorder=1)
            voisins.plot(ax=ax, color="#f2f2f2", edgecolor="#888888", linewidth=0.5, zorder=1)
            cible.plot(ax=ax, color="#f0c26a", edgecolor="black", linewidth=1.3, zorder=2)

        self._dessiner_cours_deau(ax, bounds)

        for _, row in voisins.iterrows():
            c = row.geometry.representative_point()
            ax.annotate(row["gouvernorat"], (c.x, c.y), fontsize=7, ha="center",
                        color="#333333", zorder=4)

        if stations:
            xs, ys, noms = [], [], []
            for station in stations:
                try:
                    xs.append(float(station.get("x_utm")))
                    ys.append(float(station.get("y_utm")))
                    noms.append(station.get("nom", ""))
                except (TypeError, ValueError):
                    continue
            if xs:
                ax.scatter(xs, ys, color="#1a1a1a", s=20, zorder=5, marker="o")
                for x, y, nom in zip(xs, ys, noms):
                    ax.annotate(nom, (x, y), fontsize=5.5, xytext=(3, 3),
                                textcoords="offset points", zorder=6, color="black")

        minx, miny, maxx, maxy = bounds
        # La carte MNT (relief) reste zoomee de pres sur le gouvernorat
        # (comme dans l'annuaire manuel) ; la carte de localisation garde
        # plus de marge pour montrer les voisins.
        facteur_marge = 0.04 if avec_mnt else 0.35
        marge_x = (maxx - minx) * facteur_marge + 2000
        marge_y = (maxy - miny) * facteur_marge + 2000
        ax.set_xlim(minx - marge_x, maxx + marge_x)
        ax.set_ylim(miny - marge_y, maxy + marge_y)

        # Cadre gradue (graduations + grille) sur les 4 cotes, comme le
        # modele manuel, pour toutes les cartes de gouvernorat (localisation,
        # stations et MNT).
        ax.tick_params(labelsize=5, length=2, top=True, right=True,
                       labeltop=True, labelright=True)
        ax.ticklabel_format(style="plain")
        ax.grid(True, linewidth=0.3, color="#999999", alpha=0.5, zorder=0)
        for spine in ax.spines.values():
            spine.set_linewidth(0.6)

        # Rose des vents (etoile a 8 branches alternees longues/courtes,
        # dans le style du modele manuel), plutot qu'une simple croix.
        cx, cy = 0.09, 0.90
        rayon_long, rayon_court = 0.032, 0.012
        import math
        points = []
        for i in range(16):
            angle = math.radians(90 - i * 22.5)  # part du Nord, sens horaire
            rayon = rayon_long if i % 2 == 0 else rayon_court
            points.append((cx + math.cos(angle) * rayon, cy + math.sin(angle) * rayon))
        etoile = mpatches.Polygon(points, closed=True, facecolor="black",
                                   edgecolor="black", linewidth=0.5,
                                   transform=ax.transAxes, zorder=10)
        ax.add_patch(etoile)
        for angle_deg, lettre in [(90, "N"), (0, "E"), (270, "S"), (180, "W")]:
            rad = math.radians(angle_deg)
            dx, dy = math.cos(rad) * (rayon_long + 0.022), math.sin(rad) * (rayon_long + 0.022)
            ax.annotate(lettre, (cx + dx, cy + dy), xycoords="axes fraction",
                        fontsize=7, fontweight="bold", ha="center", va="center", zorder=11)

        # Legende
        if avec_mnt:
            legend_patches = [
                mpatches.Patch(facecolor="none", edgecolor="black", label="Limite gouvernorat"),
                mlines.Line2D([0], [0], color="#3a7ebf", linewidth=1.2, label="Cours d'eau"),
            ]
            if eau_visible:
                legend_patches.insert(0, mpatches.Patch(facecolor="#bfe0f0", edgecolor="none", label="Plans d'eau"))
            if stations:
                legend_patches.append(mlines.Line2D(
                    [0], [0], marker="o", color="none", markerfacecolor="#1a1a1a",
                    markersize=6, label="Stations hydrométriques"))
            # Entete "MNT" / "Value" (non cliquable, juste du texte de
            # section dans la legende, comme le modele manuel) : on les
            # simule avec des Patch invisibles portant le texte en label.
            legend_patches.append(mpatches.Patch(facecolor="none", edgecolor="none", label="MNT"))
            legend_patches.append(mpatches.Patch(facecolor="none", edgecolor="none", label="Value"))
            label_high = f"High : {mnt_max}" if mnt_max is not None else "High"
            label_low = f"Low : {mnt_min}" if mnt_min is not None else "Low"
            legend_patches.append(mpatches.Patch(facecolor=_COULEURS_MNT[-1], edgecolor="none", label=label_high))
            legend_patches.append(mpatches.Patch(facecolor=_COULEURS_MNT[0], edgecolor="none", label=label_low))
        else:
            legend_patches = [
                mpatches.Patch(facecolor="#f0c26a", edgecolor="black", label=nom_geo),
                mpatches.Patch(facecolor="#f2f2f2", edgecolor="#888888", label="Gouvernorats voisins"),
            ]
            if self.cours_deau() is not None:
                legend_patches.append(mlines.Line2D([0], [0], color="#3a7ebf", linewidth=1.2, label="Cours d'eau"))
            if stations:
                legend_patches.append(mlines.Line2D(
                    [0], [0], marker="o", color="none", markerfacecolor="#1a1a1a",
                    markersize=6, label="Stations hydrométriques"))
        ax.legend(handles=legend_patches, loc="lower left", fontsize=6, framealpha=0.9,
                  title="Légende", title_fontsize=7)

        # Echelle en 4 segments alternes noir/blanc (coin bas-droit, pour ne
        # pas chevaucher la legende qui est en bas-gauche), avec graduations
        # intermediaires comme le modele manuel (0/2/4/8/12 ou equivalent).
        largeur_totale = 12000  # 12 km, en 4 segments de 3 km
        x0 = maxx + marge_x - (maxx - minx) * 0.05 - largeur_totale
        y0 = miny - marge_y + (maxy - miny) * 0.03
        segment = largeur_totale / 4
        for i in range(4):
            couleur = "black" if i % 2 == 0 else "white"
            ax.add_patch(mpatches.Rectangle(
                (x0 + i * segment, y0), segment, (maxy - miny) * 0.008,
                facecolor=couleur, edgecolor="black", linewidth=0.5, zorder=6
            ))
        for i, label in enumerate(["0", "2", "4", "8", "12 km"]):
            pos = x0 + (i * segment if i < 4 else largeur_totale)
            ax.annotate(label, (pos, y0), fontsize=5, ha="center", va="top", zorder=6)

        # Mini-carte de localisation
        inset = fig.add_axes([0.68, 0.68, 0.28, 0.28])
        gdf.plot(ax=inset, color="white", edgecolor="#999999", linewidth=0.3)
        cible.plot(ax=inset, color="#f0c26a", edgecolor="black", linewidth=0.6)
        inset.set_axis_off()

        phrase = _phrase_gouvernorat(gouv, nom_geo)
        if avec_mnt:
            titre = f"Réseau hydrométrique - Gouvernorat {phrase}"
        elif stations:
            titre = f"Situation des stations hydrométriques - Gouvernorat {phrase}"
        else:
            titre = f"Localisation du gouvernorat {phrase}"

        suffixe = "mnt" if avec_mnt else ("stations" if stations else "localisation")
        filename = os.path.join(self.output_dir, f"carte_{gouv.replace(chr(39), '')}_{suffixe}_{annee}.png")
        fig.savefig(filename, dpi=220, bbox_inches="tight")
        plt.close(fig)
        return filename, titre