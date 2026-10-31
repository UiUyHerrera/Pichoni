from typing import Any

from .actividad import MAX_ACTIVIDADES, Resolver, construir, personalizado, url_stream


def buscar(config: dict[str, Any], perfil_id: str | None) -> dict[str, Any] | None:
    return next((p for p in config["perfiles"] if p["id"] == perfil_id), None)


class Motor:
    def __init__(self) -> None:
        self.perfil_id: str | None = None
        self.indice = 0
        self.inicio = 0.0
        self.actividades_omitidas = 0

    def activar(self, perfil_id: str | None, ahora: float) -> None:
        self.perfil_id = perfil_id
        self.indice = 0
        self.inicio = ahora

    def paso(self, config: dict[str, Any], ahora: float) -> bool:
        if config["perfil_activo"] != self.perfil_id:
            self.activar(config["perfil_activo"], ahora)
            return True
        return False

    def actividades(self, config: dict[str, Any], resolver: Resolver) -> list[dict[str, Any]]:
        propio = personalizado(config["personalizado"])
        mostrados = self.mostrados(config)
        solicitados = [p for p in mostrados if p["tipo"] != "transmitiendo" or url_stream(p["url"])]
        limite_perfiles = MAX_ACTIVIDADES - (1 if propio else 0)
        # The stream goes first so it is the one that keeps the application ID (see below).
        seleccionados = sorted(solicitados[:limite_perfiles], key=lambda p: p["tipo"] != "transmitiendo")
        ids_solicitados = list(dict.fromkeys(
            [self.perfil_id] + [
                i for i in config.get("perfiles_extra", []) if i != self.perfil_id
            ]
        )) if self.perfil_id is not None else []
        solicitados_validos = sum(buscar(config, i) is not None for i in ids_solicitados)
        self.actividades_omitidas = solicitados_validos - len(seleccionados)
        lista = [propio] if propio else []
        con_id = False
        nombres: set[str] = set()
        for perfil in seleccionados:
            actividad = construir(perfil, self.indice, int(self.inicio * 1000), config["app_id"], resolver)
            # Discord hides activities that repeat a name, so repeats get invisible filler characters.
            while actividad["name"] in nombres:
                actividad["name"] += "ㅤ"
            nombres.add(actividad["name"])
            # The profile shows one activity per application ID, so only the first keeps it (and its buttons).
            if "application_id" in actividad:
                if con_id:
                    for clave in ("application_id", "buttons", "metadata"):
                        actividad.pop(clave)
                con_id = True
            lista.append(actividad)
        return lista

    def mostrados(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        if self.perfil_id is None:
            return []
        ids = [self.perfil_id] + [i for i in config.get("perfiles_extra", []) if i != self.perfil_id]
        perfiles: list[dict[str, Any]] = []
        tipos: set[str] = set()
        for perfil in (buscar(config, i) for i in ids):
            if perfil is None or perfil["tipo"] in tipos:
                continue
            tipos.add(perfil["tipo"])
            perfiles.append(perfil)
            if len(perfiles) == MAX_ACTIVIDADES:
                break
        return perfiles
