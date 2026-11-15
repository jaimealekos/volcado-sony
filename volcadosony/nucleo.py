# -*- coding: utf-8 -*-
r"""
Núcleo de VolcadoSony: detección de tarjetas, escaneo de clips, agrupación por
jornadas, comprobación de espacio, copia con progreso y registro del volcado.

Sin interfaz: los avisos, el progreso y los errores salen por funciones de
retorno. Estructura de la tarjeta:
    unidad:\PRIVATE\M4ROOT\CLIP   -> brutos de vídeo (*.MP4) + sidecars XML (*M01.XML)
    unidad:\PRIVATE\M4ROOT\SUB    -> proxies (*S03.MP4)  [también se buscan en CLIP]
"""

import ctypes
import os
import re
import shutil
import string
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

# ----------------------------- Configuracion ------------------------------ #

VERSION = "2.0.0"

CHUNK = 8 * 1024 * 1024          # tamano de bloque de copia (8 MB)
COPIAR_XML = True                # copiar tambien los sidecars XML de los brutos
CARPETA_XML = "_xml"             # nombre de la subcarpeta de sidecars XML
CARPETA_PROXIES = "Proxies"      # nombre de la subcarpeta de proxies
SUFIJO_PROXY_ORIGEN = "S03"      # sufijo Sony del proxy
SUFIJO_PROXY_DESTINO = "_Proxy"  # sufijo con el que se renombra al copiar
MARGEN_ESPACIO = 1.02            # margen de seguridad al comprobar el espacio libre
CARPETA_MINIATURAS = "THMBNL"    # subcarpeta de miniaturas de la tarjeta
SUFIJO_MINIATURA = "T01.JPG"     # sufijo Sony de la miniatura del bruto
TIMEOUT_FFMPEG_S = 20            # espera máxima al extraer un fotograma
ESPERA_PAUSA_S = 0.1             # tramo de espera mientras el volcado está en pausa

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

RE_PROXY = re.compile(r"^(?P<stem>.+)" + SUFIJO_PROXY_ORIGEN + r"$", re.IGNORECASE)


# ------------------------------- Utilidades ------------------------------- #

def escritorio(avisar: Callable[[str], None]) -> Path:
    """Ruta real del Escritorio (en Windows respeta redirecciones tipo OneDrive)."""
    respaldo = Path.home() / "Desktop"
    if os.name != "nt":
        return respaldo
    try:
        return _escritorio_windows()
    except (OSError, AttributeError) as e:
        avisar(f"No se pudo obtener la carpeta Escritorio de Windows ({e}); "
               f"se usa {respaldo}.")
        return respaldo


def _escritorio_windows() -> Path:
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
    fid = GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
               (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
    ppath = ctypes.c_wchar_p()
    resultado = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(fid), 0, None, ctypes.byref(ppath))
    if resultado != 0:
        raise OSError(resultado, "SHGetKnownFolderPath falló")
    try:
        if not ppath.value:
            raise OSError("SHGetKnownFolderPath devolvió una ruta vacía")
        return Path(ppath.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ppath)


def gb(n_bytes: int) -> str:
    if n_bytes < 1e9:
        return f"{n_bytes / 1e6:.0f} MB"
    return f"{n_bytes / 1e9:.1f} GB"


def plural(n: int, palabra: str) -> str:
    return f"{n} {palabra}" + ("" if n == 1 else "s")


def fecha_bonita(d) -> str:
    return f"{DIAS_ES[d.weekday()]} {d.day} de {MESES_ES[d.month - 1]} de {d.year}"


def sanear_nombre(nombre: str) -> str:
    nombre = re.sub(r'[<>:"/\\|?*]', "_", nombre).strip().rstrip(".")
    return nombre


# --------------------------- Deteccion de la SD --------------------------- #

def es_tarjeta(ruta: Path) -> bool:
    """True si la ruta contiene PRIVATE\\M4ROOT\\CLIP."""
    return (ruta / "PRIVATE" / "M4ROOT" / "CLIP").is_dir()


def _listar(carpeta: Path, avisar: Callable[[str], None]) -> list[Path]:
    try:
        return sorted(carpeta.iterdir())
    except OSError as e:
        avisar(f"No se pudo listar {carpeta}: {e}")
        return []


def detectar_tarjetas(avisar: Callable[[str], None]) -> list[Path]:
    """Busca unidades que contengan PRIVATE\\M4ROOT\\CLIP."""
    if os.name == "nt":
        raices = [Path(f"{letra}:\\") for letra in string.ascii_uppercase]
    elif sys.platform == "darwin":
        raices = _listar(Path("/Volumes"), avisar)
    else:
        usuario = Path.home().name
        raices = (_listar(Path("/media") / usuario, avisar)
                  + _listar(Path("/run/media") / usuario, avisar))

    encontradas = []
    for raiz in raices:
        try:
            if es_tarjeta(raiz):
                encontradas.append(raiz)
        except OSError as e:
            avisar(f"No se pudo leer la unidad {raiz}: {e}")
    return encontradas


def ruta_unidad(texto: str) -> Path:
    """Texto escrito por el usuario (`E`, `E:`, `E:\\`, `/Volumes/SD`) a `Path`."""
    texto = texto.strip()
    if os.name == "nt" and re.fullmatch(r"[A-Za-z](?::|\\)?", texto):
        return Path(f"{texto[0].upper()}:\\")
    return Path(texto)


# ----------------------------- Escaneo de clips ---------------------------- #

class Clip:
    __slots__ = ("ruta", "tamano", "fecha", "fuente_fecha", "xml", "proxy")

    def __init__(self, ruta: Path, avisar: Callable[[str], None]):
        self.ruta = ruta
        self.tamano = ruta.stat().st_size
        self.xml: Path | None = None
        self.proxy: Path | None = None
        self.fecha, self.fuente_fecha = self._fecha(avisar)

    def _fecha(self, avisar: Callable[[str], None]):
        """Fecha de grabacion: primero el XML de la camara, si no, el sistema de archivos."""
        xml = buscar_insensible(self.ruta.parent, self.ruta.stem + "M01.XML", avisar)
        if xml:
            self.xml = xml
            try:
                for el in ET.parse(xml).iter():
                    if el.tag.rsplit("}", 1)[-1] == "CreationDate":
                        v = el.get("value")
                        if v:
                            v = v.replace("Z", "+00:00")
                            return datetime.fromisoformat(v).date(), "XML"
            except (ET.ParseError, ValueError, OSError) as e:
                avisar(f"XML ilegible ({xml.name}): {e}. "
                       "Se usa la fecha del sistema de archivos.")
            else:
                avisar(f"El XML {xml.name} no trae una fecha de grabación válida. "
                       "Se usa la fecha del sistema de archivos.")
        return datetime.fromtimestamp(self.ruta.stat().st_mtime).date(), "FS"


def buscar_insensible(carpeta: Path, nombre: str,
                      avisar: Callable[[str], None]) -> Path | None:
    objetivo = nombre.lower()
    try:
        for f in carpeta.iterdir():
            if f.name.lower() == objetivo:
                return f
    except OSError as e:
        avisar(f"No se pudo listar la carpeta {carpeta}: {e}")
    return None


def escanear(origen: Path,
             avisar: Callable[[str], None]) -> tuple[list[Clip], int]:
    """Devuelve (clips ordenados por nombre, nº de proxies huérfanos descartados)."""
    clip_dir = origen / "PRIVATE" / "M4ROOT" / "CLIP"
    sub_dir = origen / "PRIVATE" / "M4ROOT" / "SUB"

    brutos: dict[str, Clip] = {}
    proxies: dict[str, Path] = {}

    for carpeta in (clip_dir, sub_dir):
        if not carpeta.is_dir():
            continue
        for f in _listar(carpeta, avisar):
            if not f.is_file() or f.suffix.lower() != ".mp4":
                continue
            m = RE_PROXY.match(f.stem)
            if m:
                proxies.setdefault(m.group("stem").lower(), f)
            else:
                brutos.setdefault(f.stem.lower(), Clip(f, avisar))

    huerfanos = 0
    for stem, ruta_proxy in proxies.items():
        if stem in brutos:
            brutos[stem].proxy = ruta_proxy
        else:
            huerfanos += 1

    return sorted(brutos.values(), key=lambda c: c.ruta.name.lower()), huerfanos


def miniatura(clip: Clip, avisar: Callable[[str], None]) -> bytes | None:
    """Bytes JPEG de la miniatura del clip: la de la cámara o un fotograma.

    Primero busca el JPG de THMBNL de la tarjeta; si no está y hay ffmpeg,
    extrae un fotograma del bruto. Sin ninguna de las dos cosas devuelve
    `None` sin avisar.
    """
    carpeta = clip.ruta.parent.parent / CARPETA_MINIATURAS
    if carpeta.is_dir():
        nombre = clip.ruta.stem + SUFIJO_MINIATURA
        jpg = buscar_insensible(carpeta, nombre, avisar)
        if jpg:
            try:
                return jpg.read_bytes()
            except OSError as e:
                avisar(f"No se pudo leer la miniatura {jpg.name}: {e}")
                return None

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        proceso = subprocess.run(
            [ffmpeg, "-v", "error", "-ss", "0", "-i", str(clip.ruta),
             "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2pipe",
             "-vcodec", "mjpeg", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=TIMEOUT_FFMPEG_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        avisar(f"No se pudo generar la miniatura de {clip.ruta.name}: {e}")
        return None

    if proceso.returncode != 0:
        motivo = (proceso.stderr.decode("utf-8", "replace").strip()
                  or f"ffmpeg terminó con código {proceso.returncode}")
        avisar(f"No se pudo generar la miniatura de {clip.ruta.name}: {motivo}")
        return None
    if not proceso.stdout:
        avisar(f"No se pudo generar la miniatura de {clip.ruta.name}: "
               "ffmpeg no devolvió ningún fotograma")
        return None
    return proceso.stdout


# ------------------------------- Jornadas --------------------------------- #

@dataclass
class Jornada:
    indice: int            # 1..n, orden cronológico
    fecha: date
    clips: list[Clip]
    peso: int              # suma de tamaños de los brutos
    con_proxy: int


def agrupar_jornadas(clips: list[Clip]) -> list[Jornada]:
    """Agrupa los clips por día de grabación, en orden cronológico."""
    por_dia: dict[date, list[Clip]] = {}
    for c in clips:
        por_dia.setdefault(c.fecha, []).append(c)

    return [Jornada(indice=i,
                    fecha=dia,
                    clips=lote,
                    peso=sum(c.tamano for c in lote),
                    con_proxy=sum(1 for c in lote if c.proxy))
            for i, (dia, lote) in enumerate(sorted(por_dia.items()), 1)]


def resumen_tarjeta(clips: list[Clip], huerfanos: int, origen: Path) -> dict:
    total = sum(c.tamano for c in clips)
    con_proxy = sum(1 for c in clips if c.proxy)
    dias = sorted({c.fecha for c in clips})

    if not dias:
        jornadas = "0"
    elif len(dias) == 1:
        jornadas = f"1  ({fecha_bonita(dias[0])})"
    else:
        jornadas = (f"{len(dias)}  ({fecha_bonita(dias[0])} → "
                    f"{fecha_bonita(dias[-1])})")

    aviso_huerfanos = ""
    if huerfanos:
        aviso_huerfanos = (f"{huerfanos} {'proxy' if huerfanos == 1 else 'proxies'} "
                           "sin bruto asociado (no se copiará)")

    return {
        "tarjeta": str(origen),
        "brutos": f"{len(clips)} clips · {gb(total)}",
        "proxies": f"{con_proxy} de {len(clips)} clips tienen proxy",
        "huerfanos": aviso_huerfanos,
        "jornadas": jornadas,
    }


def describir_jornada(j: Jornada, total: int) -> dict:
    return {
        "indice": j.indice,
        "titulo": f"Lote {j.indice}/{total}",
        "fecha": fecha_bonita(j.fecha),
        "detalle": (f"{plural(len(j.clips), 'clip')} · {gb(j.peso)} · "
                    f"{plural(j.con_proxy, 'proxy' if j.con_proxy == 1 else 'proxie')}"),
        "nombres": [c.ruta.name for c in j.clips[:6]],
        "mas": len(j.clips) - 6 if len(j.clips) > 6 else 0,
        "primero": j.clips[0].ruta.name,
        "ultimo": j.clips[-1].ruta.name,
        "peso": j.peso,
        "brutos": len(j.clips),
        "proxies": j.con_proxy,
        "necesario": espacio_necesario(j.clips),
    }


# ------------------------------- Espacio ---------------------------------- #

def espacio_necesario(seleccion: list[Clip]) -> int:
    """Bytes que ocuparán los brutos más sus proxies."""
    necesario = sum(c.tamano for c in seleccion)
    necesario += sum(c.proxy.stat().st_size for c in seleccion if c.proxy)
    return necesario


def comprobar_espacio(base: Path, necesario: int) -> int:
    """Bytes libres en `base` (o en su ancla si no existe).

    Lanza `OSError` si no se puede consultar la unidad; quien llama decide qué
    avisar. La comparación con `necesario` la hace `hay_espacio`.
    """
    raiz = base if base.exists() else Path(base.anchor)
    return shutil.disk_usage(raiz).free


def hay_espacio(libre: int, necesario: int) -> bool:
    return libre >= necesario * MARGEN_ESPACIO


# ------------------------------ Motor de copia ----------------------------- #

class ErrorCopia(Exception):
    pass


class Cancelado(Exception):
    """Volcado cancelado; lleva lo completado hasta el momento."""

    def __init__(self, mensaje: str = "", resultados: list | None = None,
                 errores: list[str] | None = None, segundos: float = 0.0) -> None:
        super().__init__(mensaje)
        self.resultados = [] if resultados is None else resultados
        self.errores = [] if errores is None else errores
        self.segundos = segundos


@dataclass
class Progreso:
    fichero: str                 # nombre del fichero en curso
    tipo: str                    # "bruto" | "xml" | "proxy"
    fichero_hecho: int
    fichero_total: int
    lote: str                    # "LOTE 1/3 · 05/11"
    lote_hecho: int
    lote_total: int
    total_hecho: int
    total_total: int
    visibles_hechos: int         # brutos + proxies, sin XML
    visibles_total: int
    segundos: float              # tiempo activo, sin contar la pausa
    pausado: bool = False        # True mientras el volcado está en pausa


class _PausaContada:
    """Evento de pausa que acumula el tiempo pasado en `esperar_pausa`."""

    def __init__(self, evento: threading.Event) -> None:
        self._evento = evento
        self.pausado = 0.0

    def is_set(self) -> bool:
        return self._evento.is_set()



def esperar_pausa(pausa: threading.Event, cancelar: threading.Event) -> float:
    """Espera mientras `pausa` esté puesto, sin leer ni escribir.

    Duerme en tramos de `ESPERA_PAUSA_S` hasta que se quite la pausa o se pida
    cancelar; en ese caso vuelve y la comprobación de cancelación de quien llama
    lanza `Cancelado`. Devuelve los segundos que ha estado esperando.
    """
    inicio = None
    while pausa.is_set() and not cancelar.is_set():
        if inicio is None:
            inicio = time.monotonic()
        time.sleep(ESPERA_PAUSA_S)
    return 0.0 if inicio is None else time.monotonic() - inicio


def _esperar_si_pausa(pausa: threading.Event, cancelar: threading.Event,
                      notificar: Callable[[], None]) -> None:
    """Si la pausa está puesta, avisa al entrar y al salir y espera."""
    if not pausa.is_set():
        return
    notificar()
    segundos = esperar_pausa(pausa, cancelar)
    if isinstance(pausa, _PausaContada):
        pausa.pausado += segundos
    notificar()


def copiar_archivo(src: Path, dst: Path, avisar: Callable[[str], None],
                   al_bloque: Callable[[int], None],
                   cancelar: threading.Event,
                   pausa: threading.Event) -> str:
    """Copia con bloques. Devuelve 'copiado' | 'omitido'. Lanza ErrorCopia o Cancelado."""
    parcial = dst.with_suffix(dst.suffix + ".part")
    try:
        tamano = src.stat().st_size

        if dst.exists() and dst.stat().st_size == tamano:
            al_bloque(tamano)
            return "omitido"

        with open(src, "rb", buffering=0) as fi, open(parcial, "wb") as fo:
            while True:
                _esperar_si_pausa(pausa, cancelar, lambda: al_bloque(0))
                if cancelar.is_set():
                    raise Cancelado(f"Volcado cancelado al copiar {src.name}")
                bloque = fi.read(CHUNK)
                if not bloque:
                    break
                fo.write(bloque)
                al_bloque(len(bloque))
        if parcial.stat().st_size != tamano:
            raise ErrorCopia(f"Tamaño incorrecto al copiar {src.name}")
        os.replace(parcial, dst)
        try:
            shutil.copystat(src, dst)
        except OSError as e:
            avisar(f"{dst.name} se copió, pero sin conservar la fecha original: {e}")
        return "copiado"
    except OSError as e:
        raise ErrorCopia(f"{src.name}: {e}") from e
    finally:
        if parcial.exists():
            try:
                parcial.unlink()
            except OSError as e:
                avisar(f"No se pudo borrar {parcial}; bórralo a mano: {e}")


def nombre_proxy_destino(proxy: Path) -> str:
    return re.sub(SUFIJO_PROXY_ORIGEN + r"(?=\.[^.]+$)", SUFIJO_PROXY_DESTINO,
                  proxy.name, count=1, flags=re.IGNORECASE)


def volcar(seleccion: list[Clip], destino: Path, avisar: Callable[[str], None],
           al_progresar: Callable[[Progreso], None],
           al_error: Callable[[str], None],
           cancelar: threading.Event,
           pausa: threading.Event) -> tuple[list, list, float]:
    """Copia cada bruto por lotes de jornada, seguido de su XML y su proxy.

    Devuelve (resultados, errores, segundos activos). En pausa no lee ni escribe;
    `Cancelado` lleva lo completado hasta ese momento."""
    grupos: list[tuple[str, list[tuple[Path, Path, str]]]] = []
    jornadas = agrupar_jornadas(seleccion)
    for j in jornadas:
        trabajos = []
        for c in j.clips:
            trabajos.append((c.ruta, destino / c.ruta.name, "bruto"))
            if COPIAR_XML and c.xml:
                trabajos.append((c.xml, destino / CARPETA_XML / c.xml.name, "xml"))
            if c.proxy:
                trabajos.append((c.proxy,
                                 destino / CARPETA_PROXIES / nombre_proxy_destino(c.proxy),
                                 "proxy"))
        grupos.append((f"LOTE {j.indice}/{len(jornadas)} · {j.fecha:%d/%m}", trabajos))

    todos = [t for _, trabajos in grupos for t in trabajos]
    total_bytes = sum(t[0].stat().st_size for t in todos)
    visibles_total = sum(1 for t in todos if t[2] != "xml")
    hay_xml = any(t[2] == "xml" for t in todos)
    hay_proxy = any(t[2] == "proxy" for t in todos)

    destino.mkdir(parents=True, exist_ok=True)
    if hay_xml:
        (destino / CARPETA_XML).mkdir(exist_ok=True)
    if hay_proxy:
        (destino / CARPETA_PROXIES).mkdir(exist_ok=True)

    pausa = _PausaContada(pausa)
    resultados, errores = [], []
    inicio = time.monotonic()
    fichero_hecho = lote_hecho = total_hecho = 0
    visibles_hechos = 0
    fichero_nombre, fichero_tipo, fichero_total = "", "", 0
    etiqueta_lote, lote_total = "", 0

    def segundos_activos() -> float:
        return time.monotonic() - inicio - pausa.pausado

    def informar() -> None:
        al_progresar(Progreso(
            fichero=fichero_nombre,
            tipo=fichero_tipo,
            fichero_hecho=fichero_hecho,
            fichero_total=fichero_total,
            lote=etiqueta_lote,
            lote_hecho=lote_hecho,
            lote_total=lote_total,
            total_hecho=total_hecho,
            total_total=total_bytes,
            visibles_hechos=visibles_hechos,
            visibles_total=visibles_total,
            segundos=segundos_activos(),
            pausado=pausa.is_set(),
        ))

    def cancelado(mensaje: str) -> Cancelado:
        return Cancelado(mensaje, resultados, errores, segundos_activos())

    for etiqueta_lote, trabajos in grupos:
        lote_total = sum(t[0].stat().st_size for t in trabajos)
        lote_hecho = 0
        for src, dst, tipo in trabajos:
            fichero_nombre, fichero_tipo = src.name, tipo
            fichero_hecho = 0
            fichero_total = max(src.stat().st_size, 1)
            if pausa.is_set():
                _esperar_si_pausa(pausa, cancelar, informar)
            else:
                informar()
            if cancelar.is_set():
                raise cancelado(f"Volcado cancelado antes de copiar {src.name}")

            def al_bloque(n: int) -> None:
                nonlocal fichero_hecho, lote_hecho, total_hecho
                fichero_hecho += n
                lote_hecho += n
                total_hecho += n
                informar()

            try:
                estado = copiar_archivo(src, dst, avisar, al_bloque, cancelar, pausa)
                resultados.append((src, dst, tipo, estado))
            except Cancelado as e:
                raise cancelado(str(e)) from e
            except ErrorCopia as e:
                errores.append(str(e))
                al_error(str(e))
            if tipo != "xml":
                visibles_hechos += 1
                informar()

    return resultados, errores, segundos_activos()


# ------------------------------- Limpieza ---------------------------------- #

def _dentro(ruta: Path, base: Path) -> bool:
    try:
        ruta.relative_to(base)
        return True
    except ValueError:
        return False


def borrar_copiados(resultados, destino: Path,
                    avisar: Callable[[str], None]) -> tuple[int, list[str]]:
    """Borra los dst copiados de `resultados` y las carpetas vacías.

    Los "omitido" no se tocan (ya existían). Nunca sale de `destino`: un dst
    resuelto fuera de él es un error y no se borra. Las carpetas se eliminan
    con `rmdir` y solo si quedan vacías. Devuelve (n_borrados, errores).
    """
    destino_resuelto = destino.resolve()
    borrados = 0
    errores: list[str] = []

    def fallo(ruta: Path, motivo: str) -> None:
        texto = f"{ruta}: {motivo}"
        errores.append(texto)
        avisar(texto)

    for _src, dst, _tipo, estado in resultados:
        if estado != "copiado":
            continue
        ruta = Path(dst)
        try:
            if not _dentro(ruta.resolve(), destino_resuelto):
                fallo(ruta, f"está fuera del destino {destino}; no se borra")
                continue
            ruta.unlink()
            borrados += 1
        except OSError as e:
            fallo(ruta, str(e))

    for carpeta in (destino / CARPETA_XML, destino / CARPETA_PROXIES, destino):
        try:
            if carpeta.is_dir() and not any(carpeta.iterdir()):
                carpeta.rmdir()
        except OSError as e:
            fallo(carpeta, str(e))

    return borrados, errores


# --------------------------------- Resumen --------------------------------- #

def resumen_final(resultados, errores, segundos, destino: Path) -> dict:
    brutos = [r for r in resultados if r[2] == "bruto"]
    proxies = [r for r in resultados if r[2] == "proxy"]
    xmls = [r for r in resultados if r[2] == "xml"]
    omitidos = [r for r in resultados if r[3] == "omitido"]
    total_bytes = sum(r[0].stat().st_size for r in resultados)
    copiados_bytes = sum(r[0].stat().st_size for r in resultados if r[3] == "copiado")
    velocidad = copiados_bytes / segundos / 1e6 if segundos > 0 else 0

    filas = [
        ["Brutos", f"{len(brutos)} clips"],
        ["Proxies", f"{len(proxies)} → carpeta {CARPETA_PROXIES}{os.sep}"],
    ]
    if xmls:
        filas.append(["Metadatos", f"{len(xmls)} XML → carpeta {CARPETA_XML}{os.sep}"])
    if omitidos:
        filas.append(["Ya existían", f"{len(omitidos)} (omitidos, tamaño idéntico)"])
    filas.append(["Volumen", gb(total_bytes)])
    filas.append(["Tiempo", time.strftime("%H:%M:%S", time.gmtime(segundos))])
    filas.append(["Velocidad media", f"{velocidad:.0f} MB/s" if copiados_bytes else "—"])
    filas.append(["Destino", str(destino)])

    return {"ok": not errores, "filas": filas}


def guardar_registro(resultados, errores, segundos, destino: Path) -> Path:
    """Escribe el registro del volcado en el destino y devuelve su ruta."""
    total_bytes = sum(r[0].stat().st_size for r in resultados)
    log = destino / f"volcado_{datetime.now():%Y%m%d_%H%M%S}.txt"
    with open(log, "w", encoding="utf-8") as f:
        f.write(f"VolcadoSony — {datetime.now():%d/%m/%Y %H:%M:%S}\n")
        f.write(f"Destino: {destino}\n")
        f.write(f"Total: {gb(total_bytes)} en {segundos:.0f} s\n\n")
        for src, dst, tipo, estado in resultados:
            f.write(f"[{tipo:5s}] {estado:8s} {src}  ->  {dst}\n")
        for e in errores:
            f.write(f"[ERROR] {e}\n")
    return log
