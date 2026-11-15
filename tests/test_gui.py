# -*- coding: utf-8 -*-
"""Pruebas de `volcadosony.gui`: `Api` y `Emisor` con ventana falsa, sin red ni ventana real."""

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from volcadosony import gui, nucleo


# ------------------------------- Utilidades ------------------------------- #

class VentanaFalsa:
    """Ventana mínima para pruebas: guarda el JSON de cada `evaluate_js`."""

    def __init__(self):
        self._lock = threading.Lock()
        self.llamadas = []
        self.cerrada = False

    def evaluate_js(self, js):
        with self._lock:
            self.llamadas.append(js)

    def destroy(self):
        self.cerrada = True

    def eventos(self):
        with self._lock:
            llamadas = list(self.llamadas)
        eventos = []
        for js in llamadas:
            assert js.startswith("recibir(") and js.endswith(")")
            eventos.extend(json.loads(js[len("recibir("):-1]))
        return eventos


def esperar_evento(ventana, tipo, desde=0, limite=5.0):
    """Espera a que la ventana falsa reciba un evento de `tipo` a partir de `desde`."""
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        for evento in ventana.eventos()[desde:]:
            if evento.get("type") == tipo:
                return evento
        time.sleep(0.01)
    raise AssertionError(f"No llegó el evento {tipo!r}; recibidos: "
                         f"{[e.get('type') for e in ventana.eventos()]}")


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


def ts(anio, mes, dia, hora=10):
    return datetime(anio, mes, dia, hora, 0, 0).timestamp()


def api_de_prueba(tmp_path, ruta_argumento=None):
    ventana = VentanaFalsa()
    return gui.Api(ruta_argumento, ventana), ventana


# ----------------------- Criterio 1: iniciar y escanear -------------------- #

def test_iniciar_con_tarjeta_emite_escaneando_y_tarjeta(tmp_path):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 1000, mtime=ts(2024, 11, 5))
    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    try:
        api.iniciar()
        escaneando = esperar_evento(ventana, "escaneando")
        evento = esperar_evento(ventana, "tarjeta")
    finally:
        api._al_cerrar()

    assert escaneando["ruta"] == str(tarjeta)
    assert evento["ruta"] == str(tarjeta)
    assert evento["resumen"]["tarjeta"] == str(tarjeta)
    assert evento["resumen"]["brutos"] == "1 clips · 0 MB"
    assert [j["indice"] for j in evento["jornadas"]] == [1]
    assert evento["jornadas"][0]["titulo"] == "Lote 1/1"
    assert evento["vacia"] is False
    assert evento["escritorio"] == str(nucleo.escritorio(lambda _: None))


# ------------------- Criterio 2: ruta inválida y usar_tarjeta -------------- #

def test_iniciar_sin_tarjeta_y_usar_tarjeta(tmp_path):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 1000, mtime=ts(2024, 11, 5))
    api, ventana = api_de_prueba(tmp_path, str(tmp_path / "no_es_tarjeta"))
    try:
        api.iniciar()
        sin_tarjeta = esperar_evento(ventana, "sin_tarjeta")
        assert "no contiene PRIVATE" in sin_tarjeta["mensaje"]

        api.usar_tarjeta(str(tarjeta))
        evento = esperar_evento(ventana, "tarjeta")
    finally:
        api._al_cerrar()

    assert evento["ruta"] == str(tarjeta)


def test_usar_tarjeta_invalida_avisa_con_el_mensaje_de_la_v1(tmp_path):
    api, ventana = api_de_prueba(tmp_path)
    try:
        api.usar_tarjeta(str(tmp_path / "otra"))
        evento = esperar_evento(ventana, "sin_tarjeta")
    finally:
        api._al_cerrar()

    assert evento["mensaje"].endswith(
        "no contiene la estructura Sony (PRIVATE\\M4ROOT\\CLIP).")


# --------------------- Criterio 3: revisar_destino ------------------------ #

def test_revisar_destino_sanea_usa_escritorio_y_marca_existe(tmp_path):
    api, _ = api_de_prueba(tmp_path)
    try:
        nombre = f"gui_{uuid.uuid4().hex}:x"
        saneado = nucleo.sanear_nombre(nombre)
        assert saneado != nombre

        escritorio = api.revisar_destino(nombre, "")
        assert escritorio["destino"] == str(
            nucleo.escritorio(lambda _: None) / saneado)
        assert escritorio["existe"] is False
        assert escritorio["valido"] is True

        (tmp_path / "copia").mkdir()
        existente = api.revisar_destino("copia", str(tmp_path))
        assert existente == {
            "destino": str(tmp_path / "copia"),
            "existe": True,
            "valido": True,
        }

        vacio = api.revisar_destino("", str(tmp_path))
        assert vacio["valido"] is False
    finally:
        api._al_cerrar()


# -------------------------- Criterio 4: volcar ---------------------------- #

def test_volcar_solo_la_jornada_marcada_copia_sus_clips(tmp_path):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    crear_bruto(tarjeta, "C0002.MP4", 70, mtime=ts(2024, 11, 6))
    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    base = tmp_path / "base"
    try:
        api.iniciar()
        esperar_evento(ventana, "tarjeta")
        api.volcar("MiCopia", str(base), [2])
        fin = esperar_evento(ventana, "fin")
    finally:
        api._al_cerrar()

    destino = base / "MiCopia"
    assert fin["ok"] is True
    assert fin["errores"] == []
    assert fin["filas"]
    assert (destino / "C0002.MP4").is_file()
    assert not (destino / "C0001.MP4").exists()
    assert fin["registro"].startswith("Registro guardado en ")
    assert list(destino.glob("volcado_*.txt"))


# --------------------- Criterio 5: agrupación del emisor ------------------ #

def test_emisor_deja_el_ultimo_progreso_y_conserva_el_orden():
    ventana = VentanaFalsa()
    emisor = gui.Emisor(ventana)
    try:
        emisor.emitir({"type": "aviso", "texto": "uno"})
        emisor.emitir({"type": "progreso", "total_hecho": 1})
        emisor.emitir({"type": "progreso", "total_hecho": 2})
        emisor.emitir({"type": "progreso", "total_hecho": 3})
        emisor.emitir({"type": "fin", "ok": True})
        emisor.vaciar()
    finally:
        emisor.parar()

    assert ventana.eventos() == [
        {"type": "aviso", "texto": "uno"},
        {"type": "progreso", "total_hecho": 3},
        {"type": "fin", "ok": True},
    ]


# --------------------- Resto de la interfaz pública ----------------------- #

def test_preparar_comprueba_el_espacio_de_las_jornadas_marcadas(tmp_path, monkeypatch):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    crear_bruto(tarjeta, "C0002.MP4", 70, mtime=ts(2024, 11, 6))
    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    try:
        api.iniciar()
        esperar_evento(ventana, "tarjeta")

        monkeypatch.setattr(nucleo, "comprobar_espacio", lambda base, necesario: 1)
        sin_espacio = api.preparar("copia", str(tmp_path), [1, 2])
        assert sin_espacio["ok"] is False
        assert sin_espacio["mensaje"].startswith("Espacio insuficiente: se necesitan ")

        monkeypatch.setattr(nucleo, "comprobar_espacio", lambda base, necesario: 10**12)
        assert api.preparar("copia", str(tmp_path), [2]) == {"ok": True}
    finally:
        api._al_cerrar()


def test_preparar_avisa_si_no_puede_comprobar_el_espacio(tmp_path, monkeypatch):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    try:
        api.iniciar()
        esperar_evento(ventana, "tarjeta")

        def falla(base, necesario):
            raise OSError("unidad no disponible")

        monkeypatch.setattr(nucleo, "comprobar_espacio", falla)
        assert api.preparar("copia", str(tmp_path), [1]) == {"ok": True}
        aviso = esperar_evento(ventana, "aviso")
    finally:
        api._al_cerrar()

    assert "No se pudo comprobar el espacio libre" in aviso["texto"]
    assert "unidad no disponible" in aviso["texto"]


def test_examinar_devuelve_la_carpeta_elegida_o_vacio(tmp_path):
    api, _ = api_de_prueba(tmp_path)
    try:
        api._ventana.create_file_dialog = lambda clase, directory=None: (str(tmp_path),)
        assert api.examinar("") == str(tmp_path)

        api._ventana.create_file_dialog = lambda clase, directory=None: None
        assert api.examinar(str(tmp_path)) == ""
    finally:
        api._al_cerrar()


def test_volcar_una_sola_vez_por_sesion(tmp_path):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    base = tmp_path / "base"
    try:
        api.iniciar()
        esperar_evento(ventana, "tarjeta")
        api.volcar("Copia", str(base), [1])
        esperar_evento(ventana, "fin")
        desde = len(ventana.eventos())
        api.volcar("Otra", str(base), [1])
        error = esperar_evento(ventana, "error", desde=desde)
        assert "sesión" in error["texto"]
        assert [e for e in ventana.eventos()[desde:] if e["type"] == "fin"] == []
    finally:
        api._al_cerrar()

    assert (base / "Copia" / "C0001.MP4").is_file()
    assert not (base / "Otra").exists()


def test_volcar_rechaza_nombre_vacio_y_seleccion_vacia(tmp_path):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    try:
        api.iniciar()
        esperar_evento(ventana, "tarjeta")

        api.volcar("   ", str(tmp_path / "base"), [1])
        error_nombre = esperar_evento(ventana, "error")

        desde = len(ventana.eventos())
        api.volcar("Copia", str(tmp_path / "base"), [])
        error_seleccion = esperar_evento(ventana, "error", desde=desde)
    finally:
        api._al_cerrar()

    assert "nombre" in error_nombre["texto"].lower()
    assert "jornada" in error_seleccion["texto"].lower()


def test_progreso_incluye_velocidad_y_eta(tmp_path):
    api, ventana = api_de_prueba(tmp_path)
    progreso = nucleo.Progreso(
        fichero="C0001.MP4", tipo="bruto",
        fichero_hecho=500, fichero_total=1000,
        lote="LOTE 1/1 · 05/11", lote_hecho=500, lote_total=1000,
        total_hecho=500, total_total=1000,
        visibles_hechos=0, visibles_total=1, segundos=2.0)
    try:
        api._progreso(progreso)
        evento = esperar_evento(ventana, "progreso")
    finally:
        api._al_cerrar()

    assert evento["fichero"] == "C0001.MP4"
    assert evento["velocidad"] == 250.0
    assert evento["eta"] == 2.0


def test_al_cerrar_cancela_el_volcado_y_emite_cancelado(tmp_path, monkeypatch):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    entrado = threading.Event()

    def volcar_bloqueado(seleccion, destino, avisar, al_progresar, al_error,
                         cancelar):
        entrado.set()
        cancelar.wait(5)
        raise nucleo.Cancelado("cancelado en la prueba")

    try:
        api.iniciar()
        esperar_evento(ventana, "tarjeta")
        monkeypatch.setattr(nucleo, "volcar", volcar_bloqueado)
        api.volcar("Copia", str(tmp_path / "base"), [1])
        assert entrado.wait(2)

        desde = len(ventana.eventos())
        api._al_cerrar()
        api._emisor.vaciar()
        cancelado = esperar_evento(ventana, "cancelado", desde=desde, limite=1)
    finally:
        api._al_cerrar()

    assert cancelado["type"] == "cancelado"
    assert not api._hilo_volcado.is_alive()
