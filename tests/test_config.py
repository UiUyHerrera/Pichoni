from nucleo.config import config_vacia, normalizar
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
