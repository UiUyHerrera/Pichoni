import threading
import time
from unittest.mock import Mock

import app
from app import Api, Bandeja, Servicio
from nucleo.config import config_vacia, perfil_vacio
from nucleo.rotacion import Motor
from nucleo.version import VERSION


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


def test_actualizacion_automatica_lanza_instalador_y_cierra_app(monkeypatch, tmp_path):
    instalador = tmp_path / "Pichoni-Setup-1.2.3.exe"
    lanzado = []
    eventos = []

    class VentanaFalsa:
        def evaluate_js(self, script):
            eventos.append(script)

    class BandejaFalsa:
        def salir(self):
            eventos.append("salir")

    api = Api(None)
    api._ventana = VentanaFalsa()
    api._bandeja = BandejaFalsa()
    api.comprobar_actualizacion = Mock(return_value={
        "estado": "disponible",
        "disponible": "1.2.3",
        "url": "https://github.com/example/Pichoni/releases/download/v1.2.3/Pichoni-Setup-1.2.3.exe",
        "digest": "sha256:" + "a" * 64,
        "tamano": 100,
    })
    monkeypatch.setattr(app, "descargar_instalador", lambda *args: instalador)
    monkeypatch.setattr(app.subprocess, "Popen", lambda args, **kwargs: lanzado.append((args, kwargs)))
    monkeypatch.setattr(app.time, "sleep", lambda _: None)

    api._actualizar_automaticamente()

    assert lanzado[0][0] == [
        str(instalador), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"
    ]
    assert eventos[-1] == "salir"
    assert "Instalando Pichoni 1.2.3" in eventos[0]


def test_actualizacion_automatica_no_hace_nada_si_ya_esta_actualizada(monkeypatch):
    api = Api(None)
    api.comprobar_actualizacion = Mock(return_value={"estado": "actualizada"})

    api._actualizar_automaticamente()

    api.comprobar_actualizacion.assert_called_once_with()


def test_actualizacion_automatica_solo_se_inicia_desde_instalacion_estandar(monkeypatch, tmp_path):
    class ThreadFalsa:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            self.iniciada = False

        def start(self):
            self.iniciada = True

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "executable", str(tmp_path / "Programs" / "Pichoni" / "Pichoni.exe"))
    monkeypatch.setattr(app.threading, "Thread", ThreadFalsa)
    api = Api(None)

    assert api.iniciar_actualizacion_automatica() == {"estado": "buscando"}


def test_actualizacion_portable_no_se_inicia(monkeypatch):
    monkeypatch.setattr(app.sys, "frozen", False, raising=False)
    api = Api(None)

    assert api.iniciar_actualizacion_automatica() == {"estado": "no_aplica"}


def test_cerrar_desde_api_sale_de_pichoni():
    api = Api(None)
    bandeja = Mock()
    api._bandeja = bandeja

    api.cerrar()

    bandeja.salir.assert_called_once_with()


def test_cerrar_desde_api_destruye_ventana_si_no_hay_bandeja():
    api = Api(None)
    ventana = Mock()
    api._ventana = ventana

    api.cerrar()

    ventana.destroy.assert_called_once_with()


def test_salir_desde_bandeja_cierra_app_y_es_idempotente():
    bandeja = Bandeja.__new__(Bandeja)
    bandeja.saliendo = False
    bandeja._salida_candado = threading.Lock()
    bandeja.icono = Mock()
    bandeja.servicio = Mock()
    bandeja.ventana = Mock()

    bandeja.salir()
    bandeja.salir()

    bandeja.icono.stop.assert_called_once_with()
    bandeja.ventana.destroy.assert_called_once_with()


def test_cerrar_ventana_programa_salida_real_despues_de_animacion(monkeypatch):
    bandeja = Bandeja.__new__(Bandeja)
    bandeja.saliendo = False
    bandeja.ventana = Mock()
    temporizador = Mock()
    monkeypatch.setattr(app.threading, "Timer", lambda *args: temporizador)

    assert bandeja.al_cerrar() is False

    bandeja.ventana.evaluate_js.assert_called_once()
    temporizador.start.assert_called_once_with()


def test_comprobar_actualizacion_expone_digest_y_tamano_del_instalador(monkeypatch):
    class RespuestaFalsa:
        status_code = 200

        def json(self):
            return {
                "tag_name": "v99.0.0",
                "assets": [{
                    "name": "Pichoni-Setup-99.0.0.exe",
                    "browser_download_url": "https://github.com/UiUyHerrera/Pichoni/releases/download/v99.0.0/Pichoni-Setup-99.0.0.exe",
                    "digest": "sha256:" + "a" * 64,
                    "size": 12345,
                }],
            }

    monkeypatch.setattr(app.requests, "get", lambda *args, **kwargs: RespuestaFalsa())
    api = Api(None)

    actualizacion = api.comprobar_actualizacion()

    assert actualizacion["estado"] == "disponible"
    assert actualizacion["actual"] == VERSION
    assert actualizacion["digest"] == "sha256:" + "a" * 64
    assert actualizacion["tamano"] == 12345
