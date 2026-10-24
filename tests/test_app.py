import threading
import time

from app import Servicio
from nucleo.config import config_vacia, perfil_vacio
from nucleo.rotacion import Motor


class ConexionFalsa:
    def __init__(self):
        self.actualizaciones = []

    def actualizar(self, actividades, punto):
        self.actualizaciones.append((actividades, punto))


class ImagenesFalsas:
    def __init__(self, resolver):
        self._resolver = resolver

    def resolver(self, url, app_id=None):
        return self._resolver(url, app_id)


def servicio_para_aplicar(imagenes):
    servicio = Servicio.__new__(Servicio)
    servicio.candado = threading.RLock()
    servicio.aplicar_candado = threading.Lock()
    servicio.config = config_vacia()
    perfil = perfil_vacio("Perfil")
    perfil["imagen"]["url"] = "https://images.example/test.png"
    servicio.config["perfiles"] = [perfil]
    servicio.config["perfil_activo"] = perfil["id"]
    servicio.motor = Motor()
    servicio.motor.activar(perfil["id"], time.time())
    servicio.conexion = ConexionFalsa()
    servicio.imagenes = imagenes
    servicio.ultimo_envio = 0
    servicio.pendiente = False
    return servicio


def test_resolver_no_bloquea_el_candado_y_descarta_resultado_obsoleto():
    entro_resolver = threading.Event()
    continuar_resolver = threading.Event()

    def resolver(url, app_id):
        entro_resolver.set()
        assert continuar_resolver.wait(3)
        return "mp:resolved"

    servicio = servicio_para_aplicar(ImagenesFalsas(resolver))
    hilo = threading.Thread(target=servicio.aplicar)
    hilo.start()
    assert entro_resolver.wait(2)

    inicio = time.monotonic()
    with servicio.candado:
        servicio.config["punto"] = "idle"
    assert time.monotonic() - inicio < 0.5

    continuar_resolver.set()
    hilo.join(3)

    assert not hilo.is_alive()
    assert servicio.conexion.actualizaciones == []
    assert servicio.pendiente is True


def test_aplicar_usa_app_id_capturado_y_envia_actividad():
    recibidos = []

    def resolver(url, app_id):
        recibidos.append((url, app_id))
        return "mp:resolved"

    servicio = servicio_para_aplicar(ImagenesFalsas(resolver))
    servicio.config["app_id"] = "123456"

    servicio.aplicar()

    assert recibidos == [("https://images.example/test.png", "123456")]
    assert len(servicio.conexion.actualizaciones) == 1
    actividades, punto = servicio.conexion.actualizaciones[0]
    assert actividades[0]["assets"]["large_image"] == "mp:resolved"
    assert punto == "online"
