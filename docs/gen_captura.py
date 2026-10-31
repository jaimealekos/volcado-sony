# Genera docs/captura.svg: un fotograma realista de la UI de VolcadoSony
# usando los mismos estilos Rich que el programa real.
import random
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (BarColumn, DownloadColumn, Progress,
                           TaskProgressColumn, TextColumn, TimeElapsedColumn,
                           TimeRemainingColumn, TransferSpeedColumn)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

random.seed(7)
console = Console(record=True, width=96, force_terminal=True, legacy_windows=False)

# --- Banner (identico al del programa) ---
titulo = Text()
titulo.append("VOLCADO SONY", style="bold white")
sub = Text("Volcado de brutos y proxies de tarjeta SD al disco duro", style="cyan")
console.print()
console.print(Panel(Align.center(Group(Align.center(titulo), Align.center(sub))),
                    box=box.DOUBLE, border_style="bright_magenta", padding=(1, 4),
                    subtitle="[dim]v1.0.2[/]", subtitle_align="right"))
console.print()
console.print("  [bold green]✔[/] Tarjeta SD detectada en [bold]E:[/]\\")
console.print()

t = Table(box=box.ROUNDED, border_style="cyan", show_header=False, padding=(0, 2))
t.add_column(style="bold")
t.add_column()
t.add_row("Tarjeta", "E:\\")
t.add_row("Brutos", "27 clips · 103.4 GB")
t.add_row("Proxies", "19 de 27 clips tienen proxy")
t.add_row("Jornadas", "3  [dim](jueves 9 de julio de 2026 → sábado 11 de julio de 2026)[/]")
console.print(t)
console.print()
console.print("  [bold cyan]▸[/] [bold]Nombre de la carpeta Destino:[/] Rodaje_Madrid")
console.print("  [bold cyan]▸[/] [bold]Ruta para la carpeta Destino[/] [dim][Enter = Escritorio]:[/]")
console.print("      [green]Destino:[/] C:\\Users\\jaime\\Desktop\\Rodaje_Madrid")
console.print()
console.print("  [bold cyan]▸[/] [bold]¿Volcar todos los brutos + proxies?[/] [dim][Enter = Sí / n = No][/]")
console.print(Rule("[bold]Volcando 27 brutos + 19 proxies · 103.4 GB[/]",
                   style="bright_magenta"))
console.print()

# --- Fotograma de las tres barras a mitad de volcado ---
reloj = [0.0]
prog = Progress(
    TextColumn("  [bold cyan]{task.fields[etiqueta]}"),
    BarColumn(bar_width=None, complete_style="bright_magenta", finished_style="bold green"),
    TaskProgressColumn(),
    DownloadColumn(binary_units=False),
    TransferSpeedColumn(),
    TextColumn("[dim]•[/]"),
    TimeElapsedColumn(),
    TextColumn("[dim]ETA[/]"),
    TimeRemainingColumn(),
    console=console, expand=True, get_time=lambda: reloj[0], auto_refresh=False,
)
GB = 1_000_000_000
t_f = prog.add_task("f", total=int(4.3 * GB), etiqueta="🎬 C0013.MP4")
t_l = prog.add_task("l", total=int(38.2 * GB), etiqueta="LOTE 2/3 · 10/07")
t_t = prog.add_task("t", total=int(103.4 * GB), etiqueta="TOTAL 13/27")

# Posicion de partida del fotograma
prog.update(t_l, completed=int(14.9 * GB))
prog.update(t_t, completed=int(38.0 * GB))

# Muestras de velocidad realistas (~180 MB/s) para que Rich calcule ETA y MB/s.
# Primero 45 s de ficheros anteriores; el fichero en curso empieza en el s 45.
for paso in range(60):
    reloj[0] += 1.0
    inc = 180_000_000 + random.randint(-25_000_000, 25_000_000)
    if paso == 45:
        prog.reset(t_f, total=int(4.3 * GB), etiqueta="🎬 C0013.MP4")
    if paso >= 45:
        prog.update(t_f, advance=inc)
    prog.update(t_l, advance=inc)
    prog.update(t_t, advance=inc)

console.print(prog.get_renderable())
console.print()

salida = Path(__file__).parent / "captura.svg"
salida.write_text(console.export_svg(title="VolcadoSony"), encoding="utf-8")
print("SVG generado:", salida, f"({salida.stat().st_size/1024:.0f} KB)")
