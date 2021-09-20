# On souhaite obtenir dans un attribut le nombre de façades d'un bâtiment où chaque façade a une longueur inférieure à
# 2.5 m et n'est pas collée à un autre bâtiment

# Il y a plusieurs façons de lancer les différentes étapes de calcul dans QGIS : 1) créer une fonction personnalisée,
# 2) lancer le script dans la console Python, 3) créer un algorithme à intégrer dans la boîte à outils de traitements
# Ici on choisit la solution 2) qui est la plus rapide à mettre en place. Le script est copié-collé tel quel dans
# l'éditeur puis lancé.

# Les lignes ci-dessous sont à décommenter si l'on ne travaille pas avec la console Python. Elles permettent d'importer
# les classes de la bibliothèque PyQgis utilisées dans le script. En effet, via la console Python, ces classes sont déjà
# intégrées.

# from qgis.core import (
#     QgsExpression,
#     QgsExpressionContext,
#     QgsFeature,
#     QgsFields,
#     QgsField,
#     qgsfunction,
#     QgsSpatialIndex,
#     QgsProject
# )
#
# from qgis.utils import iface

from datetime import datetime  # on importe cette classe car elle ne fait pas partie de PyQGIS. Elle sert pour
# déterminer le temps de calcul.

start = datetime.now()  # l'heure de début du calcul

# On crée une barre de progression pour suivre l'évolution du calcul
iface.messageBar().clearWidgets()
progressMessageBar = iface.messageBar().createMessage("Remplissage de l'attribut n_p_facade en cours...")
progress = QProgressBar()
progress.setMaximum(100)
progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
progressMessageBar.layout().addWidget(progress)
iface.messageBar().pushWidget(progressMessageBar, Qgis.Info)

# Sélection de la couche que l'on souhaite modifier
layer = QgsProject.instance().mapLayersByName("ZoneTestGV_Bati")[0]  # ZoneTestGV_Bati est le nom de la couche test
iface.setActiveLayer(layer)

# On crée un index spatial. Cela permet de considérablement diminuer le temps de calcul pour des étapes suivantes.
index = QgsSpatialIndex(layer.getFeatures())

# On crée un attribut n_p_facade (comprendre "nombre de petites façades") qui contiendra le nombre de façades
# extérieures pour chaque bâtiment, et dont la longueur est inférieure à 2.5 m. On ajoute une condition de le créer
# que s'il n'existe pas encore
layer_fields_count = layer.fields().count()
layer_fields_names = layer.fields().names()
n_p_facade_exists = False

for f in range(0, layer_fields_count):
    if layer_fields_names[f] == 'n_p_facade':
        n_p_facade_exists = True
if not n_p_facade_exists:
    res = layer.dataProvider().addAttributes([QgsField("n_p_facade", QVariant.Int)])
    layer.updateFields()

iterations_count = 0  # initialisation d'un compteur qui sert à l'actualisation de la barre de progression

# On effectue une même série d'opérations sur chaque bâtiment
for feature in layer.getFeatures():

    # Permet d'actualiser la barre de progression à chaque fois que la série d'opérations démarre pour chaque bâtiment
    iterations_count += 1
    percent = iterations_count / float(selected_features_count) * 100
    progress.setValue(percent)

    # Détermination du nombre de façade du bâtiment
    geometry = feature.geometry()
    contour = geometry.removeInteriorRings()  # on garde uniquement le contour extérieur
    abs_contour = contour.constGet()  # permet de transformer un objet QgsGeometry en QgsAbstractGeometry afin
    # d'utiliser la méthode nCoordinates
    facade_count = abs_contour.nCoordinates() - 1  # nCoordinates compte le nombre de points dans la géométrie. On
    # enlève le point qui permet de fermer la géométrie et on obtient le nombre de façades

    # Un attribut num_facade est associé à l'entité. Il sert à utiliser l'expression Qgis qui suit. C'est un attribut
    # temporaire qui n'est pas écrit dans la couche.
    fields = QgsFields()
    field = QgsField('num_facade')
    fields.append(field)
    feature.setFields(fields)

    # On utilise une expression écrite dans la calculatrice de champ Qgis. Concrètement, cela revient à obtenir la
    # géométrie du nième segment du contour d'un bâtiment. Comme l'expression varie en fonction de la géométrie et de
    # l'attribut num_facade associé à l'entité, il faut définir un contexte d'expression
    temporary_expression = QgsExpression('geometry_n(segments_to_lines(exterior_ring($geometry)),"num_facade")')
    temporary_context = QgsExpressionContext()

    count_petite_facade = 0  # initialisation du compteur de petites façades

    # Ceci est la série d'opérations qui permet, pour chaque bâtiment, d'évaluer si chaque façade peut être considérée
    # comme une petite façade extérieure. La classe range ne comprend pas la valeur rentrée dans l'argument stop, c'est
    # pourquoi on rajoute +1
    for n in range(1, facade_count + 1):
        feature['num_facade'] = n  # on rentre la variable d'itération. Cela permet de sélectionner la géométrie du
        # numéro de façade correspondant lorsqu'on évalue l'expression par la suite
        temporary_context.setFeature(feature)  # cette étape permet d'associer à l'expression le bâtiment évalué dans la
        # 1ère boucle
        geometry_facade = temporary_expression.evaluate(temporary_context)
        geometry_facade_bb = geometry_facade.boundingBox()  # cette étape permet d'utiliser la méthode intersects sur
        # l'index spatial. En effet, l'intersection peut uniquement être réalisée avec un objet QgsRectangle. La
        # géométrie est inchangée
        length_facade = geometry_facade.length()
        if length_facade < 2.5:  # avant de faire d'autres opérations, on évalue si la façade à une longueur inférieure
            # à 2.5 m
            is_common_boundary = False  # initialisation d'une variable booléenne pour différencier un segment commun ou
            # non à un autre bâtiment
            intersect_ids = index.intersects(geometry_facade_bb)  # cette étape permet de récupérer tous les
            # identifiants des bâtiments qui intersectent la façade
            # Ainsi, la boucle suivante qui calcule la géométrie résultante de l'intersection et la compare avec la
            # géométrie de la façade est plus rapide car elle n'est effectuée que sur les bâtiments filtrés au préalable
            # avec l'index spatial
            for i in intersect_ids:
                layer_feature = layer.getFeature(i)
                if layer_feature.id() == feature.id():  # on évacue le cas où l'on ferait l'intersection du bâtiment sur
                    # lui-même
                    None
                else:
                    common_boundary = geometry_facade.intersection(layer_feature.geometry())
                    if common_boundary.equals(geometry_facade):  # si la géométrie résultante de l'intersection est
                        # égale à celle de la façade, alors cela veut dire que c'est une façade collée à un autre
                        # bâtiment, on ne la prend pas en compte
                        is_common_boundary = True
            if not is_common_boundary:  # si aucun bâtiment n'est collé à la façade, alors on considère que c'est une façade extérieure
                count_petite_facade += 1

    # Finalement on renseigne la valeur finale de count_petite_facade dans l'attribut n_p_facade pour le bâtiment
    # correspondant
    index_n_p_facade = layer.fields().indexFromName('n_p_facade')
    attrs = {index_n_p_facade: count_petite_facade}
    feature_id = feature.id()
    layer.dataProvider().changeAttributeValues({feature_id: attrs})

stop = datetime.now()  # date de la fin du calcul
print("Durée du calcul :", stop - start)  # on affiche dans la console Python la différence entre les dates de fin et de
# début de calcul pour obtenir le temps de calcul total
