#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
VolcadoSony — Volcado de tarjetas de cámaras Sony (XAVC S / XAVC HS) al disco duro.

Compatible con cualquier cámara Sony que grabe con la estructura PRIVATE\M4ROOT:
Alpha (A7/A9/A1/A6xxx), ZV, RX, FX3/FX30, compactas HX/WX y Handycam 4K.

Estructura de la tarjeta:
    unidad:\PRIVATE\M4ROOT\CLIP   -> brutos de video (*.MP4) + sidecars XML (*M01.XML)
    unidad:\PRIVATE\M4ROOT\SUB    -> proxies (*S03.MP4)  [se busca tambien en CLIP]

Uso:
    VolcadoSony.exe            -> detecta automaticamente la tarjeta SD
    VolcadoSony.exe X:\        -> usa esa unidad/ruta como origen (debe contener PRIVATE\M4ROOT)
"""

import ctypes
import ctypes.wintypes
import os
import re
import shutil
import string
import sys
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# ----------------------------- Configuracion ------------------------------ #

VERSION = "1.0.1"

CHUNK = 8 * 1024 * 1024          # tamano de bloque de copia (8 MB)
COPIAR_XML = True                # copiar tambien los sidecars XML de los brutos
CARPETA_XML = "_xml"             # nombre de la subcarpeta de sidecars XML
CARPETA_PROXIES = "Proxies"      # nombre de la subcarpeta de proxies
SUFIJO_PROXY_ORIGEN = "S03"      # sufijo Sony del proxy
SUFIJO_PROXY_DESTINO = "_Proxy"  # sufijo con el que se renombra al copiar

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# Consola en UTF-8 (evita errores cp1252 en consolas antiguas o salida redirigida)
if os.name == "nt":
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
try:
    sys.stdin.reconfigure(encoding="utf-8-sig", errors="replace")
except Exception:
    pass

console = Console(highlight=False)

RE_PROXY = re.compile(r"^(?P<stem>.+)" + SUFIJO_PROXY_ORIGEN + r"$", re.IGNORECASE)


# ------------------------------- Utilidades ------------------------------- #

def escritorio_windows() -> Path:
    """Ruta real del Escritorio (respeta redirecciones tipo OneDrive)."""
    try:
        from ctypes import windll, wintypes  # noqa: F401

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
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None,
                                                      ctypes.byref(ppath)) == 0:
            ruta = Path(ppath.value)
            ctypes.windll.ole32.CoTaskMemFree(ppath)
            return ruta
    except Exception:
        pass
    return Path.home() / "Desktop"


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


def preguntar(texto: str, por_defecto: str = "") -> str:
    console.print(f"  [bold cyan]▸[/] [bold]{texto}[/]", end="")
    if por_defecto:
        console.print(f" [dim]{por_defecto}[/]", end="")
    console.print(" ", end="")
    try:
        return input().strip("\ufeff \t")
    except EOFError:
        console.print()
        console.print("  [bold red]✖ La entrada estándar se cerró: no se puede preguntar "
                      "al usuario. Saliendo.[/]")
        sys.exit(1)


def si_no(texto: str) -> bool:
    """Enter = si, n/N = no."""
    r = preguntar(texto, "[Enter = Sí / n = No]")
    return not r.lower().startswith("n")


def avisar(texto: str) -> None:
    """Aviso no bloqueante: el volcado sigue adelante."""
    console.print(f"  [yellow]⚠ {escape(texto)}[/]")


def pausa_final() -> None:
    console.print()
    try:
        input("  Pulsa Enter para salir... ")
    except EOFError:
        pass


# --------------------------- Deteccion de la SD --------------------------- #

def detectar_tarjetas() -> list[Path]:
    """Busca unidades que contengan PRIVATE\\M4ROOT\\CLIP."""
    encontradas = []
    for letra in string.ascii_uppercase:
        raiz = Path(f"{letra}:\\")
        try:
            if (raiz / "PRIVATE" / "M4ROOT" / "CLIP").is_dir():
                encontradas.append(raiz)
        except OSError as e:
            avisar(f"No se pudo leer la unidad {letra}: {e}")
            continue
    return encontradas


def elegir_origen() -> Path:
    if len(sys.argv) > 1:
        origen = Path(sys.argv[1])
        if (origen / "PRIVATE" / "M4ROOT" / "CLIP").is_dir():
            return origen
        console.print(f"  [bold red]✖[/] La ruta [bold]{escape(str(origen))}[/] no contiene "
                      r"[bold]PRIVATE\M4ROOT\CLIP[/]")
        sys.exit(1)

    with console.status("[bold cyan]Buscando tarjeta SD de Sony...", spinner="dots"):
        tarjetas = detectar_tarjetas()

    if not tarjetas:
        console.print(r"  [bold red]✖[/] No se ha encontrado ninguna unidad con "
                      r"[bold]PRIVATE\M4ROOT\CLIP[/]")
        console.print("    Inserta la tarjeta SD y vuelve a ejecutar el programa,")
        console.print("    o indica la unidad manualmente:")
        r = preguntar("Unidad de la tarjeta (ej. E:) o Enter para salir:")
        if not r:
            sys.exit(0)
        origen = Path(r if r.endswith(("\\", "/")) else r + "\\")
        if not (origen / "PRIVATE" / "M4ROOT" / "CLIP").is_dir():
            console.print(f"  [bold red]✖[/] [bold]{escape(str(origen))}[/] tampoco contiene la "
                          "estructura Sony. Saliendo.")
            sys.exit(1)
        return origen

    if len(tarjetas) == 1:
        console.print("  [bold green]✔[/] Tarjeta SD detectada en "
                      f"[bold]{escape(str(tarjetas[0]))}[/]")
        return tarjetas[0]

    console.print("  [bold yellow]![/] Se han detectado varias tarjetas:")
    for i, t in enumerate(tarjetas, 1):
        console.print(f"      [bold]{i}[/]) {t}")
    while True:
        r = preguntar(f"¿Cuál usar? [1-{len(tarjetas)}]:")
        if r.isdigit() and 1 <= int(r) <= len(tarjetas):
            return tarjetas[int(r) - 1]


# ----------------------------- Escaneo de clips ---------------------------- #

class Clip:
    __slots__ = ("ruta", "tamano", "fecha", "fuente_fecha", "xml", "proxy")

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.tamano = ruta.stat().st_size
        self.xml: Path | None = None
        self.proxy: Path | None = None
        self.fecha, self.fuente_fecha = self._fecha()

    def _fecha(self):
        """Fecha de grabacion: primero el XML de la camara, si no, el sistema de archivos."""
        xml = buscar_insensible(self.ruta.parent, self.ruta.stem + "M01.XML")
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


def buscar_insensible(carpeta: Path, nombre: str) -> Path | None:
    objetivo = nombre.lower()
    try:
        for f in carpeta.iterdir():
            if f.name.lower() == objetivo:
                return f
    except OSError as e:
        avisar(f"No se pudo listar la carpeta {carpeta}: {e}")
    return None


def escanear(origen: Path) -> tuple[list[Clip], int]:
    """Devuelve (clips ordenados por nombre, nº de proxies huérfanos descartados)."""
    clip_dir = origen / "PRIVATE" / "M4ROOT" / "CLIP"
    sub_dir = origen / "PRIVATE" / "M4ROOT" / "SUB"

    brutos: dict[str, Clip] = {}
    proxies: dict[str, Path] = {}

    with console.status("[bold cyan]Escaneando la tarjeta...", spinner="dots"):
        for carpeta in (clip_dir, sub_dir):
            if not carpeta.is_dir():
                continue
            for f in sorted(carpeta.iterdir()):
                if not f.is_file() or f.suffix.lower() != ".mp4":
                    continue
                m = RE_PROXY.match(f.stem)
                if m:
                    proxies.setdefault(m.group("stem").lower(), f)
                else:
                    brutos.setdefault(f.stem.lower(), Clip(f))

    huerfanos = 0
    for stem, ruta_proxy in proxies.items():
        if stem in brutos:
            brutos[stem].proxy = ruta_proxy
        else:
            huerfanos += 1

    return sorted(brutos.values(), key=lambda c: c.ruta.name.lower()), huerfanos


# ------------------------------- Interfaz --------------------------------- #

def banner() -> None:
    titulo = Text()
    titulo.append("VOLCADO SONY", style="bold white")
    sub = Text("Volcado de brutos y proxies de tarjeta SD al disco duro", style="cyan")
    console.print()
    console.print(Panel(Align.center(Group(Align.center(titulo), Align.center(sub))),
                        box=box.DOUBLE, border_style="bright_magenta", padding=(1, 4),
                        subtitle=f"[dim]v{VERSION}[/]", subtitle_align="right"))
    console.print()


def tabla_resumen(clips: list[Clip], huerfanos: int, origen: Path) -> None:
    total = sum(c.tamano for c in clips)
    con_proxy = sum(1 for c in clips if c.proxy)
    dias = sorted({c.fecha for c in clips})

    t = Table(box=box.ROUNDED, border_style="cyan", show_header=False, padding=(0, 2))
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Tarjeta", escape(str(origen)))
    t.add_row("Brutos", f"{len(clips)} clips · {gb(total)}")
    t.add_row("Proxies", f"{con_proxy} de {len(clips)} clips tienen proxy")
    if huerfanos:
        plural = "proxy" if huerfanos == 1 else "proxies"
        t.add_row("", f"[yellow]{huerfanos} {plural} sin bruto asociado "
                      "(no se copiará)[/]")
    t.add_row("Jornadas", f"{len(dias)}" + (
        f"  [dim]({fecha_bonita(dias[0])})[/]" if len(dias) == 1 else
        f"  [dim]({fecha_bonita(dias[0])} → {fecha_bonita(dias[-1])})[/]"))
    console.print(t)
    console.print()


def elegir_lotes(clips: list[Clip]) -> list[Clip]:
    """Agrupa por dia y pregunta lote a lote."""
    por_dia: dict = {}
    for c in clips:
        por_dia.setdefault(c.fecha, []).append(c)

    seleccion: list[Clip] = []
    console.print(Rule("[bold]Selección por jornadas[/]", style="bright_magenta"))
    console.print()
    n_lotes = len(por_dia)
    for i, (dia, lote) in enumerate(sorted(por_dia.items()), 1):
        peso = sum(c.tamano for c in lote)
        con_proxy = sum(1 for c in lote if c.proxy)
        console.print(f"  [bold bright_magenta]Lote {i}/{n_lotes}[/] · "
                      f"[bold]{fecha_bonita(dia)}[/] · "
                      f"{plural(len(lote), 'clip')} · {gb(peso)} · "
                      f"{plural(con_proxy, 'proxy' if con_proxy == 1 else 'proxie')}")
        nombres = "  ".join(c.ruta.name for c in lote[:6])
        extra = f"  [dim]y {len(lote) - 6} más...[/]" if len(lote) > 6 else ""
        console.print(f"      [dim]{nombres}[/]{extra}")
        if si_no("¿Copiar este lote?"):
            seleccion.extend(lote)
            console.print("      [bold green]✔ Añadido al volcado[/]")
        else:
            console.print("      [dim]— Omitido[/]")
        console.print()
    return seleccion


# ------------------------------ Motor de copia ----------------------------- #

class ErrorCopia(Exception):
    pass


def copiar_archivo(src: Path, dst: Path, progreso: Progress,
                   t_fichero, t_lote, t_total) -> str:
    """Copia con progreso. Devuelve 'copiado' | 'omitido'. Lanza ErrorCopia."""
    tamano = src.stat().st_size

    if dst.exists() and dst.stat().st_size == tamano:
        progreso.update(t_fichero, completed=tamano)
        progreso.update(t_lote, advance=tamano)
        progreso.update(t_total, advance=tamano)
        return "omitido"

    parcial = dst.with_suffix(dst.suffix + ".part")
    try:
        with open(src, "rb", buffering=0) as fi, open(parcial, "wb") as fo:
            while True:
                bloque = fi.read(CHUNK)
                if not bloque:
                    break
                fo.write(bloque)
                progreso.update(t_fichero, advance=len(bloque))
                progreso.update(t_lote, advance=len(bloque))
                progreso.update(t_total, advance=len(bloque))
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


def volcar(seleccion: list[Clip], destino: Path) -> tuple[list, list, float]:
    """Copia cada bruto por lotes de jornada, seguido de su XML y su proxy.

    Devuelve (resultados, errores, segundos)."""
    # Lotes de clips, uno por jornada, en orden cronologico
    por_dia: dict = {}
    for c in seleccion:
        por_dia.setdefault(c.fecha, []).append(c)

    grupos: list[tuple[str, list[tuple[Path, Path, str]]]] = []
    dias = sorted(por_dia)
    for i, dia in enumerate(dias, 1):
        trabajos = []
        for c in por_dia[dia]:
            trabajos.append((c.ruta, destino / c.ruta.name, "bruto"))
            if COPIAR_XML and c.xml:
                trabajos.append((c.xml, destino / CARPETA_XML / c.xml.name, "xml"))
            if c.proxy:
                trabajos.append((c.proxy,
                                 destino / CARPETA_PROXIES / nombre_proxy_destino(c.proxy),
                                 "proxy"))
        grupos.append((f"LOTE {i}/{len(dias)} · {dia:%d/%m}", trabajos))

    todos = [t for _, trabajos in grupos for t in trabajos]
    total_bytes = sum(t[0].stat().st_size for t in todos)
    n_visibles = sum(1 for t in todos if t[2] != "xml")
    hay_xml = any(t[2] == "xml" for t in todos)
    hay_proxy = any(t[2] == "proxy" for t in todos)

    destino.mkdir(parents=True, exist_ok=True)
    if hay_xml:
        (destino / CARPETA_XML).mkdir(exist_ok=True)
    if hay_proxy:
        (destino / CARPETA_PROXIES).mkdir(exist_ok=True)

    resultados, errores = [], []
    inicio = time.monotonic()

    progreso = Progress(
        TextColumn("  [bold cyan]{task.fields[etiqueta]}"),
        BarColumn(bar_width=None, complete_style="bright_magenta",
                  finished_style="bold green"),
        TaskProgressColumn(),
        DownloadColumn(binary_units=False),
        TransferSpeedColumn(),
        TextColumn("[dim]•[/]"),
        TimeElapsedColumn(),
        TextColumn("[dim]ETA[/]"),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    )

    with progreso:
        # Orden de las barras: fichero en curso, lote actual, total
        t_fichero = progreso.add_task("fichero", total=1, etiqueta="")
        t_lote = progreso.add_task("lote", total=1, etiqueta="")
        t_total = progreso.add_task("total", total=total_bytes,
                                    etiqueta=f"TOTAL 0/{n_visibles}")

        visibles_hechos = 0
        for etiqueta_lote, trabajos in grupos:
            lote_bytes = sum(t[0].stat().st_size for t in trabajos)
            progreso.reset(t_lote, total=max(lote_bytes, 1),
                           etiqueta=etiqueta_lote)
            for src, dst, tipo in trabajos:
                icono = {"bruto": "🎬", "proxy": "🎞 ", "xml": "📄"}[tipo]
                progreso.update(t_fichero, completed=0,
                                total=max(src.stat().st_size, 1),
                                etiqueta=f"{icono} {src.name}")
                try:
                    estado = copiar_archivo(src, dst, progreso,
                                            t_fichero, t_lote, t_total)
                    resultados.append((src, dst, tipo, estado))
                except ErrorCopia as e:
                    errores.append(str(e))
                    progreso.console.print(f"    [bold red]✖ {e}[/]")
                if tipo != "xml":
                    visibles_hechos += 1
                    progreso.update(t_total,
                                    etiqueta=f"TOTAL {visibles_hechos}/{n_visibles}")

    return resultados, errores, time.monotonic() - inicio


# --------------------------------- Resumen --------------------------------- #

def resumen_final(resultados, errores, segundos, destino: Path) -> None:
    brutos = [r for r in resultados if r[2] == "bruto"]
    proxies = [r for r in resultados if r[2] == "proxy"]
    xmls = [r for r in resultados if r[2] == "xml"]
    omitidos = [r for r in resultados if r[3] == "omitido"]
    total_bytes = sum(r[0].stat().st_size for r in resultados)
    copiados_bytes = sum(r[0].stat().st_size for r in resultados if r[3] == "copiado")
    velocidad = copiados_bytes / segundos / 1e6 if segundos > 0 else 0

    t = Table(box=box.ROUNDED, border_style="green" if not errores else "red",
              show_header=False, padding=(0, 2))
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Brutos", f"{len(brutos)} clips")
    t.add_row("Proxies", f"{len(proxies)} → carpeta {CARPETA_PROXIES}\\")
    if xmls:
        t.add_row("Metadatos", f"{len(xmls)} XML → carpeta {CARPETA_XML}\\")
    if omitidos:
        t.add_row("Ya existían", f"{len(omitidos)} (omitidos, tamaño idéntico)")
    t.add_row("Volumen", gb(total_bytes))
    t.add_row("Tiempo", time.strftime("%H:%M:%S", time.gmtime(segundos)))
    t.add_row("Velocidad media", f"{velocidad:.0f} MB/s" if copiados_bytes else "—")
    t.add_row("Destino", escape(str(destino)))

    console.print()
    if errores:
        console.print(Panel(Align.center(Text("VOLCADO TERMINADO CON ERRORES",
                                              style="bold white on red")),
                            box=box.DOUBLE, border_style="red"))
        for e in errores:
            console.print(f"  [bold red]✖[/] {e}")
    else:
        console.print(Panel(Align.center(Text("✔ VOLCADO COMPLETADO",
                                              style="bold white on green")),
                            box=box.DOUBLE, border_style="green"))
    console.print(t)

    # Registro en el destino
    log = destino / f"volcado_{datetime.now():%Y%m%d_%H%M%S}.txt"
    try:
        with open(log, "w", encoding="utf-8") as f:
            f.write(f"VolcadoSony — {datetime.now():%d/%m/%Y %H:%M:%S}\n")
            f.write(f"Destino: {destino}\n")
            f.write(f"Total: {gb(total_bytes)} en {segundos:.0f} s\n\n")
            for src, dst, tipo, estado in resultados:
                f.write(f"[{tipo:5s}] {estado:8s} {src}  ->  {dst}\n")
            for e in errores:
                f.write(f"[ERROR] {e}\n")
        console.print(f"  [dim]Registro guardado en {log.name}[/]")
    except OSError as e:
        texto = (f"No se pudo guardar el registro en {escape(str(log))}: "
                 f"{escape(str(e))}.")
        if not errores:
            texto += " Los ficheros sí se copiaron."
        console.print(f"  [bold red]✖ {texto}[/]")


# ----------------------------------- Main ---------------------------------- #

def main() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW("VolcadoSony")
        except Exception:
            pass

    banner()

    origen = elegir_origen()
    clips, huerfanos = escanear(origen)

    if not clips:
        console.print("  [bold yellow]![/] La tarjeta no contiene ningún bruto en "
                      r"PRIVATE\M4ROOT\CLIP")
        pausa_final()
        return

    console.print()
    tabla_resumen(clips, huerfanos, origen)

    # 1) Nombre de la carpeta destino
    while True:
        nombre = sanear_nombre(preguntar("Nombre de la carpeta Destino:"))
        if nombre:
            break
        console.print("      [yellow]El nombre no puede estar vacío.[/]")

    # 2) Ruta de la carpeta destino (Enter = Escritorio)
    r = preguntar("Ruta para la carpeta Destino", "[Enter = Escritorio]:")
    base = Path(r) if r else escritorio_windows()
    destino = base / nombre
    if destino.exists():
        console.print(f"      [yellow]La carpeta {escape(str(destino))} ya existe: "
                      "se añadirá contenido (lo idéntico se omite).[/]")
    else:
        console.print(f"      [green]Destino:[/] {escape(str(destino))}")
    console.print()

    # 3) ¿Todo o por lotes?
    if si_no("¿Volcar todos los brutos + proxies?"):
        seleccion = clips
    else:
        console.print()
        seleccion = elegir_lotes(clips)

    if not seleccion:
        console.print("  [bold yellow]No se ha seleccionado nada. Fin.[/]")
        pausa_final()
        return

    # Comprobacion de espacio libre
    necesario = sum(c.tamano for c in seleccion)
    necesario += sum(c.proxy.stat().st_size for c in seleccion if c.proxy)
    try:
        libre = shutil.disk_usage(base if base.exists() else base.anchor).free
        if libre < necesario * 1.02:
            console.print(f"  [bold red]✖ Espacio insuficiente:[/] se necesitan "
                          f"{gb(necesario)} y solo hay {gb(libre)} libres en "
                          f"{base.anchor}")
            if not si_no("¿Continuar de todas formas?"):
                pausa_final()
                return
    except OSError as e:
        avisar(f"No se pudo comprobar el espacio libre en {base.resolve().anchor}: "
               f"se continúa sin comprobarlo ({e})")

    n_proxies = sum(1 for c in seleccion if c.proxy)
    console.print()
    console.print(Rule(f"[bold]Volcando {len(seleccion)} brutos + {n_proxies} proxies "
                       f"· {gb(necesario)}[/]", style="bright_magenta"))
    console.print()

    resultados, errores, segundos = volcar(seleccion, destino)
    resumen_final(resultados, errores, segundos, destino)
    pausa_final()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n  [bold red]Volcado interrumpido por el usuario.[/]")
        sys.exit(130)
