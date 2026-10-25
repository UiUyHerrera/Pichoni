from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

from pypresence import ActivityType

from app import Api, Servicio
from nucleo.config import config_vacia
from nucleo.rpc import ConexionRPC
from nucleo.rotacion import Motor


class PresenciaFalsa:
    def __init__(self):
        self.actualizaciones = []
        self.limpiezas = 0

    def update(self, **actividad):
        self.actualizaciones.append(actividad)

    def clear(self):
        self.limpiezas += 1


def test_rpc_publica_una_actividad_compatible_y_filtra_imagenes_y_botones():
    conexion = ConexionRPC("123")
    conexion.actualizar([
        {"type": 4, "state": "Estado personalizado"},
        {
            "type": 2,
            "name": "Escuchando",
            "details": "Un álbum",
            "timestamps": {"start": 1_700_000_000_000},
            "assets": {
                "large_image": "https://images.example/cover.png",
                "large_text": "Portada",
                "small_image": "mp:resuelta",
            },
            "buttons": ["Abrir enlace", "No seguro"],
            "metadata": {"button_urls": ["https://example.com", "http://example.com"]},
        },
        {"type": 3, "name": "Viendo"},
    ], "online")
    presencia = PresenciaFalsa()

    conexion._publicar(presencia)

    assert conexion.actividades_omitidas == 2
    assert len(presencia.actualizaciones) == 1
    actividad = presencia.actualizaciones[0]
    assert actividad["activity_type"] == ActivityType(2)
    assert actividad["details"] == "Un álbum"
    assert actividad["start"] == 1_700_000_000
    assert actividad["large_image"] == "https://images.example/cover.png"
    assert actividad["small_image"] is None
    assert actividad["buttons"] == [{"label": "Abrir enlace", "url": "https://example.com"}]


def test_rpc_limpia_presencia_si_no_hay_actividad_compatible():
    conexion = ConexionRPC("123")
    conexion.actualizar([{"type": 1}, {"type": 4}], "online")
    presencia = PresenciaFalsa()

    conexion._publicar(presencia)

    assert conexion.actividades_omitidas == 2
    assert presencia.limpiezas == 1
    assert presencia.actualizaciones == []


def test_estado_del_servicio_funciona_con_conexion_rpc_sin_token():
    servicio = Servicio.__new__(Servicio)
    servicio.candado = RLock()
    servicio.config = config_vacia()
    servicio.motor = Motor()
    servicio.conexion = ConexionRPC("123")
    servicio.usuario = None
    servicio.compartir = None
    servicio.token = ""
    servicio.token_invalido = False
    servicio.revision = 0

    estado = servicio.estado()

    assert estado["modo_conexion"] == "rpc"
    assert estado["conectado"] is False
    assert estado["tiene_token"] is False
    assert estado["visible"] is None


def servicio_falso(modo, token=""):
    servicio = Mock()
    servicio.candado = RLock()
    servicio.config = config_vacia()
    servicio.config["modo_conexion"] = modo
    servicio.token = token
    servicio.conexion = Mock()
    servicio.imagenes = Mock()
    servicio.usuario = {"username": "usuario"}
    servicio.compartir = True
    servicio.guardar_config = Mock()
    servicio.conectar_rpc = Mock()
    servicio.conectar_token = Mock()
    servicio.estado = lambda: {"config": servicio.config}
    return servicio


def test_cambiar_a_rpc_detiene_conexion_token_y_conserva_el_token():
    servicio = servicio_falso("token", "token-guardado")
    conexion_anterior = servicio.conexion

    resultado = Api(servicio).cambiar_modo_conexion("rpc")

    conexion_anterior.detener.assert_called_once_with()
    servicio.conectar_rpc.assert_called_once_with()
    servicio.conectar_token.assert_not_called()
    assert servicio.token == "token-guardado"
    assert resultado["config"]["modo_conexion"] == "rpc"
    assert resultado["config"]["inicio_completado"] is True


def test_seleccionar_rpc_en_el_inicio_marca_la_bienvenida_completada():
    servicio = servicio_falso("rpc")
    servicio.config["inicio_completado"] = False

    Api(servicio).cambiar_modo_conexion("rpc")

    assert servicio.config["inicio_completado"] is True
    servicio.guardar_config.assert_called_once_with()


def test_cambiar_a_token_sin_credenciales_no_inicia_conexion():
    servicio = servicio_falso("rpc")
    conexion_anterior = servicio.conexion

    Api(servicio).cambiar_modo_conexion("token")

    conexion_anterior.detener.assert_called_once_with()
    servicio.conectar_token.assert_not_called()
    servicio.conectar_rpc.assert_not_called()
    assert servicio.config["modo_conexion"] == "token"


def test_modo_de_conexion_invalido_no_modifica_la_configuracion():
    servicio = servicio_falso("rpc")

    resultado = Api(servicio).cambiar_modo_conexion("desconocido")

    assert resultado == {"error": "Modo de conexión no válido."}
    assert servicio.config["modo_conexion"] == "rpc"
    servicio.guardar_config.assert_not_called()


def test_eliminar_token_cambia_a_rpc_y_borra_archivo(tmp_path):
    servicio = servicio_falso("token", "token-guardado")
    archivo_token = tmp_path / "token.txt"
    archivo_token.write_text("token-guardado", encoding="utf-8")
    servicio.almacen = SimpleNamespace(archivo_token=Path(archivo_token))
    conexion_anterior = servicio.conexion

    resultado = Api(servicio).borrar_token()

    assert not archivo_token.exists()
    assert servicio.token == ""
    assert servicio.config["modo_conexion"] == "rpc"
    conexion_anterior.detener.assert_called_once_with()
    servicio.conectar_rpc.assert_called_once_with()
    assert resultado["config"]["modo_conexion"] == "rpc"


def test_error_al_eliminar_token_no_simula_un_cierre_exitoso():
    servicio = servicio_falso("token", "token-guardado")
    servicio.almacen = SimpleNamespace(
        archivo_token=SimpleNamespace(unlink=Mock(side_effect=PermissionError("acceso denegado")))
    )
    conexion_anterior = servicio.conexion

    resultado = Api(servicio).borrar_token()

    assert resultado["error"].startswith("No se pudo eliminar el token guardado:")
    assert servicio.token == "token-guardado"
    assert servicio.config["modo_conexion"] == "token"
    conexion_anterior.detener.assert_not_called()
