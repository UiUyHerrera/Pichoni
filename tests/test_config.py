from nucleo.config import Almacen, MAX_TIEMPO_MINUTOS, config_vacia, limite_tiempo_minutos, normalizar, perfil_vacio
from nucleo.version import es_version_nueva


def test_tema_personalizado_es_el_predeterminado():
    assert config_vacia()["tema"] == "pichoni"
    assert config_vacia()["color_marca"] == "#280060"
    assert config_vacia()["color_botones"] == ""
    assert config_vacia()["color_fondo"] == ""
    assert config_vacia()["color_paneles"] == ""
    assert config_vacia()["color_barra_lateral"] == ""
    assert config_vacia()["color_texto"] == ""


def test_modo_rpc_es_predeterminado_y_configuraciones_antiguas_mantienen_token():
    assert config_vacia()["modo_conexion"] == "rpc"
    assert config_vacia()["inicio_completado"] is False
    assert normalizar({"perfiles": []})["modo_conexion"] == "token"
    assert normalizar({"modo_conexion": "rpc"})["modo_conexion"] == "rpc"
    assert normalizar({"modo_conexion": "rpc"})["inicio_completado"] is False
    assert normalizar({"modo_conexion": "token"})["modo_conexion"] == "token"
    assert normalizar({"modo_conexion": "token"})["inicio_completado"] is True
    assert normalizar({"modo_conexion": "invalido"})["modo_conexion"] == "rpc"


def test_instalacion_nueva_muestra_un_perfil_rpc_compatible(tmp_path):
    configuracion = Almacen(tmp_path).cargar()

    assert configuracion["modo_conexion"] == "rpc"
    assert configuracion["inicio_completado"] is False
    assert configuracion["perfiles"][0]["tipo"] == "jugando"


def test_tema_anterior_se_normaliza_a_la_base_pichoni():
    assert normalizar({"tema": "claro"})["tema"] == "pichoni"
    assert normalizar({"tema": "desconocido"})["tema"] == "pichoni"


def test_color_marca_valido_se_conserva_y_el_invalido_usa_el_predeterminado():
    assert normalizar({"color_marca": "#A1b2C3"})["color_marca"] == "#a1b2c3"
    assert normalizar({"color_marca": "rojo"})["color_marca"] == "#280060"
    assert normalizar({"color_marca": "#12345"})["color_marca"] == "#280060"


def test_colores_personalizados_validos_se_conservan_y_los_invalidos_se_ignoran():
    config = normalizar({
        "color_botones": "#A1b2C3",
        "color_fondo": "#A1b2C3",
        "color_paneles": "#123456",
        "color_barra_lateral": "rojo",
        "color_texto": "#12345",
    })

    assert config["color_botones"] == "#a1b2c3"
    assert config["color_fondo"] == "#a1b2c3"
    assert config["color_paneles"] == "#123456"
    assert config["color_barra_lateral"] == ""
    assert config["color_texto"] == ""


def test_la_rotacion_legacy_se_desactiva_al_cargar_configuracion():
    config = normalizar({
        "rotar_perfiles": {"activo": True, "ids": ["perfil"], "minutos": 5},
    })

    assert config["rotar_perfiles"]["activo"] is False
    assert config["rotar_perfiles"]["ids"] == []


def test_compara_versiones_de_actualizacion():
    assert es_version_nueva("1.1.0", "1.0.9")
    assert es_version_nueva("v2.0.0", "1.9.9")
    assert not es_version_nueva("1.0.0", "1.0.0")
    assert not es_version_nueva("version-invalida", "1.0.0")


def test_tiempo_configurado_se_limita_a_timestamps_unix_validos():
    perfil = perfil_vacio()
    perfil["tiempo"] = {
        "modo": "fingido",
        "minutos": 444 * 525_600,
        "total": 444 * 525_600,
    }

    normalizado = normalizar({"perfiles": [perfil]})["perfiles"][0]["tiempo"]

    assert normalizado["minutos"] == limite_tiempo_minutos()
    assert normalizado["total"] == MAX_TIEMPO_MINUTOS


def test_limite_del_fake_time_es_la_epoca_unix_actual():
    assert 0 < limite_tiempo_minutos(1_800_000_000) <= MAX_TIEMPO_MINUTOS


def test_duracion_regresiva_puede_superar_la_epoca_unix():
    perfil = perfil_vacio()
    perfil["tiempo"] = {"modo": "regresiva", "minutos": 444 * 525_600}

    normalizado = normalizar({"perfiles": [perfil]})["perfiles"][0]["tiempo"]

    assert normalizado["minutos"] == MAX_TIEMPO_MINUTOS


def test_tiempo_configurado_no_supera_el_timestamp_unix_actual():
    perfil = perfil_vacio()
    perfil["tiempo"] = {
        "modo": "fingido",
        "minutos": 445 * 525_600,
        "total": 445 * 525_600,
    }

    normalizado = normalizar({"perfiles": [perfil]})["perfiles"][0]["tiempo"]

    assert normalizado["minutos"] == limite_tiempo_minutos()
    assert normalizado["total"] == MAX_TIEMPO_MINUTOS
