from nucleo.actividad import construir, personalizado
from nucleo.config import migrar_estados, normalizar, normalizar_perfil, perfil_vacio


def resolver(url: str) -> str | None:
    return "mp:" + url.rsplit("/", 1)[-1] if url.startswith("https://") else None


def perfil(**cambios):
    p = perfil_vacio("Prueba", "jugando")
    p["nombre"] = "Minecraft"
    p.update(cambios)
    return normalizar_perfil(p)


def test_basico_sin_extras():
    a = construir(perfil(), 0, 1000, "1", resolver)
    assert a == {"name": "Minecraft", "type": 0}


def test_textos_rotan_por_indice_y_saltan_vacios():
    p = perfil(detalles=["uno", "", "dos"], texto=["solo"])
    assert construir(p, 0, 0, "1", resolver)["details"] == "uno"
    assert construir(p, 1, 0, "1", resolver)["details"] == "dos"
    assert construir(p, 2, 0, "1", resolver)["details"] == "uno"
    assert construir(p, 5, 0, "1", resolver)["state"] == "solo"


def test_stream_solo_usa_un_enlace_valido():
    assert construir(perfil(tipo="transmitiendo", url="https://twitch.tv/x"), 0, 0, "1", resolver)["url"] == "https://twitch.tv/x"
    assert construir(perfil(tipo="transmitiendo", url="https://youtube.com/@x"), 0, 0, "1", resolver)["url"] == "https://youtube.com/@x"
    assert "url" not in construir(perfil(tipo="transmitiendo", url=""), 0, 0, "1", resolver)
    assert "url" not in construir(perfil(tipo="transmitiendo", url="nada"), 0, 0, "1", resolver)
    assert "url" not in construir(perfil(tipo="transmitiendo", url="https://aimgearz.cl/"), 0, 0, "1", resolver)


def test_imagenes_y_botones_llevan_app_id():
    p = perfil(
        imagen={"url": "https://x.com/a.png", "texto": "hola"},
        imagen_chica={"url": "https://x.com/b.png", "texto": ""},
        botones=[{"texto": "Canal", "url": "https://twitch.tv/x"}, {"texto": "Malo", "url": "ftp://x"}],
    )
    a = construir(p, 0, 0, "999", resolver)
    assert a["application_id"] == "999"
    assert a["assets"] == {"large_image": "mp:a.png", "large_text": "hola", "small_image": "mp:b.png"}
    assert a["buttons"] == ["Canal"]
    assert a["metadata"] == {"button_urls": ["https://twitch.tv/x"]}


def test_imagen_que_no_resuelve_se_omite():
    a = construir(perfil(imagen={"url": "http://x/a.png", "texto": ""}), 0, 0, "1", resolver)
    assert "assets" not in a and "application_id" not in a


def test_tiempos():
    assert construir(perfil(tiempo={"modo": "transcurrido", "minutos": 5}), 0, 5000, "1", resolver)["timestamps"] == {"start": 5000}
    assert construir(perfil(tiempo={"modo": "regresiva", "minutos": 2}), 0, 5000, "1", resolver)["timestamps"] == {"end": 125000}


def test_tiempo_fake_de_444_anios_envia_timestamp_unix_negativo():
    actividad = construir(
        perfil(tiempo={"modo": "fingido", "minutos": 444 * 525_600}),
        0,
        1_800_000_000_000,
        "1",
        resolver,
    )

    assert actividad["timestamps"]["start"] == 1_800_000_000_000 - 444 * 525_600 * 60_000
    assert actividad["timestamps"]["start"] < 0


def test_transmision_no_envia_tiempos_manuales():
    p = perfil(tipo="transmitiendo", tiempo={"modo": "regresiva", "minutos": 2})
    assert "timestamps" not in construir(p, 0, 5000, "1", resolver)


def test_personalizado():
    assert personalizado({"texto": "", "emoji": ""}) is None
    assert personalizado({"texto": "hola", "emoji": "🔥"}) == {"name": "Custom Status", "type": 4, "state": "hola", "emoji": {"name": "🔥"}}


def test_normalizar_limpia_basura():
    c = normalizar({"punto": "raro", "perfiles": [{"tipo": "x", "rotar_cada": 1, "detalles": "uno"}], "perfil_activo": "nope", "app_id": "abc"})
    assert c["punto"] == "online"
    assert c["perfiles"][0]["tipo"] == "jugando"
    assert c["perfiles"][0]["rotar_cada"] == 15
    assert c["perfiles"][0]["detalles"] == ["uno"]
    assert c["perfil_activo"] is None
    assert c["app_id"].isdigit()


def test_migrar_estados_viejos():
    viejo = {
        "punto": "dnd",
        "app_id": "123",
        "tipo": "transmitiendo",
        "transmitiendo": {"nombre": "Min", "detalles": "d", "texto": "t", "url": "https://twitch.tv/a", "foto": "https://i/a.png", "foto_texto": "f"},
        "jugando": {"nombre": "Cyber", "detalles": "", "texto": "", "foto": "", "foto_texto": ""},
    }
    c = migrar_estados(viejo)
    activo = next(p for p in c["perfiles"] if p["id"] == c["perfil_activo"])
    assert c["punto"] == "dnd" and c["app_id"] == "123"
    assert activo["tipo"] == "transmitiendo" and activo["imagen"] == {"url": "https://i/a.png", "texto": "f"}
    assert len(c["perfiles"]) == 2
