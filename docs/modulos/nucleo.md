# Contrato — nucleo (`volcadosony/nucleo.py`)

Lógica de `volcado_sony.py` v1.0.2 sin `rich`, sin `input()` y sin `print`. Se
trasladan tal cual (mismo comportamiento y mismos textos de aviso): constantes de
configuración, `gb`, `plural`, `fecha_bonita`, `sanear_nombre`, `Clip`,
`buscar_insensible`, `escanear`, `miniatura`, `copiar_archivo` (reescrita sin
`Progress`), `nombre_proxy_destino`, `volcar` y el registro de `resumen_final`.
`VERSION = "2.0.0"`. Constantes de miniaturas: `CARPETA_MINIATURAS = "THMBNL"`,
`SUFIJO_MINIATURA = "T01.JPG"` y `TIMEOUT_FFMPEG_S = 20`. Pausa:
`ESPERA_PAUSA_S = 0.1` (tramo de espera).

## Avisos

Toda función que hoy llama a `avisar(texto)` recibe un parámetro
`avisar: Callable[[str], None]` (en `escritorio`, `Clip.__init__`, `escanear`,
`copiar_archivo`, `volcar`, `detectar_tarjetas`). Nunca se silencia un error.

## Interfaz pública

```python
def escritorio(avisar) -> Path
```
Windows: `SHGetKnownFolderPath(FOLDERID_Desktop)` como en la v1. Si falla con
`OSError` o `AttributeError`, avisa «No se pudo obtener la carpeta Escritorio de
Windows (<error>); se usa <ruta>.» y devuelve `Path.home() / "Desktop"`. Otros
sistemas: `Path.home() / "Desktop"`.

```python
def es_tarjeta(ruta: Path) -> bool          # ruta/PRIVATE/M4ROOT/CLIP es carpeta
def detectar_tarjetas(avisar) -> list[Path]
```
Windows: letras A–Z como en la v1. macOS: cada entrada de `/Volumes`. Linux: cada
entrada de `/media/<usuario>` y `/run/media/<usuario>`. Devuelve las que cumplen
`es_tarjeta`. Error de lectura de una unidad: aviso y se sigue.

```python
def ruta_unidad(texto: str) -> Path
```
Texto escrito por el usuario (`E`, `E:`, `E:\`, `/Volumes/SD`) a `Path`. En
Windows, una letra sola o `X:` pasa a `X:\`.

```python
def escanear(origen: Path, avisar) -> tuple[list[Clip], int]   # igual que v1

def miniatura(clip: Clip, avisar) -> bytes | None
```
Primero busca el JPG de la cámara: `clip.ruta.parent.parent / CARPETA_MINIATURAS`
(la carpeta `THMBNL` de la tarjeta) con `buscar_insensible`, nombre
`clip.ruta.stem + SUFIJO_MINIATURA` (ej. `C4104T01.JPG` para `C4104.MP4`). Si
existe, devuelve sus bytes. Si no, y `shutil.which("ffmpeg")` da una ruta, extrae
un fotograma del bruto con `ffmpeg -v error -ss 0 -i <bruto> -frames:v 1
-vf scale=640:-2 -f image2pipe -vcodec mjpeg -` (stdout; timeout
`TIMEOUT_FFMPEG_S = 20`; en Windows `creationflags=subprocess.CREATE_NO_WINDOW`).
Fallo de ffmpeg, timeout o de lectura: aviso con el motivo y `None`. Sin THMBNL y
sin ffmpeg: `None` sin aviso.

@dataclass
class Jornada:
    indice: int            # 1..n, orden cronológico
    fecha: date
    clips: list[Clip]
    peso: int              # suma de tamaños de los brutos (como la v1)
    con_proxy: int
def agrupar_jornadas(clips) -> list[Jornada]
```

```python
def resumen_tarjeta(clips, huerfanos, origen) -> dict
```
Devuelve `{"tarjeta": str, "brutos": "12 clips · 34.5 GB", "proxies": "11 de 12
clips tienen proxy", "huerfanos": "1 proxy sin bruto asociado (no se copiará)" o
"", "jornadas": "3  (lunes 1 de … → miércoles 3 de …)"}` con los mismos textos que
`tabla_resumen` de la v1 (sin marcado rich).

```python
def describir_jornada(j: Jornada, total: int) -> dict
```
`{"indice", "titulo": "Lote 1/3", "fecha": fecha_bonita, "detalle": "5 clips · 12.3
GB · 5 proxies", "nombres": [hasta 6 nombres], "mas": nº restantes, "primero":
nombre del primer clip, "ultimo": nombre del último (iguales si solo hay uno),
"peso": bytes de los brutos, "brutos": nº de clips, "proxies": nº con proxy,
"necesario": bytes de brutos más proxies}`. Mismos plurales que `elegir_lotes` de
la v1.

```python
def espacio_necesario(seleccion) -> int     # brutos + proxies, como v1
def comprobar_espacio(base: Path, necesario: int) -> int
```
Devuelve los bytes libres en `base` (o en su ancla si no existe). Lanza `OSError`
hacia quien llama, que avisará. El umbral `MARGEN_ESPACIO = 1.02` es constante del
módulo; `hay_espacio(libre, necesario)` aplica `libre >= necesario * MARGEN_ESPACIO`.

```python
@dataclass
class Progreso:
    fichero: str; tipo: str                 # nombre y "bruto" | "xml" | "proxy"
    fichero_hecho: int; fichero_total: int
    lote: str                               # "LOTE 1/3 · 05/11"
    lote_hecho: int; lote_total: int
    total_hecho: int; total_total: int
    visibles_hechos: int; visibles_total: int   # brutos + proxies, sin XML
    segundos: float                         # tiempo activo, sin contar la pausa
    pausado: bool                           # True mientras el volcado está en pausa

class Cancelado(Exception):
    resultados: list        # (src, dst, tipo, estado) completados hasta el momento
    errores: list[str]
    segundos: float         # tiempo activo hasta la cancelación

def esperar_pausa(pausa: threading.Event, cancelar: threading.Event) -> float
```
Duerme en tramos de `ESPERA_PAUSA_S` mientras `pausa` esté puesto y `cancelar` no.
No lee ni escribe. Al pedir cancelar vuelve y la comprobación de quien llama lanza
`Cancelado`; devuelve los segundos esperados.

```python
def copiar_archivo(src, dst, avisar, al_bloque, cancelar, pausa) -> str
def volcar(seleccion, destino, avisar, al_progresar: Callable[[Progreso], None],
           al_error: Callable[[str], None], cancelar: threading.Event,
           pausa: threading.Event) -> tuple[list, list, float]
```
Mismo orden, carpetas, comprobación de tamaño, `.part`, `copystat` y omisión de
idénticos que la v1. `al_progresar` se llama tras cada bloque y al cambiar de
fichero (la gui se encarga de no saturar la vista). `al_error` recibe cada error de
copia en cuanto ocurre (y se acumula en la lista). Si `cancelar` está puesto entre
bloques: borra el `.part` y lanza `Cancelado`.

Con `pausa` puesto, la copia espera entre bloques y antes de cada fichero sin leer
ni escribir (el `.part` del fichero en curso sigue abierto). Al entrar y al salir de
la pausa se llama una vez a `al_progresar` con `pausado` actualizado. `segundos` es
tiempo activo (monótono menos lo pausado), tanto en `Progreso` como en el valor que
devuelve `volcar`. Si se cancela, `volcar` adjunta a `Cancelado` los `resultados` y
`errores` acumulados y los `segundos` activos.

```python
def borrar_copiados(resultados, destino: Path, avisar) -> tuple[int, list[str]]
```
Borra solo los `dst` con estado `"copiado"` (nunca los `"omitido"` ni los `"reemplazado"`: ya había un fichero con ese nombre antes del volcado).
Después elimina `destino/_xml`, `destino/Proxies` y `destino` solo si quedan vacías
(`rmdir`, nunca `rmtree`). Nunca toca nada fuera de `destino`: si un `dst` resuelto
no está dentro del `destino` resuelto, lo deja, avisa y lo añade a los errores.
Devuelve `(n_borrados, errores)` con la ruta y el motivo de cada fallo.

```python
def resumen_final(resultados, errores, segundos, destino) -> dict
def guardar_registro(resultados, errores, segundos, destino) -> Path
```
`resumen_final` devuelve `{"ok": bool, "filas": [[rótulo, valor], ...]}` con las
mismas filas y textos que la tabla de la v1 (Brutos, Proxies, Metadatos si hay,
Ya existían si hay, Volumen, Tiempo, Velocidad media, Destino). Separador de
carpetas con `os.sep`. `guardar_registro` escribe el mismo fichero que la v1 y
devuelve su ruta; lanza `OSError` si falla.

## Criterios de aceptación (tests/test_nucleo.py, tarjeta falsa en tmp_path)

1. `escanear` empareja brutos de `CLIP` con proxies `S03` de `SUB` y de `CLIP`;
   cuenta huérfanos; fecha desde `CreationDate` del XML `M01.XML`, si no, mtime.
2. `agrupar_jornadas` ordena por fecha e indexa 1..n; `describir_jornada` corta a
   6 nombres y da el resto en `mas`.
3. `volcar` deja la estructura y el orden de la v1 (bruto, xml, proxy por clip,
   jornadas en orden), renombra `S03`→`_Proxy`, omite idénticos (estado
   "omitido") y la segunda pasada no recopia nada.
4. `volcar` con `cancelar` puesto lanza `Cancelado` y no deja ficheros `.part`.
5. `resumen_final` y `guardar_registro` dan las filas y el fichero esperados.
6. `ruta_unidad("e")`, `("E:")`, `("E:\\")` dan `E:\` en Windows.
7. `miniatura` lee el JPG de `THMBNL` (búsqueda insensible); sin THMBNL y sin
   ffmpeg da `None` sin aviso; un ffmpeg que falla da `None` y un aviso con el
   motivo.
8. `volcar` con `pausa` puesto desde el principio y quitado a los 0.3 s termina
   bien; `Progreso.segundos` y el `segundos` devuelto son menores que el tiempo
   real (la pausa no cuenta) y algún progreso lleva `pausado=True`.
9. Cancelar durante la pausa lanza `Cancelado` con los `resultados` completados,
   los `errores` y los `segundos` activos, sin dejar `.part`.
10. `borrar_copiados` borra los copiados, respeta los `"omitido"` y deja la
    carpeta si no queda vacía; un `dst` fuera de `destino` no se borra y genera
    error.
