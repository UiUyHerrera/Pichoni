from nucleo.config import MAX_TIEMPO_MINUTOS, config_vacia, limite_tiempo_minutos, normalizar, perfil_vacio
from nucleo.version import es_version_nueva


def test_tema_personalizado_es_el_predeterminado():
    assert config_vacia()["tema"] == "pichoni"


def test_tema_valido_se_conserva_y_el_invalido_usa_el_predeterminado():
    assert normalizar({"tema": "claro"})["tema"] == "claro"
    assert normalizar({"tema": "desconocido"})["tema"] == "pichoni"


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
