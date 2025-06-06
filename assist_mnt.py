"""
assist_mnt.py
"""

import os
import processing
import numpy as np
import networkx as nx

from qgis.PyQt.QtCore import QCoreApplication, Qt, QObject, QVariant
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis._core import QgsVectorFileWriter
from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsRasterTransparency,
    QgsMapLayer,
    QgsProcessingFeedback,
    QgsField,
    QgsFields,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsRectangle,
    QgsRasterDataProvider,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext
)
from qgis.gui import QgsMapTool, QgsRubberBand
from osgeo import gdal

class AssistMnt(QObject):
    """
    Plugin QGIS AssistMnt.
    """

    def __init__(self, iface):
        """
        Constructeur du plugin.

        :param iface: Interface QGIS.
        :type iface: QgisInterface
        """
        super().__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr(u'&Assist MNT')
        self.toolbar = self.iface.addToolBar('Assist MNT')
        self.toolbar.setObjectName('Assist MNT')
        self.ridge_tool = None  # Instance du nouvel outil

    def tr(self, message):
        """
        Traduire un message en utilisant l'API de traduction Qt.

        :param message: Message à traduire.
        :type message: str
        :return: Message traduit.
        :rtype: str
        """
        return QCoreApplication.translate('AssistMnt', message)

    def add_action(self, icon_path, text, callback, parent=None):
        """
        Ajouter une action à la barre d'outils personnalisée Assist MNT.

        :param icon_path: Chemin de l'icône.
        :type icon_path: str
        :param text: Texte affiché pour l'action.
        :type text: str
        :param callback: Fonction de rappel à exécuter.
        :type callback: function
        :param parent: Widget parent.
        :type parent: QWidget
        :return: Action ajoutée.
        :rtype: QAction
        """
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        self.actions.append(action)
        return action

    def initGui(self):
        """
        Crée les boutons de la barre d'outils dans l'interface QGIS.
        """
        icon_dir = self.plugin_dir

        # Bouton pour MNTvisu
        self.add_action(
            os.path.join(icon_dir, "icon_2dm.png"),
            text=self.tr(u'MNTvisu'),
            callback=self.mntvisu_callback,
            parent=self.iface.mainWindow()
        )

        # Bouton pour StartMNT
        self.action_startMNT = self.add_action(
            os.path.join(icon_dir, "icon_start.png"),
            text=self.tr(u'StartMNT'),
            callback=self.startmnt_callback,
            parent=self.iface.mainWindow()
        )

        # **Ajouter ce code pour le bouton toggle**
        # Bouton toggle pour le mode de tracé libre
        icon_path = os.path.join(icon_dir, "icon_toggle.png")  # Assurez-vous que l'icône existe
        icon = QIcon(icon_path)
        self.action_toggle_free_draw = QAction(icon, self.tr(u'Tracé Libre'), self.iface.mainWindow())
        self.action_toggle_free_draw.setCheckable(True)
        self.action_toggle_free_draw.toggled.connect(self.toggle_free_draw)
        self.toolbar.addAction(self.action_toggle_free_draw)
        self.actions.append(self.action_toggle_free_draw)

        # Bouton pour StopMNT
        self.action_stopMNT = self.add_action(
            os.path.join(icon_dir, "icon_stop.png"),
            text=self.tr(u'StopMNT'),
            callback=self.stopmnt_callback,
            parent=self.iface.mainWindow()
        )



    def unload(self):
        """
        Supprime la barre d'outils du plugin et ses boutons de l'interface QGIS.
        """
        for action in self.actions:
            self.toolbar.removeAction(action)
        del self.toolbar

    def toggle_free_draw(self, checked):
        """Bascule entre le mode assisté et le mode de tracé libre."""
        if self.ridge_tool is not None:
            self.ridge_tool.set_free_draw_mode(checked)
        else:
            QMessageBox.warning(None, "Avertissement", "Veuillez d'abord activer l'outil avec le bouton StartMNT.")
            # Désactiver le bouton si l'outil n'est pas actif
            self.action_toggle_free_draw.setChecked(False)

    def mntvisu_callback(self):
        """Function for MNTvisu button."""

        # Définir le code EPSG à assigner
        EPSG_CODE = 2154  # RGF93 / Lambert-93

        # Obtenir les couches raster sélectionnées
        selected_layers = [
            layer for layer in self.iface.layerTreeView().selectedLayers()
            if layer.type() == QgsMapLayer.RasterLayer
        ]

        if not selected_layers:
            QMessageBox.warning(None, "Avertissement", "Aucune couche raster sélectionnée.")
            return

        feedback = QgsProcessingFeedback()

        # Assigner EPSG 2154 à chaque couche raster sélectionnée
        crs = QgsCoordinateReferenceSystem(EPSG_CODE)
        for layer in selected_layers:
            if layer.crs() != crs:
                layer.setCrs(crs)
                layer.triggerRepaint()

        # Si plusieurs couches sont sélectionnées, les combiner en une seule couche raster
        if len(selected_layers) > 1:
            # Rassembler les chemins des fichiers des couches raster sélectionnées
            raster_paths = [layer.source() for layer in selected_layers]

            # Définir les paramètres pour l'algorithme 'gdal:merge'
            merge_params = {
                'INPUT': raster_paths,
                'PCT': False,
                'SEPARATE': False,
                'NODATA_INPUT': None,
                'NODATA_OUTPUT': None,
                'OPTIONS': '',
                'DATA_TYPE': 0,  # Utiliser le type de données de la première couche
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }

            # Exécuter l'algorithme de fusion
            merge_result = processing.run("gdal:merge", merge_params, feedback=feedback)
            merged_layer = QgsRasterLayer(merge_result['OUTPUT'], 'Raster Combiné')

            if not merged_layer.isValid():
                QMessageBox.critical(None, "Erreur", "Échec de la création du raster combiné.")
                return

            # Assigner EPSG 2154 au raster combiné
            merged_layer.setCrs(crs)

            # Ajouter la couche raster combinée au projet
            QgsProject.instance().addMapLayer(merged_layer)
            combined_layer = merged_layer
        else:
            # Une seule couche raster sélectionnée, l'utiliser directement
            combined_layer = selected_layers[0]

        # Générer un ombrage de la couche raster combinée
        hillshade_params = {
            'INPUT': combined_layer.source(),
            'BAND': 1,
            'Z_FACTOR': 1.0,
            'SCALE': 1.0,
            'AZIMUTH': 315.0,
            'ALTITUDE': 45.0,
            'COMPUTE_EDGES': False,
            'ZEVENBERGEN': False,
            'MULTIDIRECTIONAL': False,
            'COMBINED': False,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }

        hillshade_result = processing.run("gdal:hillshade", hillshade_params, feedback=feedback)
        hillshade_layer = QgsRasterLayer(hillshade_result['OUTPUT'], 'Ombrage')
        hillshade_layer.setCrs(crs)

        if not hillshade_layer.isValid():
            QMessageBox.critical(None, "Erreur", "Échec de la création de l'ombrage.")
            return

        # Ajouter la couche d'ombrage en dessous de la couche raster combinée
        QgsProject.instance().addMapLayer(hillshade_layer, False)
        root = QgsProject.instance().layerTreeRoot()
        combined_node = root.findLayer(combined_layer.id())
        hillshade_node = root.insertLayer(root.children().index(combined_node) + 1, hillshade_layer)

        # Appliquer le style 'styleQGIS.qml' à la couche raster d'origine
        style_path = os.path.join(self.plugin_dir, 'styleQGIS.qml')

        if os.path.exists(style_path):
            combined_layer.loadNamedStyle(style_path)
            combined_layer.triggerRepaint()
        else:
            QMessageBox.warning(None, "Avertissement", "Le fichier de style 'styleQGIS.qml' est introuvable.")

            # Faire en sorte que les pixels avec une valeur de 0 deviennent totalement transparents
        transparency = combined_layer.renderer().rasterTransparency()
        transparent_pixel = QgsRasterTransparency.TransparentSingleValuePixel()
        transparent_pixel.min = 0
        transparent_pixel.max = 0
        transparent_pixel_list = [transparent_pixel]
        transparency.setTransparentSingleValuePixelList(transparent_pixel_list)
        combined_layer.triggerRepaint()

        # Appliquer le mode de fusion 'Multiply' à la couche raster combinée
        combined_layer.setBlendMode(QPainter.CompositionMode_Multiply)
        combined_layer.triggerRepaint()

        # Supprimer les couches raster de base non combinées si elles ont été fusionnées
        if len(selected_layers) > 1:
            for layer in selected_layers:
                QgsProject.instance().removeMapLayer(layer.id())

    def startmnt_callback(self):
        """Activation de l'outil de tracé."""
        # Vérifier qu'une couche raster est active
        mnt_layer = None
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.RasterLayer and layer.isValid():
                mnt_layer = layer
                break

        if mnt_layer is None:
            QMessageBox.warning(None, "Avertissement", "Aucune couche raster active trouvée.")
            return

        # Créer une instance de l'outil de dessin de ligne de crête
        self.ridge_tool = RidgeDrawingTool(self.canvas, mnt_layer)
        self.canvas.setMapTool(self.ridge_tool)

    def stopmnt_callback(self):
        """Désactivation de l'outil et exportation du shapefile."""
        """Désactivation de l'outil et exportation du shapefile."""
        if self.ridge_tool is None:
            QMessageBox.warning(None, "Avertissement", "Aucun tracé en cours.")
            return
        # **Si en mode tracé libre, quitter ce mode pour enregistrer les points**
        if self.ridge_tool.free_draw_mode:
            self.ridge_tool.set_free_draw_mode(False)
            self.action_toggle_free_draw.setChecked(False)



        # Exporter la polyligne finale dans un fichier .shp
        output_path = os.path.join(self.plugin_dir, "ligne_cretes.shp")

        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))

        writer = QgsVectorFileWriter(
            output_path,
            "UTF-8",
            fields,
            QgsWkbTypes.MultiLineString,
            self.canvas.mapSettings().destinationCrs(),
            "ESRI Shapefile"
        )

        if writer.hasError() != QgsVectorFileWriter.NoError:
            QMessageBox.critical(None, "Erreur", "Échec de l'écriture du fichier shapefile.")
            return

        # Créer une géométrie MultiLineString à partir des polylignes confirmées
        multi_line_geom = QgsGeometry.unaryUnion([geom for geom in self.ridge_tool.confirmed_polylines])

        feature = QgsFeature()
        feature.setGeometry(multi_line_geom)
        feature.setAttributes([1])
        writer.addFeature(feature)
        del writer  # Important pour s'assurer que les données sont bien écrites

        # Ajouter le shapefile au projet
        new_layer = QgsVectorLayer(output_path, "Ligne de Crêtes", "ogr")
        if not new_layer.isValid():
            QMessageBox.critical(None, "Erreur", "Impossible de charger le shapefile.")
            return

        QgsProject.instance().addMapLayer(new_layer)

        # Nettoyer et réinitialiser l'outil
        self.ridge_tool.reset()
        self.ridge_tool = None
        self.canvas.unsetMapTool(self.canvas.mapTool())

        QMessageBox.information(None, "Succès", "La polyligne a été exportée avec succès.")

class RidgeDrawingTool(QgsMapTool):
    """
    Outil de dessin de ligne de crête avec assistance dynamique sur MNT.
    """

    def __init__(self, canvas, raster_layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.raster_layer = raster_layer
        self.start_point = None
        self.dynamic_path = None
        self.confirmed_polylines = []
        self.free_draw_mode = False  # **Ajouter cette ligne**
        self.free_draw_points = []  # **Ajouter cette ligne**

        # Rubber band pour la ligne dynamique
        self.dynamic_rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.dynamic_rubber_band.setColor(QColor(255, 0, 0))
        self.dynamic_rubber_band.setWidth(2)
        self.dynamic_rubber_band.setLineStyle(Qt.DashLine)

        # Rubber band pour les polylignes confirmées
        self.confirmed_rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.confirmed_rubber_band.setColor(QColor(0, 0, 255))
        self.confirmed_rubber_band.setWidth(2)

        # **Ajouter ce code pour le tracé libre**
        # Rubber band pour le tracé libre
        self.free_draw_rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.free_draw_rubber_band.setColor(QColor(0, 255, 0))
        self.free_draw_rubber_band.setWidth(2)

    def set_free_draw_mode(self, free_draw):
        """Bascule le mode de tracé libre."""
        if free_draw:
            # Entrer en mode tracé libre
            self.free_draw_mode = True
            self.dynamic_rubber_band.reset(QgsWkbTypes.LineGeometry)

            # Initialiser les points du tracé libre avec le dernier point
            if self.start_point is not None:
                self.free_draw_points = [self.start_point]
                self.free_draw_rubber_band.reset(QgsWkbTypes.LineGeometry)
                self.free_draw_rubber_band.addPoint(self.start_point)
            else:
                # Aucun point de départ défini
                self.free_draw_points = []
        else:
            # Sortir du mode tracé libre
            self.free_draw_mode = False
            self.free_draw_rubber_band.reset(QgsWkbTypes.LineGeometry)
            if len(self.free_draw_points) >= 2:
                # Créer une polyligne à partir des points tracés librement
                free_draw_line = QgsGeometry.fromPolylineXY(self.free_draw_points)
                # Ajouter aux polylignes confirmées
                self.confirmed_polylines.append(free_draw_line)
                self.confirmed_rubber_band.addGeometry(free_draw_line, None)
                # Mettre à jour le point de départ pour le prochain segment
                self.start_point = self.free_draw_points[-1]
            elif len(self.free_draw_points) == 1:
                # Un seul point cliqué en mode libre
                self.start_point = self.free_draw_points[0]
            # Réinitialiser les points du tracé libre
            self.free_draw_points = []

    def canvasPressEvent(self, event):
        """Gestion des clics de souris."""
        map_point = self.toMapCoordinates(event.pos())

        if self.free_draw_mode:
            # Mode tracé libre
            self.free_draw_points.append(map_point)
            self.free_draw_rubber_band.addPoint(map_point)
        else:
            if self.start_point is None:
                # Premier clic : définir le point de départ
                self.start_point = map_point
            else:
                # Clic suivant : confirmer le segment actuel
                if self.dynamic_path:
                    # Ajouter la polyligne confirmée
                    self.confirmed_polylines.append(self.dynamic_path)
                    self.confirmed_rubber_band.addGeometry(self.dynamic_path, None)
                    # Mettre à jour le point de départ pour le prochain segment
                    self.start_point = self.dynamic_path.asPolyline()[-1]
                # Réinitialiser la ligne dynamique
                self.dynamic_rubber_band.reset(QgsWkbTypes.LineGeometry)

    def canvasMoveEvent(self, event):
        """Gestion des mouvements de souris."""
        if self.free_draw_mode:
            current_point = self.toMapCoordinates(event.pos())
            if self.free_draw_points:
                # Mettre à jour le rubber band pour montrer la ligne du dernier point jusqu'au curseur
                self.free_draw_rubber_band.reset(QgsWkbTypes.LineGeometry)
                for point in self.free_draw_points:
                    self.free_draw_rubber_band.addPoint(point)
                self.free_draw_rubber_band.addPoint(current_point)
        else:
            # Comportement existant
            if self.start_point is not None:
                current_point = self.toMapCoordinates(event.pos())
                # Calculer le chemin de plus haute altitude
                path_geometry = self.calculate_highest_path(self.start_point, current_point)
                if path_geometry:
                    self.dynamic_path = path_geometry
                    self.dynamic_rubber_band.reset(QgsWkbTypes.LineGeometry)
                    self.dynamic_rubber_band.addGeometry(path_geometry, None)
                else:
                    self.dynamic_rubber_band.reset(QgsWkbTypes.LineGeometry)

    def calculate_highest_path(self, start_point, end_point):
        """Calcul du chemin de plus haute altitude entre deux points dans le buffer."""
        import sys
        from osgeo import gdal

        # Création du buffer autour de la ligne entre les deux points
        line = QgsGeometry.fromPolylineXY([start_point, end_point])
        buffer_distance = 15  # 10 mètres de chaque côté
        buffer_geom = line.buffer(buffer_distance, -1)

        # Définir l'étendue du raster à extraire
        extent = buffer_geom.boundingBox()
        raster_provider = self.raster_layer.dataProvider()
        raster_crs = self.raster_layer.crs()
        canvas_crs = self.canvas.mapSettings().destinationCrs()

        # Transformation des coordonnées si nécessaire
        if not raster_crs == canvas_crs:
            xform = QgsCoordinateTransform(canvas_crs, raster_crs, QgsProject.instance())
            extent = xform.transformBoundingBox(extent)

        # Ouvrir le raster avec GDAL
        source = self.raster_layer.dataProvider().dataSourceUri()
        dataset = gdal.Open(source)
        if dataset is None:
            return None

        gt = dataset.GetGeoTransform()
        inv_gt = gdal.InvGeoTransform(gt)
        if inv_gt is None:
            return None

        xmin, ymin, xmax, ymax = extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()

        # S'assurer que xmin <= xmax et ymin <= ymax
        if xmin > xmax:
            xmin, xmax = xmax, xmin
        if ymin > ymax:
            ymin, ymax = ymax, ymin

        # Transformer les coordonnées de l'étendue en coordonnées pixels
        xoff1, yoff1 = gdal.ApplyGeoTransform(inv_gt, xmin, ymax)
        xoff2, yoff2 = gdal.ApplyGeoTransform(inv_gt, xmax, ymin)

        xoff = int(min(xoff1, xoff2))
        yoff = int(min(yoff1, yoff2))
        xsize = int(abs(xoff2 - xoff1))
        ysize = int(abs(yoff2 - yoff1))

        if xsize == 0 or ysize == 0:
            return None

        # Lire le tableau de données
        band = dataset.GetRasterBand(1)
        data_array = band.ReadAsArray(xoff, yoff, xsize, ysize)
        if data_array is None:
            return None

        # Création du graphe
        G = nx.DiGraph()

        # Fonction pour convertir les indices de pixel en coordonnées
        x0 = gt[0] + xoff * gt[1]
        y0 = gt[3] + yoff * gt[5]
        pixel_size_x = gt[1]
        pixel_size_y = gt[5]

        def pixel_to_map(i, j):
            x = x0 + j * pixel_size_x + pixel_size_x / 2
            y = y0 + i * pixel_size_y + pixel_size_y / 2
            return QgsPointXY(x, y)

        rows, cols = data_array.shape

        # Ajout des nœuds au graphe
        for i in range(rows):
            for j in range(cols):
                pos = pixel_to_map(i, j)
                point_geom = QgsGeometry.fromPointXY(pos)
                if buffer_geom.contains(point_geom):
                    value = data_array[i][j]
                    if value is not None and not np.isnan(value):
                        node = (i, j)
                        G.add_node(node, elevation=value, pos=pos)

        # Ajout des arêtes au graphe
        for node in G.nodes():
            i, j = node
            neighbors = [
                (i + di, j + dj)
                for di in [-1, 0, 1]
                for dj in [-1, 0, 1]
                if not (di == 0 and dj == 0)
            ]
            for neighbor in neighbors:
                if neighbor in G.nodes():
                    weight = -G.nodes[neighbor]['elevation']
                    G.add_edge(node, neighbor, weight=weight)

        # Trouver les nœuds les plus proches des points de départ et d'arrivée
        start_node = None
        end_node = None
        min_start_dist = float('inf')
        min_end_dist = float('inf')

        for node in G.nodes():
            pos = G.nodes[node]['pos']
            dist_start = (pos.x() - start_point.x()) ** 2 + (pos.y() - start_point.y()) ** 2
            dist_end = (pos.x() - end_point.x()) ** 2 + (pos.y() - end_point.y()) ** 2

            if dist_start < min_start_dist:
                min_start_dist = dist_start
                start_node = node

            if dist_end < min_end_dist:
                min_end_dist = dist_end
                end_node = node

        if start_node is None or end_node is None:
            return None

        # Calcul du chemin le plus court (plus haute altitude)
        try:
            path = nx.dijkstra_path(G, start_node, end_node)
        except nx.NetworkXNoPath:
            return None

        # Conversion du chemin en polyligne
        point_list = [G.nodes[node]['pos'] for node in path]
        return QgsGeometry.fromPolylineXY(point_list)

    def reset(self):
        """Réinitialise l'outil en supprimant les éléments temporaires."""
        self.start_point = None
        self.dynamic_path = None
        self.confirmed_polylines = []
        self.dynamic_rubber_band.reset(QgsWkbTypes.LineGeometry)
        self.confirmed_rubber_band.reset(QgsWkbTypes.LineGeometry)
        # **Réinitialiser le tracé libre**
        self.free_draw_rubber_band.reset(QgsWkbTypes.LineGeometry)
        self.free_draw_points = []
        self.free_draw_mode = False