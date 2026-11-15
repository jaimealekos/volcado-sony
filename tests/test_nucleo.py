# -*- coding: utf-8 -*-
"""Pruebas de `volcadosony.nucleo`: tarjeta falsa en `tmp_path`, sin red."""

import os
import threading
import time
from datetime import date, datetime
from pathlib import Path

import pytest

from volcadosony import nucleo


# ------------------------------- Utilidades ------------------------------- #

def tarjeta_falsa(tmp_path):
    origen = tmp_path / "tarjeta"
    (origen / "PRIVATE" / "M4ROOT" / "CLIP").mkdir(parents=True)
    (origen / "PRIVATE" / "M4ROOT" / "SUB").mkdir(parents=True)
    return origen


def crear_bruto(origen, nombre, tamano, mtime=None):
    ruta = origen / "PRIVATE" / "M4ROOT" / "CLIP" / nombre
    ruta.write_bytes(b"\0" * tamano)
    if mtime is not None:
        os.utime(ruta, (mtime, mtime))
    return ruta


def crear_xml(origen, nombre, fecha_iso):
    ruta = origen / "PRIVATE" / "M4ROOT" / "CLIP" / nombre
    ruta.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<NonRealTimeMeta xmlns="urn:schemas-professionalDisc:nonRealTimeMeta:ver.2.20">\n'
        f'  <CreationDate value="{fecha_iso}"/>\n'
        '</NonRealTimeMeta>\n',
        encoding="utf-8")
    return ruta


def crear_proxy(origen, nombre, tamano, carpeta="SUB"):
    ruta = origen / "PRIVATE" / "M4ROOT" / carpeta / nombre
    ruta.write_bytes(b"\0" * tamano)
    return ruta


def ts(anio, mes, dia, hora=10):
    return datetime(anio, mes, dia, hora, 0, 0).timestamp()


# ------------------------- Criterio 1: escanear --------------------------- #

def test_escanear_empareja_proxies_y_lee_la_fecha(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 1000, mtime=ts(2024, 1, 1))
    crear_xml(origen, "c0001m01.xml", "2024-11-05T10:00:00Z")
    crear_proxy(origen, "C0001S03.MP4", 100)
    crear_bruto(origen, "C0002.MP4", 2000, mtime=ts(2024, 11, 6, 12))
    crear_proxy(origen, "C0002S03.MP4", 200, carpeta="CLIP")
    crear_proxy(origen, "C0009S03.MP4", 300)

    avisos = []
    clips, huerfanos = nucleo.escanear(origen, avisos.append)

    assert [c.ruta.name for c in clips] == ["C0001.MP4", "C0002.MP4"]
    assert huerfanos == 1
    assert avisos == []

    primero, segundo = clips
    assert primero.tamano == 1000
    assert primero.proxy.name == "C0001S03.MP4"
    assert primero.xml.name == "c0001m01.xml"
    assert primero.fecha == date(2024, 11, 5)
    assert primero.fuente_fecha == "XML"

    assert segundo.proxy.name == "C0002S03.MP4"
    assert segundo.xml is None
    assert segundo.fecha == date(2024, 11, 6)
    assert segundo.fuente_fecha == "FS"


def test_escanear_avisa_si_el_xml_es_ilegible(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 10, mtime=ts(2024, 3, 4))
    (origen / "PRIVATE" / "M4ROOT" / "CLIP" / "C0001M01.XML").write_text(
        "<NonRealTimeMeta><CreationDate", encoding="utf-8")

    avisos = []
    clips, _ = nucleo.escanear(origen, avisos.append)

    assert clips[0].fuente_fecha == "FS"
    assert clips[0].fecha == date(2024, 3, 4)
    assert len(avisos) == 1
    assert "XML ilegible" in avisos[0]


# --------------------- Criterio 2: jornadas y descripción ------------------ #

def test_agrupar_jornadas_ordena_e_indexa(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    for n in range(1, 8):
        crear_bruto(origen, f"C000{n}.MP4", 1_000_000, mtime=ts(2024, 11, 5))
    for n in range(8, 10):
        crear_bruto(origen, f"C000{n}.MP4", 1_000_000, mtime=ts(2024, 11, 6))
    clips, _ = nucleo.escanear(origen, lambda _: None)

    jornadas = nucleo.agrupar_jornadas(clips)

    assert [j.indice for j in jornadas] == [1, 2]
    assert [j.fecha for j in jornadas] == [date(2024, 11, 5), date(2024, 11, 6)]
    assert [len(j.clips) for j in jornadas] == [7, 2]
    assert jornadas[0].peso == 7_000_000
    assert jornadas[0].con_proxy == 0


def test_describir_jornada_corta_a_seis_nombres(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    for n in range(1, 8):
        crear_bruto(origen, f"C000{n}.MP4", 1_000_000, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)
    jornada = nucleo.agrupar_jornadas(clips)[0]

    d = nucleo.describir_jornada(jornada, 1)

    assert d["indice"] == 1
    assert d["titulo"] == "Lote 1/1"
    assert d["fecha"] == "martes 5 de noviembre de 2024"
    assert d["detalle"] == "7 clips · 7 MB · 0 proxies"
    assert d["nombres"] == [f"C000{n}.MP4" for n in range(1, 7)]
    assert d["primero"] == "C0001.MP4"
    assert d["ultimo"] == "C0007.MP4"
    assert d["mas"] == 1
    assert d["peso"] == 7_000_000
    assert d["brutos"] == 7
    assert d["proxies"] == 0
    assert d["necesario"] == 7_000_000


# -------------------------- Criterio 3: volcar ---------------------------- #

def test_volcar_estructura_orden_y_omitidos(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 60, mtime=ts(2024, 11, 6))
    crear_xml(origen, "C0001M01.XML", "2024-11-06T09:00:00Z")
    crear_proxy(origen, "C0001S03.MP4", 20)
    crear_bruto(origen, "C0002.MP4", 40, mtime=ts(2024, 11, 5))
    crear_xml(origen, "C0002M01.XML", "2024-11-05T09:00:00Z")
    crear_proxy(origen, "C0002S03.MP4", 10)

    avisos = []
    clips, huerfanos = nucleo.escanear(origen, avisos.append)
    assert huerfanos == 0
    total = sum(f.stat().st_size
                for f in (origen / "PRIVATE" / "M4ROOT" / "CLIP").iterdir()
                if f.is_file())
    total += sum(f.stat().st_size for f in (origen / "PRIVATE" / "M4ROOT" / "SUB").iterdir())

    destino = tmp_path / "destino"
    progresos, errores = [], []
    resultados, errs, segundos = nucleo.volcar(
        clips, destino, avisos.append, progresos.append, errores.append,
        threading.Event(), threading.Event())

    # Orden de la v1: por jornada, y en cada clip bruto -> xml -> proxy.
    assert [(r[0].name, r[2], r[3]) for r in resultados] == [
        ("C0002.MP4", "bruto", "copiado"),
        ("C0002M01.XML", "xml", "copiado"),
        ("C0002S03.MP4", "proxy", "copiado"),
        ("C0001.MP4", "bruto", "copiado"),
        ("C0001M01.XML", "xml", "copiado"),
        ("C0001S03.MP4", "proxy", "copiado"),
    ]
    assert errs == [] and errores == []
    assert segundos >= 0
    assert (destino / "C0002.MP4").read_bytes() == \
        (origen / "PRIVATE" / "M4ROOT" / "CLIP" / "C0002.MP4").read_bytes()
    assert (destino / "_xml" / "C0002M01.XML").is_file()
    assert (destino / "Proxies" / "C0002_Proxy.MP4").is_file()
    assert not (destino / "Proxies" / "C0002S03.MP4").exists()
    assert not list(destino.rglob("*.part"))

    # `copystat`: la fecha del original se conserva.
    origen_bruto = origen / "PRIVATE" / "M4ROOT" / "CLIP" / "C0002.MP4"
    assert (destino / "C0002.MP4").stat().st_mtime == pytest.approx(
        origen_bruto.stat().st_mtime, abs=0.01)

    ultimo = progresos[-1]
    assert ultimo.total_total == total
    assert ultimo.total_hecho == total
    assert ultimo.visibles_total == 4
    assert ultimo.visibles_hechos == 4
    assert progresos[0].lote == "LOTE 1/2 · 05/11"
    assert ultimo.lote == "LOTE 2/2 · 06/11"

    # Segunda pasada: todo idéntico se omite y ningún fichero se retoca.
    fechas = {r[1]: r[1].stat().st_mtime_ns for r in resultados}
    resultados2, errs2, _ = nucleo.volcar(
        clips, destino, avisos.append, lambda _: None, errores.append,
        threading.Event(), threading.Event())

    assert [r[3] for r in resultados2] == ["omitido"] * 6
    assert errs2 == []
    assert {r[1]: r[1].stat().st_mtime_ns for r in resultados2} == fechas


# ------------------------ Criterio 4: cancelación ------------------------- #

def test_volcar_continua_tras_un_error_de_copia(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    crear_bruto(origen, "C0002.MP4", 40, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)

    destino = tmp_path / "destino"
    (destino / "C0001.MP4").mkdir(parents=True)
    errores = []
    resultados, errs, _ = nucleo.volcar(
        clips, destino, lambda _: None, lambda _: None, errores.append,
        threading.Event(), threading.Event())

    assert len(errs) == 1 and "C0001.MP4" in errs[0]
    assert errores == errs
    assert [r[0].name for r in resultados] == ["C0002.MP4"]
    assert (destino / "C0002.MP4").is_file()
    assert not list(destino.rglob("*.part"))


def test_volcar_con_cancelar_lanza_cancelado_sin_part(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    crear_xml(origen, "C0001M01.XML", "2024-11-05T09:00:00Z")
    crear_proxy(origen, "C0001S03.MP4", 20)
    clips, _ = nucleo.escanear(origen, lambda _: None)

    destino = tmp_path / "destino"
    cancelar = threading.Event()
    cancelar.set()

    with pytest.raises(nucleo.Cancelado):
        nucleo.volcar(clips, destino, lambda _: None, lambda _: None,
                      lambda _: None, cancelar, threading.Event())

    assert not list(destino.rglob("*.part"))
    assert [p for p in destino.rglob("*") if p.is_file()] == []


def test_volcar_cancelado_a_mitad_de_fichero_borra_el_part(tmp_path, monkeypatch):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 100, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)
    monkeypatch.setattr(nucleo, "CHUNK", 10)

    class EventoTrasDosConsultas:
        """Devuelve False las dos primeras veces y True después."""

        def __init__(self):
            self.consultas = 0

        def is_set(self):
            self.consultas += 1
            return self.consultas > 2

    destino = tmp_path / "destino"
    with pytest.raises(nucleo.Cancelado):
        nucleo.volcar(clips, destino, lambda _: None, lambda _: None,
                      lambda _: None, EventoTrasDosConsultas(),
                      threading.Event())

    assert not list(destino.rglob("*.part"))
    assert not (destino / "C0001.MP4").exists()


# ------------------- Criterio 8: pausa y tiempo activo ------------------- #

def test_volcar_en_pausa_no_cuenta_el_tiempo_pausado(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    crear_bruto(origen, "C0002.MP4", 70, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)

    destino = tmp_path / "destino"
    pausa = threading.Event()
    pausa.set()
    threading.Timer(0.3, pausa.clear).start()
    progresos = []
    inicio = time.monotonic()
    resultados, errores, segundos = nucleo.volcar(
        clips, destino, lambda _: None, progresos.append, lambda _: None,
        threading.Event(), pausa)
    total = time.monotonic() - inicio

    assert errores == []
    assert [r[3] for r in resultados] == ["copiado", "copiado"]
    assert total >= 0.25
    assert segundos < total - 0.2
    assert any(p.pausado for p in progresos)


def test_volcar_cancelado_en_pausa_lleva_los_resultados(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    crear_bruto(origen, "C0002.MP4", 70, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)

    destino = tmp_path / "destino"
    pausa = threading.Event()
    cancelar = threading.Event()

    def al_progresar(progreso):
        if progreso.visibles_hechos >= 1 and not pausa.is_set():
            pausa.set()
            threading.Timer(0.2, cancelar.set).start()

    with pytest.raises(nucleo.Cancelado) as info:
        nucleo.volcar(clips, destino, lambda _: None, al_progresar,
                      lambda _: None, cancelar, pausa)

    error = info.value
    assert [r[3] for r in error.resultados] == ["copiado"]
    assert error.errores == []
    assert error.segundos >= 0
    assert not list(destino.rglob("*.part"))


# --------------------- Criterio 9: borrar lo copiado ---------------------- #

def test_borrar_copiados_respeta_omitidos_y_carpetas_no_vacias(tmp_path):
    destino = tmp_path / "destino"
    (destino / "_xml").mkdir(parents=True)
    (destino / "Proxies").mkdir()
    copiado = destino / "C0001.MP4"
    copiado.write_bytes(b"copiado")
    omitido = destino / "C0002.MP4"
    omitido.write_bytes(b"omitido")
    xml = destino / "_xml" / "C0001M01.XML"
    xml.write_bytes(b"xml")
    proxy = destino / "Proxies" / "C0001_Proxy.MP4"
    proxy.write_bytes(b"proxy")
    extra = destino / "nota.txt"
    extra.write_bytes(b"extra")

    resultados = [
        (tmp_path / "origen1", copiado, "bruto", "copiado"),
        (tmp_path / "origen2", omitido, "bruto", "omitido"),
        (tmp_path / "origen3", xml, "xml", "copiado"),
        (tmp_path / "origen4", proxy, "proxy", "copiado"),
    ]
    borrados, errores = nucleo.borrar_copiados(resultados, destino, lambda _: None)

    assert borrados == 3
    assert errores == []
    assert not copiado.exists()
    assert not xml.exists()
    assert not proxy.exists()
    assert omitido.is_file()
    assert extra.is_file()
    assert destino.is_dir()
    assert not (destino / "_xml").exists()
    assert not (destino / "Proxies").exists()


def test_copia_sobre_fichero_distinto_es_reemplazado_y_no_se_borra(tmp_path):
    src = tmp_path / "C0001.MP4"
    src.write_bytes(b"nuevo contenido")
    destino = tmp_path / "destino"
    destino.mkdir()
    dst = destino / "C0001.MP4"
    dst.write_bytes(b"viejo")

    estado = nucleo.copiar_archivo(src, dst, lambda _: None, lambda _: None,
                                   threading.Event(), threading.Event())
    borrados, _ = nucleo.borrar_copiados([(src, dst, "bruto", estado)],
                                         destino, lambda _: None)

    assert estado == "reemplazado"
    assert borrados == 0
    assert dst.read_bytes() == b"nuevo contenido"


def test_borrar_copiados_no_borra_nada_fuera_del_destino(tmp_path):
    destino = tmp_path / "destino"
    destino.mkdir()
    fuera = tmp_path / "fuera.MP4"
    fuera.write_bytes(b"no se borra")
    resultados = [(tmp_path / "origen", fuera, "bruto", "copiado")]

    avisos = []
    borrados, errores = nucleo.borrar_copiados(resultados, destino, avisos.append)

    assert borrados == 0
    assert fuera.is_file()
    assert len(errores) == 1 and str(fuera) in errores[0]
    assert avisos == errores


# -------------------- Criterio 5: resumen y registro ---------------------- #

def test_resumen_final_filas_y_ok(tmp_path):
    src = tmp_path / "C0001.MP4"
    src.write_bytes(b"\0" * 1_500_000)
    dst = tmp_path / "destino" / "C0001.MP4"
    resultados = [(src, dst, "bruto", "copiado")]
    destino = tmp_path / "destino"

    resumen = nucleo.resumen_final(resultados, [], 1.5, destino)

    assert resumen["ok"] is True
    assert resumen["filas"] == [
        ["Brutos", "1 clips"],
        ["Proxies", f"0 → carpeta {nucleo.CARPETA_PROXIES}{os.sep}"],
        ["Volumen", "2 MB"],
        ["Tiempo", "00:00:01"],
        ["Velocidad media", "1 MB/s"],
        ["Destino", str(destino)],
    ]

    resumen2 = nucleo.resumen_final(
        resultados + [(src, dst, "xml", "omitido")], ["C0001.MP4: fallo"],
        1.5, destino)

    assert resumen2["ok"] is False
    assert ["Metadatos", f"1 XML → carpeta {nucleo.CARPETA_XML}{os.sep}"] in resumen2["filas"]
    assert ["Ya existían", "1 (omitidos, tamaño idéntico)"] in resumen2["filas"]
    assert ["Destino", str(destino)] in resumen2["filas"]


def test_guardar_registro_escribe_el_fichero(tmp_path):
    src = tmp_path / "C0001.MP4"
    src.write_bytes(b"\0" * 1_500_000)
    destino = tmp_path / "destino"
    destino.mkdir()
    dst = destino / "C0001.MP4"
    resultados = [(src, dst, "bruto", "copiado")]

    log = nucleo.guardar_registro(resultados, ["C0002.MP4: fallo"], 1.5, destino)

    assert log.parent == destino
    assert log.name.startswith("volcado_") and log.suffix == ".txt"
    texto = log.read_text(encoding="utf-8")
    assert texto.startswith("VolcadoSony — ")
    assert f"Destino: {destino}" in texto
    assert "Total: 2 MB en 2 s" in texto
    assert f"[bruto] copiado  {src}  ->  {dst}" in texto
    assert "[ERROR] C0002.MP4: fallo" in texto


def test_guardar_registro_sin_destino_lanza_oserror(tmp_path):
    src = tmp_path / "C0001.MP4"
    src.write_bytes(b"\0" * 10)
    destino = tmp_path / "no_existe"

    with pytest.raises(OSError):
        nucleo.guardar_registro([(src, destino / src.name, "bruto", "copiado")],
                                [], 1.0, destino)


# --------------------------- Espacio en disco ----------------------------- #

def test_espacio_necesario_suma_brutos_y_proxies(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 1000, mtime=ts(2024, 11, 5))
    crear_proxy(origen, "C0001S03.MP4", 100)
    crear_bruto(origen, "C0002.MP4", 2000, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)

    assert nucleo.espacio_necesario(clips) == 3100


def test_comprobar_espacio_devuelve_libres_y_propaga_oserror(tmp_path, monkeypatch):
    libre = nucleo.comprobar_espacio(tmp_path, 1000)
    assert isinstance(libre, int) and libre > 0

    def falla(_):
        raise OSError("unidad no disponible")

    monkeypatch.setattr(nucleo.shutil, "disk_usage", falla)
    with pytest.raises(OSError):
        nucleo.comprobar_espacio(tmp_path, 1000)


def test_hay_espacio_aplica_el_margen():
    assert nucleo.hay_espacio(1021, 1000) is True
    assert nucleo.hay_espacio(1019, 1000) is False


# ------------------------- Criterio 6: ruta_unidad ------------------------- #

@pytest.mark.skipif(os.name != "nt", reason="solo Windows")
def test_ruta_unidad_normaliza_la_letra():
    assert str(nucleo.ruta_unidad("e")) == "E:\\"
    assert str(nucleo.ruta_unidad("E:")) == "E:\\"
    assert str(nucleo.ruta_unidad("E:\\")) == "E:\\"


def test_ruta_unidad_respeta_una_ruta_completa():
    assert nucleo.ruta_unidad("tarjeta") == Path("tarjeta")


# ----------------------- Criterio 7: miniaturas ---------------------------- #

def crear_miniatura(origen, nombre, contenido=b"\xff\xd8\xff\xe0"):
    carpeta = origen / "PRIVATE" / "M4ROOT" / "THMBNL"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_bytes(contenido)
    return ruta


def test_miniatura_lee_el_jpg_de_thmbnl(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 10, mtime=ts(2024, 11, 5))
    jpg = crear_miniatura(origen, "c0001t01.jpg", b"jpeg-falso")
    clips, _ = nucleo.escanear(origen, lambda _: None)

    avisos = []
    datos = nucleo.miniatura(clips[0], avisos.append)

    assert datos == jpg.read_bytes()
    assert avisos == []


def test_miniatura_sin_thmbnl_y_sin_ffmpeg_da_none(tmp_path, monkeypatch):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 10, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)
    monkeypatch.setattr(nucleo.shutil, "which", lambda _: None)

    avisos = []
    assert nucleo.miniatura(clips[0], avisos.append) is None
    assert avisos == []


def test_miniatura_sin_thmbnl_extrae_un_fotograma_con_ffmpeg(tmp_path, monkeypatch):
    origen = tarjeta_falsa(tmp_path)
    bruto = crear_bruto(origen, "C0001.MP4", 10, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)
    monkeypatch.setattr(nucleo.shutil, "which", lambda _: "ffmpeg")

    class Proceso:
        returncode = 0
        stdout = b"fotograma"
        stderr = b""

    llamadas = []

    def run(argumentos, **opciones):
        llamadas.append((argumentos, opciones))
        return Proceso()

    monkeypatch.setattr(nucleo.subprocess, "run", run)

    avisos = []
    assert nucleo.miniatura(clips[0], avisos.append) == b"fotograma"
    assert avisos == []
    argumentos, opciones = llamadas[0]
    assert argumentos[:5] == ["ffmpeg", "-v", "error", "-ss", "0"]
    assert str(bruto) in argumentos
    assert opciones["timeout"] == nucleo.TIMEOUT_FFMPEG_S


def test_miniatura_con_ffmpeg_que_falla_da_none_y_avisa(tmp_path, monkeypatch):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 10, mtime=ts(2024, 11, 5))
    clips, _ = nucleo.escanear(origen, lambda _: None)
    monkeypatch.setattr(nucleo.shutil, "which", lambda _: "ffmpeg")

    class Proceso:
        returncode = 1
        stdout = b""
        stderr = b"bruto ilegible"

    monkeypatch.setattr(nucleo.subprocess, "run", lambda *a, **k: Proceso())

    avisos = []
    assert nucleo.miniatura(clips[0], avisos.append) is None
    assert len(avisos) == 1
    assert "C0001.MP4" in avisos[0]
    assert "bruto ilegible" in avisos[0]


# --------------------------- Resto de interfaz ---------------------------- #

def test_es_tarjeta_reconoce_la_estructura(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    assert nucleo.es_tarjeta(origen) is True
    assert nucleo.es_tarjeta(tmp_path) is False


def test_detectar_tarjetas_no_falla(tmp_path, monkeypatch):
    buena = tarjeta_falsa(tmp_path)
    vacia = tmp_path / "vacia"
    vacia.mkdir()

    monkeypatch.setattr(nucleo.os, "name", "posix")
    monkeypatch.setattr(nucleo.sys, "platform", "darwin")

    def listar_falso(carpeta, avisar):
        if carpeta == Path("/Volumes"):
            return [buena, vacia]
        return []

    monkeypatch.setattr(nucleo, "_listar", listar_falso)

    encontradas = nucleo.detectar_tarjetas(lambda _: None)

    assert encontradas == [buena]


def test_escritorio_avisa_y_usa_el_respaldo_si_falla(tmp_path, monkeypatch):
    def falla():
        raise OSError("sin acceso")

    monkeypatch.setattr(nucleo.os, "name", "nt")
    monkeypatch.setattr(nucleo, "_escritorio_windows", falla)

    avisos = []
    ruta = nucleo.escritorio(avisos.append)

    assert ruta == Path.home() / "Desktop"
    assert avisos == [f"No se pudo obtener la carpeta Escritorio de Windows "
                      f"(sin acceso); se usa {ruta}."]


def test_escritorio_devuelve_una_ruta():
    assert isinstance(nucleo.escritorio(lambda _: None), Path)


def test_helpers_de_texto():
    assert nucleo.gb(999_000_000) == "999 MB"
    assert nucleo.gb(1_500_000_000) == "1.5 GB"
    assert nucleo.plural(1, "clip") == "1 clip"
    assert nucleo.plural(2, "clip") == "2 clips"
    assert nucleo.fecha_bonita(date(2024, 11, 5)) == "martes 5 de noviembre de 2024"
    assert nucleo.sanear_nombre(' a/b:c*? ') == "a_b_c__"
    assert nucleo.nombre_proxy_destino(Path("C0001S03.MP4")) == "C0001_Proxy.MP4"


def test_resumen_tarjeta_textos(tmp_path):
    origen = tarjeta_falsa(tmp_path)
    crear_bruto(origen, "C0001.MP4", 1000, mtime=ts(2024, 11, 5))
    crear_proxy(origen, "C0001S03.MP4", 100)
    crear_bruto(origen, "C0002.MP4", 2000, mtime=ts(2024, 11, 6))
    crear_proxy(origen, "C0009S03.MP4", 300)
    clips, huerfanos = nucleo.escanear(origen, lambda _: None)

    resumen = nucleo.resumen_tarjeta(clips, huerfanos, origen)

    assert resumen["tarjeta"] == str(origen)
    assert resumen["brutos"] == "2 clips · 0 MB"
    assert resumen["proxies"] == "1 de 2 clips tienen proxy"
    assert resumen["huerfanos"] == "1 proxy sin bruto asociado (no se copiará)"
    assert resumen["jornadas"] == ("2  (martes 5 de noviembre de 2024 → "
                                   "miércoles 6 de noviembre de 2024)")
