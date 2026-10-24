from typing import Any

from .actividad import MAX_ACTIVIDADES, Resolver, construir, personalizado, rota, url_stream
from .config import MIN_ROTACION_MINUTOS, MIN_ROTACION_SEGUNDOS


def buscar(config: dict[str, Any], perfil_id: str | None) -> dict[str, Any] | None:
    return next((p for p in config["perfiles"] if p["id"] == perfil_id), None)


class Motor:
    def __init__(self) -> None:
        self.perfil_id: str | None = None
        self.indice = 0
        self.inicio = 0.0
        self.ultimo_texto = 0.0
        self.ultimo_perfil = 0.0
        self.actividades_omitidas = 0

    def activar(self, perfil_id: str | None, ahora: float) -> None:
        self.perfil_id = perfil_id
        self.indice = 0
        self.inicio = ahora
        self.ultimo_texto = ahora
        self.ultimo_perfil = ahora

    def paso(self, config: dict[str, Any], ahora: float) -> bool:
        cambio = False
        rotar = config["rotar_perfiles"]
        ids = [i for i in rotar["ids"] if buscar(config, i)]
        if rotar["activo"] and ids and config["perfil_activo"] is not None:
            intervalo = max(rotar["minutos"], MIN_ROTACION_MINUTOS) * 60
            if config["perfil_activo"] not in ids:
                config["perfil_activo"] = ids[0]
                cambio = True
            elif len(ids) > 1 and ahora - self.ultimo_perfil >= intervalo:
                siguiente = (ids.index(config["perfil_activo"]) + 1) % len(ids)
                config["perfil_activo"] = ids[siguiente]
                cambio = True
        if config["perfil_activo"] != self.perfil_id:
            self.activar(config["perfil_activo"], ahora)
            return True
        rotan = [p for p in self.mostrados(config) if rota(p)]
        if rotan:
            intervalo = max(rotan[0]["rotar_cada"], MIN_ROTACION_SEGUNDOS)
            if ahora - self.ultimo_texto >= intervalo:
                self.indice += 1
                self.ultimo_texto = ahora
                cambio = True
        return cambio

    def actividades(self, config: dict[str, Any], resolver: Resolver) -> list[dict[str, Any]]:
        propio = personalizado(config["personalizado"])
        mostrados = self.mostrados(config)
        solicitados = [p for p in mostrados if p["tipo"] != "transmitiendo" or url_stream(p["url"])]
        limite_perfiles = MAX_ACTIVIDADES - (1 if propio else 0)
        seleccionados = solicitados[:limite_perfiles]
        ids_solicitados = list(dict.fromkeys(
            [self.perfil_id] + [
                i for i in config.get("perfiles_extra", []) if i != self.perfil_id
            ]
        )) if self.perfil_id is not None else []
        solicitados_validos = sum(buscar(config, i) is not None for i in ids_solicitados)
        self.actividades_omitidas = solicitados_validos - len(seleccionados)
        lista = [propio] if propio else []
        for perfil in seleccionados:
            lista.append(construir(perfil, self.indice, int(self.inicio * 1000), config["app_id"], resolver))
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
