from ezdxf import bbox
from shapely.geometry import Polygon

# 1. Получаем bounding box в локальных координатах самого текста
# (Для этого временно используем специальный инструмент ezdxf)
# ezdxf умеет трансформировать вершины объекта через его матрицу
vertices = bbox.extents([entity]).rect_vertices()

# vertices вернет 4 точки (кортежи x, y, z), которые уже повернуты в 3D пространстве
# Нам нужны только X и Y для 2D геометрии Shapely:
flat_vertices = [(v[0], v[1]) for v in vertices]

# 2. Передаем вершины в Shapely (замыкать контур вручную не нужно, Shapely сделает сам)
shapely_text_contour = Polygon(flat_vertices)

print(shapely_text_contour.wkt)
