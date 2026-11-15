# -*- coding: utf-8 -*-
r"""
Ventana de VolcadoSony: expone `Api` a la vista, lanza búsqueda, escaneo y
volcado en hilos, y entrega los eventos a la vista desde un único `Emisor`.

Sin lógica de negocio: tarjetas, clips, jornadas, espacio y copia los decide
`nucleo`. Aquí solo vive lo que necesita la ventana: el hilo de entrega, los
hilos de trabajo, el diálogo nativo de carpeta y la cancelación al cerrar.
"""

import base64
import dataclasses
import itertools
import json
import logging
import os
import sys
import threading
from pathlib import Path

import webview

from . import nucleo

log = logging.getLogger(__name__)

INTERVALO_UI_MS = 100          # cadencia máxima de entrega de eventos a la vista
ESPERA_CIERRE_S = 5.0          # espera máxima al hilo de volcado al cerrar
VENTANA_OCULTA_ENV = "VOLCADO_VENTANA_OCULTA"
TITULO = "VolcadoSony"
ANCHO = 1000
ALTO = 820
TAMANO_MINIMO = (820, 600)
FONDO = "#0C0C10"              # --bg de la vista: sin destello blanco al abrir
VISTA = "index.html"


# ------------------------------- Utilería --------------------------------- #

def ruta_vista() -> Path:
    """`ui/index.html`: dentro del exe en `sys._MEIPASS`, junto al módulo si no."""
    congelado = getattr(sys, "_MEIPASS", None)
    if congelado:
        return Path(congelado) / "volcadosony" / "ui" / VISTA
    return Path(__file__).resolve().parent / "ui" / VISTA


class _VentanaDiferida:
    """Ventana real todavía sin crear: `js_api` obliga a tener `Api` antes."""

    def __init__(self) -> None:
        self.real = None

    def evaluate_js(self, js: str) -> object:
        return self.real.evaluate_js(js) if self.real is not None else None

    def create_file_dialog(self, *args: object, **kwargs: object) -> object:
        if self.real is None:
            return None
        return self.real.create_file_dialog(*args, **kwargs)

    def destroy(self) -> None:
        if self.real is not None:
            self.real.destroy()


# ------------------------- Entrega de eventos a la vista ------------------ #

class Emisor:
    """Entrega lo pendiente desde un solo hilo, como mucho cada `intervalo`.

    De varios `progreso` seguidos solo queda el último, en el lugar del primero:
    nunca adelanta a lo que le precedía.
    """

    def __init__(self, ventana: object,
                 intervalo: float = INTERVALO_UI_MS / 1000) -> None:
        self._ventana = ventana
        self._intervalo = intervalo
        self._lock = threading.Lock()
        self._pendientes: dict[object, dict] = {}
        self._serie = itertools.count()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None

    def emitir(self, evento: dict) -> None:
        """Encola `evento`; se puede llamar desde cualquier hilo y no bloquea."""
        clave = "progreso" if evento.get("type") == "progreso" else next(self._serie)
        with self._lock:
            self._pendientes[clave] = evento

    def arrancar(self) -> None:
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._run, daemon=True)
            self._hilo.start()

    def parar(self) -> None:
        self._parar.set()
        if self._hilo is not None and self._hilo is not threading.current_thread():
            self._hilo.join(1.0)

    def vaciar(self) -> None:
        """Entrega ahora lo pendiente, en una sola llamada a la vista."""
        with self._lock:
            lote = list(self._pendientes.values())
            self._pendientes = {}
        if lote:
            self._ventana.evaluate_js(
                "recibir(" + json.dumps(lote, ensure_ascii=False) + ")")

    def _run(self) -> None:
        while not self._parar.wait(self._intervalo):
            try:
                self.vaciar()
            except Exception:
                log.exception("No se pudieron entregar los eventos a la vista")


# ----------------------------------- Api ---------------------------------- #

class Api:
    """Métodos que llama la vista. Ninguno bloquea más de un instante."""

    def __init__(self, ruta_argumento: str | None, ventana: object) -> None:
        self._ruta_argumento = ruta_argumento
        self._ventana = ventana
        self._emisor = Emisor(ventana)
        self._emisor.arrancar()

        self._jornadas: list[nucleo.Jornada] = []
        self._escaneo = 0  # sube con cada escaneo; las miniaturas de uno viejo se descartan
        self._cancelar = threading.Event()
        self._pausa = threading.Event()
        self._modo_detener: str | None = None
        self._lock_volcado = threading.Lock()
        self._hilo_volcado: threading.Thread | None = None
        self._volcado_iniciado = False

    # ----------------------------- Eventos --------------------------------- #

    def _avisar(self, texto: str) -> None:
        self._emisor.emitir({"type": "aviso", "texto": texto})

    def _sin_tarjeta(self, mensaje: str) -> None:
        self._emisor.emitir({"type": "sin_tarjeta", "mensaje": mensaje})

    def _escanear_tarjeta(self, origen: Path) -> None:
        self._escaneo += 1
        escaneo = self._escaneo
        try:
            self._emisor.emitir({"type": "escaneando", "ruta": str(origen)})
            clips, huerfanos = nucleo.escanear(origen, self._avisar)
            jornadas = nucleo.agrupar_jornadas(clips)
            self._jornadas = jornadas
            self._emisor.emitir({
                "type": "tarjeta",
                "ruta": str(origen),
                "resumen": nucleo.resumen_tarjeta(clips, huerfanos, origen),
                "jornadas": [nucleo.describir_jornada(j, len(jornadas))
                             for j in jornadas],
                "escritorio": str(nucleo.escritorio(self._avisar)),
                "vacia": not clips,
            })
        except Exception as e:
            log.exception("Falló el escaneo de %s", origen)
            self._sin_tarjeta(f"No se pudo escanear la tarjeta {origen}: {e}")
            return
        try:
            for jornada in jornadas:
                if escaneo != self._escaneo:
                    return
                self._emitir_miniaturas(jornada)
        except Exception as e:
            log.exception("Fallaron las miniaturas de %s", origen)
            self._avisar(f"No se pudieron sacar las miniaturas de {origen}: {e}")

    def _emitir_miniaturas(self, jornada: nucleo.Jornada) -> None:
        """Emite la miniatura del primer clip y, si hay más, del último."""
        parejas = [("primero", jornada.clips[0])]
        if len(jornada.clips) > 1:
            parejas.append(("ultimo", jornada.clips[-1]))
        for cual, clip in parejas:
            datos = nucleo.miniatura(clip, self._avisar)
            datos_url = None
            if datos:
                datos_url = ("data:image/jpeg;base64,"
                             + base64.b64encode(datos).decode("ascii"))
            self._emisor.emitir({
                "type": "miniatura",
                "indice": jornada.indice,
                "cual": cual,
                "nombre": clip.ruta.name,
                "datos": datos_url,
            })

    def _detectar(self) -> None:
        try:
            tarjetas = nucleo.detectar_tarjetas(self._avisar)
            if not tarjetas:
                self._sin_tarjeta(
                    r"No se ha encontrado ninguna unidad con PRIVATE\M4ROOT\CLIP")
            elif len(tarjetas) == 1:
                self._escanear_tarjeta(tarjetas[0])
            else:
                self._emisor.emitir(
                    {"type": "tarjetas", "rutas": [str(t) for t in tarjetas]})
        except Exception as e:
            log.exception("Falló la búsqueda de tarjetas")
            self._sin_tarjeta(f"No se pudo buscar la tarjeta SD: {e}")

    def _buscar(self) -> None:
        try:
            if self._ruta_argumento:
                origen = Path(self._ruta_argumento)
                if nucleo.es_tarjeta(origen):
                    self._escanear_tarjeta(origen)
                else:
                    self._sin_tarjeta(
                        f"La ruta {origen} no contiene PRIVATE\\M4ROOT\\CLIP")
                return
            self._detectar()
        except Exception as e:
            log.exception("Falló la búsqueda inicial de la tarjeta")
            self._sin_tarjeta(f"No se pudo buscar la tarjeta SD: {e}")

    # ------------------------- Métodos de la vista ------------------------- #

    def iniciar(self) -> None:
        """Busca la tarjeta al abrir: la del argumento o la que haya conectada."""
        self._emisor.emitir({"type": "buscando"})
        threading.Thread(target=self._buscar, daemon=True).start()

    def usar_tarjeta(self, texto: str) -> None:
        origen = nucleo.ruta_unidad(texto)
        if nucleo.es_tarjeta(origen):
            threading.Thread(target=self._escanear_tarjeta, args=(origen,),
                             daemon=True).start()
        else:
            self._sin_tarjeta(
                f"{origen} no contiene la estructura Sony "
                r"(PRIVATE\M4ROOT\CLIP).")

    def buscar_de_nuevo(self) -> None:
        self._emisor.emitir({"type": "buscando"})
        threading.Thread(target=self._detectar, daemon=True).start()

    def examinar(self, ruta_actual: str) -> str:
        inicial = ruta_actual.strip() if ruta_actual else ""
        inicial = inicial or str(nucleo.escritorio(self._avisar))
        try:
            elegidas = self._ventana.create_file_dialog(
                webview.FOLDER_DIALOG, directory=inicial)
        except Exception as e:
            self._avisar(f"No se pudo abrir el selector de carpetas: {e}")
            return ""
        return str(elegidas[0]) if elegidas else ""

    def revisar_destino(self, nombre: str, ruta: str) -> dict:
        saneado = nucleo.sanear_nombre(nombre)
        base = Path(ruta) if ruta and ruta.strip() else nucleo.escritorio(self._avisar)
        destino = base / saneado
        return {
            "destino": str(destino),
            "existe": destino.exists(),
            "valido": bool(saneado),
        }

    def preparar(self, nombre: str, ruta: str, indices: list[int]) -> dict:
        """Comprueba el espacio de las jornadas marcadas antes de volcar."""
        base = Path(ruta) if ruta and ruta.strip() else nucleo.escritorio(self._avisar)
        necesario = nucleo.espacio_necesario(self._seleccion(indices))
        try:
            libre = nucleo.comprobar_espacio(base, necesario)
        except OSError as e:
            self._avisar(
                f"No se pudo comprobar el espacio libre en "
                f"{base.resolve().anchor}: se continúa sin comprobarlo ({e})")
            return {"ok": True}
        if not nucleo.hay_espacio(libre, necesario):
            return {
                "ok": False,
                "mensaje": (
                    f"Espacio insuficiente: se necesitan {nucleo.gb(necesario)} "
                    f"y solo hay {nucleo.gb(libre)} libres en "
                    f"{base.resolve().anchor}"),
            }
        return {"ok": True}

    def volcar(self, nombre: str, ruta: str, indices: list[int]) -> None:
        """Copia las jornadas marcadas en un hilo; una sola vez por sesión."""
        saneado = nucleo.sanear_nombre(nombre)
        if not saneado:
            self._error("El nombre de la carpeta Destino no puede estar vacío.")
            return
        seleccion = self._seleccion(indices)
        if not seleccion:
            self._error("No hay ninguna jornada seleccionada para volcar.")
            return
        with self._lock_volcado:
            if self._volcado_iniciado:
                self._error("El volcado ya se ha realizado en esta sesión.")
                return
            self._volcado_iniciado = True
        base = Path(ruta) if ruta and ruta.strip() else nucleo.escritorio(self._avisar)
        destino = base / saneado
        self._cancelar.clear()
        self._pausa.clear()
        self._modo_detener = None
        self._hilo_volcado = threading.Thread(
            target=self._copiar, args=(seleccion, destino), daemon=True)
        self._hilo_volcado.start()

    def pausar(self) -> None:
        """Pone en pausa el volcado en curso."""
        if not self._volcado_activo():
            self._error("No hay ningún volcado en curso para pausar.")
            return
        self._pausa.set()

    def reanudar(self) -> None:
        """Quita la pausa del volcado en curso."""
        if not self._volcado_activo():
            self._error("No hay ningún volcado en curso que reanudar.")
            return
        self._pausa.clear()

    def detener(self, modo: str) -> None:
        """Detiene el volcado: `modo` es "conservar" o "borrar"."""
        if modo not in ("conservar", "borrar"):
            self._error(f"Modo de detención no válido: {modo!r}. "
                        "Usa «conservar» o «borrar».")
            return
        if not self._volcado_activo():
            self._error("No hay ningún volcado en curso que detener.")
            return
        self._modo_detener = modo
        self._cancelar.set()
        self._pausa.clear()

    def _volcado_activo(self) -> bool:
        return (self._hilo_volcado is not None
                and self._hilo_volcado.is_alive())

    def salir(self) -> None:
        self._ventana.destroy()

    # ----------------------------- Volcado --------------------------------- #

    def _seleccion(self, indices: list[int]) -> list[nucleo.Clip]:
        marcadas = {int(i) for i in indices}
        return [c for j in self._jornadas if j.indice in marcadas for c in j.clips]

    def _progreso(self, progreso: nucleo.Progreso) -> None:
        velocidad = (progreso.total_hecho / progreso.segundos
                     if progreso.segundos > 0 else 0.0)
        datos = dataclasses.asdict(progreso)
        datos.update({
            "type": "progreso",
            "velocidad": velocidad,
            "eta": ((progreso.total_total - progreso.total_hecho) / velocidad
                    if velocidad > 0 else None),
        })
        self._emisor.emitir(datos)

    def _error(self, texto: str) -> None:
        self._emisor.emitir({"type": "error", "texto": texto})

    def _copiar(self, seleccion: list[nucleo.Clip], destino: Path) -> None:
        try:
            try:
                resultados, errores, segundos = nucleo.volcar(
                    seleccion, destino, self._avisar, self._progreso,
                    self._error, self._cancelar, self._pausa)
            except nucleo.Cancelado as e:
                self._detener_volcado(e, destino)
                return

            self._modo_detener = None
            self._pausa.clear()
            resumen = nucleo.resumen_final(resultados, errores, segundos, destino)
            self._emisor.emitir({
                "type": "fin",
                "ok": resumen["ok"],
                "filas": resumen["filas"],
                "errores": errores,
                "registro": self._guardar_registro(
                    resultados, errores, segundos, destino),
            })
        except Exception as e:
            log.exception("Falló el volcado en %s", destino)
            texto = f"No se pudo volcar en {destino}: {e}"
            self._error(texto)
            self._emisor.emitir({"type": "fin", "ok": False, "filas": [],
                                 "errores": [texto], "registro": texto})

    def _detener_volcado(self, e: nucleo.Cancelado, destino: Path) -> None:
        """Convierte la cancelación en `cancelado` o `detenido` según el modo."""
        modo = self._modo_detener
        self._modo_detener = None
        self._pausa.clear()
        if modo is None:
            self._emisor.emitir({"type": "cancelado"})
            return
        if modo == "conservar":
            copiados = sum(1 for r in e.resultados
                           if r[3] in ("copiado", "reemplazado"))
            self._emisor.emitir({
                "type": "detenido",
                "modo": "conservar",
                "copiados": copiados,
                "registro": self._guardar_registro(
                    e.resultados, e.errores, e.segundos, destino),
                "errores": list(e.errores),
            })
            return
        borrados, errores = nucleo.borrar_copiados(
            e.resultados, destino, self._avisar)
        self._emisor.emitir({
            "type": "detenido",
            "modo": "borrar",
            "borrados": borrados,
            "errores": list(e.errores) + errores,
            "destino": str(destino),
        })

    def _guardar_registro(self, resultados: list, errores: list[str],
                          segundos: float, destino: Path) -> str:
        try:
            log_volcado = nucleo.guardar_registro(
                resultados, errores, segundos, destino)
        except OSError as e:
            texto = f"No se pudo guardar el registro en {destino}: {e}."
            if not errores:
                texto += " Los ficheros sí se copiaron."
            return texto
        return f"Registro guardado en {log_volcado}"

    # ------------------------------ Cierre --------------------------------- #

    def _al_cerrar(self) -> None:
        """Al cerrar la ventana: cancela el volcado, lo espera y para el emisor."""
        self._pausa.clear()
        self._cancelar.set()
        if (self._hilo_volcado is not None
                and self._hilo_volcado is not threading.current_thread()):
            self._hilo_volcado.join(ESPERA_CIERRE_S)
        self._emisor.parar()


# ---------------------------------- run ----------------------------------- #

def run(ruta_argumento: str | None) -> int:
    """Abre la ventana, arranca pywebview y devuelve 0 al cerrarla."""
    ventana = _VentanaDiferida()
    api = Api(ruta_argumento, ventana)
    opciones = {"hidden": True} if os.environ.get(VENTANA_OCULTA_ENV) else {}
    real = webview.create_window(
        TITULO,
        url=str(ruta_vista()),
        js_api=api,
        width=ANCHO,
        height=ALTO,
        min_size=TAMANO_MINIMO,
        background_color=FONDO,
        **opciones,
    )
    ventana.real = real
    real.events.closing += api._al_cerrar
    webview.start()
    return 0
