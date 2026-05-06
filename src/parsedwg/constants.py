"""Constant values used across the package."""

import enum

# Return codes.
OK = 0
ERROR = 1
NOT_FOUND = 2
UNBOUND_ERROR = 3

BUFFER_SIZE = 40


class EntityType(int, enum.Enum):
    """The type of the `File` and `DXF` entity."""

    # Folders and files
    FOLDER = 0
    FILE = 1
    ZIPFILE = 2
    ZIPPED_FILE = 3

    # DXF entities
    BLOCK = 4
    LAYOUT = 5
    LAYER = 6
    _3DFACE = 7
    _3DSOLID = 8
    ACAD_PROXY_ENTITY = 9
    ARC = 10
    ATTDEF = 11
    ATTRIB = 12
    BODY = 13
    CIRCLE = 14
    COORDINATION_MODEL = 15
    DIMENSION = 16
    ELLIPSE = 17
    HATCH = 18
    HELIX = 19
    IMAGE = 20
    INSERT = 21
    LEADER = 22
    LIGHT = 23
    LINE = 24
    LWPOLYLINE = 25
    MESH = 26
    MLEADER = 27
    MLEADERSTYLE = 28
    MLINE = 29
    MTEXT = 30
    OLEFRAME = 31
    OLE2FRAME = 32
    POINT = 33
    POLYLINE = 34
    RAY = 35
    REGION = 36
    SECTION = 37
    SEQEND = 38
    SHAPE = 39
    SOLID = 40
    SPLINE = 41
    SUN = 42
    SURFACE = 43
    TABLE = 44
    TEXT = 45
    TOLERANCE = 46
    TRACE = 47
    UNDERLAY = 48
    VERTEX = 49
    VIEWPORT = 50
    WIPEOUT = 51
    XLINE = 52
    PRIMITIVE= 53

ENTITY_TYPES = {e.name: e for e in EntityType}


# Словарь расшифровки материалов
ANSI_MAP = {
    'ANSI31': 'Чугун / Кирпич',
    'ANSI32': 'Сталь',
    'ANSI33': 'Медь / Латунь',
    'ANSI34': 'Пластик / Резина',
    'ANSI35': 'Огнеупорный кирпич',
    'ANSI36': 'Мрамор / Стекло',
    'ANSI37': 'Свинец / Изоляция',
    'ANSI38': 'Алюминий'
}

