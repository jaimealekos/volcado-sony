# -*- coding: utf-8 -*-
"""Pruebas de `volcadosony.gui`: `Api` y `Emisor` con ventana falsa, sin red ni ventana real."""

import base64
import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from volcadosony import gui, nucleo


@pytest.fixture(autouse=True)
def sin_ffmpeg(monkeypatch):
    """Las pruebas no ejecutan ffmpeg real: sin THMBNL no hay miniatura."""
    monkeypatch.setattr(nucleo.shutil, "which", lambda _: None)


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


def esperar_miniaturas(ventana, cantidad, limite=5.0):
    """Espera a que lleguen al menos `cantidad` eventos `miniatura`."""
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        miniaturas = [e for e in ventana.eventos()
                      if e.get("type") == "miniatura"]
        if len(miniaturas) >= cantidad:
            return miniaturas
        time.sleep(0.01)
    raise AssertionError(f"No llegaron {cantidad} miniaturas; recibidos: "
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


def crear_miniatura(origen, nombre, contenido):
    carpeta = origen / "PRIVATE" / "M4ROOT" / "THMBNL"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_bytes(contenido)
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


# ------------------- Criterio 8: pausar, reanudar y detener --------------- #

class CopiaLenta:
    """Copia real que, tras el primer fichero, espera a que la prueba la suelte."""

    def __init__(self, monkeypatch):
        self._real = nucleo.copiar_archivo
        self.copiado_uno = threading.Event()
        self.continuar = threading.Event()
        monkeypatch.setattr(nucleo, "copiar_archivo", self)

    def __call__(self, src, dst, avisar, al_bloque, cancelar, pausa):
        estado = self._real(src, dst, avisar, al_bloque, cancelar, pausa)
        if estado == "copiado" and not self.copiado_uno.is_set():
            self.copiado_uno.set()
            self.continuar.wait(5)
        return estado


def api_con_dos_brutos(tmp_path):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 60, mtime=ts(2024, 11, 5))
    crear_bruto(tarjeta, "C0002.MP4", 70, mtime=ts(2024, 11, 5))
    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    api.iniciar()
    esperar_evento(ventana, "tarjeta")
    return api, ventana


def test_detener_conservar_emite_detenido_y_deja_lo_copiado(tmp_path, monkeypatch):
    api, ventana = api_con_dos_brutos(tmp_path)
    base = tmp_path / "base"
    copia = CopiaLenta(monkeypatch)
    try:
        api.volcar("Copia", str(base), [1])
        assert copia.copiado_uno.wait(2)
        api.pausar()
        api.detener("conservar")
        copia.continuar.set()
        detenido = esperar_evento(ventana, "detenido")
    finally:
        copia.continuar.set()
        api._al_cerrar()

    destino = base / "Copia"
    assert detenido["modo"] == "conservar"
    assert detenido["copiados"] == 1
    assert detenido["errores"] == []
    assert detenido["registro"].startswith("Registro guardado en ")
    assert (destino / "C0001.MP4").is_file()
    assert not (destino / "C0002.MP4").exists()
    assert list(destino.glob("volcado_*.txt"))


def test_detener_borrar_emite_detenido_y_no_deja_lo_copiado(tmp_path, monkeypatch):
    api, ventana = api_con_dos_brutos(tmp_path)
    base = tmp_path / "base"
    copia = CopiaLenta(monkeypatch)
    try:
        api.volcar("Copia", str(base), [1])
        assert copia.copiado_uno.wait(2)
        api.pausar()
        api.detener("borrar")
        copia.continuar.set()
        detenido = esperar_evento(ventana, "detenido")
    finally:
        copia.continuar.set()
        api._al_cerrar()

    destino = base / "Copia"
    assert detenido["modo"] == "borrar"
    assert detenido["borrados"] == 1
    assert detenido["errores"] == []
    assert detenido["destino"] == str(destino)
    assert not destino.exists()
    assert not list(base.rglob("*.part"))


def test_detener_sin_volcado_y_modo_invalido_dan_error(tmp_path):
    api, ventana = api_de_prueba(tmp_path)
    try:
        api.detener("conservar")
        error_sin_volcado = esperar_evento(ventana, "error")

        desde = len(ventana.eventos())
        api.detener("otro")
        error_modo = esperar_evento(ventana, "error", desde=desde)
    finally:
        api._al_cerrar()

    assert "volcado" in error_sin_volcado["texto"].lower()
    assert "modo" in error_modo["texto"].lower()


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


# ----------------------- Criterio 6: miniaturas ---------------------------- #

def test_iniciar_emite_miniaturas_del_primero_y_el_ultimo(tmp_path):
    tarjeta = tarjeta_falsa(tmp_path)
    crear_bruto(tarjeta, "C0001.MP4", 10, mtime=ts(2024, 11, 5))
    crear_bruto(tarjeta, "C0002.MP4", 10, mtime=ts(2024, 11, 5))
    crear_bruto(tarjeta, "C0003.MP4", 10, mtime=ts(2024, 11, 6))
    primero = crear_miniatura(tarjeta, "C0001T01.JPG", b"primero")
    ultimo = crear_miniatura(tarjeta, "C0002T01.JPG", b"ultimo")
    unico = crear_miniatura(tarjeta, "C0003T01.JPG", b"unico")

    api, ventana = api_de_prueba(tmp_path, str(tarjeta))
    try:
        api.iniciar()
        esperar_evento(ventana, "tarjeta")
        esperar_miniaturas(ventana, 3)
        time.sleep(0.3)
        miniaturas = [e for e in ventana.eventos()
                      if e.get("type") == "miniatura"]
    finally:
        api._al_cerrar()

    assert [(m["indice"], m["cual"], m["nombre"]) for m in miniaturas] == [
        (1, "primero", "C0001.MP4"),
        (1, "ultimo", "C0002.MP4"),
        (2, "primero", "C0003.MP4"),
    ]
    prefijo = "data:image/jpeg;base64,"
    assert all(m["datos"].startswith(prefijo) for m in miniaturas)
    assert [base64.b64decode(m["datos"][len(prefijo):]) for m in miniaturas] == [
        primero.read_bytes(), ultimo.read_bytes(), unico.read_bytes()]


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
                         cancelar, pausa):
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


# ------------------------- Alto de ventana al volcar ----------------------- #

class VentanaAjustable(VentanaFalsa):
    def __init__(self):
        super().__init__()
        self.crecidas = []

    def crecer(self, falta, alto_maximo, cima):
        self.crecidas.append((falta, alto_maximo, cima))


class VentanaReal:
    """Imita lo que usa `_VentanaDiferida.crecer` de una ventana pywebview."""

    def __init__(self, alto, y):
        self.width, self.height, self.x, self.y = 1000, alto, 100, y

    def resize(self, ancho, alto):
        self.width, self.height = ancho, alto

    def move(self, x, y):
        self.x, self.y = x, y


def test_ajustar_ventana_pasa_la_peticion_a_la_ventana():
    ventana = VentanaAjustable()
    api = gui.Api(None, ventana)
    api.ajustar_ventana(254.0, 1392, 0)
    assert ventana.crecidas == [(254, 1392, 0)]


def test_ajustar_ventana_rechaza_valores_no_validos():
    ventana = VentanaAjustable()
    api = gui.Api(None, ventana)
    api.ajustar_ventana(0, 1392, 0)
    api.ajustar_ventana(100, 200, 0)
    assert ventana.crecidas == []


def test_crecer_suma_lo_que_falta_si_cabe_en_pantalla():
    diferida = gui._VentanaDiferida()
    diferida.real = VentanaReal(alto=820, y=50)
    diferida.crecer(256, 1392, 0)
    assert (diferida.real.height, diferida.real.y) == (1076, 50)


def test_crecer_no_pasa_de_la_pantalla_y_sube_la_ventana():
    diferida = gui._VentanaDiferida()
    diferida.real = VentanaReal(alto=820, y=400)
    diferida.crecer(900, 1392, 0)
    assert (diferida.real.height, diferida.real.y) == (1392, 0)


def test_crecer_sube_lo_justo_para_no_salirse_por_abajo():
    diferida = gui._VentanaDiferida()
    diferida.real = VentanaReal(alto=820, y=500)
    diferida.crecer(256, 1392, 0)
    assert (diferida.real.height, diferida.real.y) == (1076, 316)
