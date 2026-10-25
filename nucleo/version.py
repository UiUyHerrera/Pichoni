import re

VERSION = "1.0.5"
REPOSITORIO = "UiUyHerrera/Pichoni"
PAGINA_VERSIONES = f"https://github.com/{REPOSITORIO}/releases"


def es_version_nueva(disponible: str, actual: str = VERSION) -> bool:
    patron = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
    coincidencia_disponible = patron.fullmatch(disponible)
    coincidencia_actual = patron.fullmatch(actual)
    if not coincidencia_disponible or not coincidencia_actual:
        return False
    return tuple(map(int, coincidencia_disponible.groups())) > tuple(map(int, coincidencia_actual.groups()))
