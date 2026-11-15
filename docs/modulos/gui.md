# Contrato — gui (`volcadosony/gui.py`, `volcadosony/ui/`)

Ventana única pywebview con estética de consola. Referencia de estilo y técnica:
`F:\code\github\joseante\joseante\webui.py` (hilo de entrega de eventos,
`evaluate_js`, ventana oculta para pruebas) y `F:\code\github\joseante\assets\ui\app.css`
(retícula de caracteres, cajas de línea, casillas `.check`). No se copia nada de
Joseante que no se use aquí.

## gui.py

```python
def run(ruta_argumento: str | None) -> int
```
Crea la ventana (`title="VolcadoSony"`, 1000×820, mínimo 820×600,
`background_color` = `--bg`), carga `ui/index.html` (ruta resuelta con
`sys._MEIPASS` si está congelado; si no, junto al módulo), expone `Api` con
`js_api` y llama a `webview.start()`. Variable de entorno `VOLCADO_VENTANA_OCULTA`:
con valor, `hidden=True` (solo pruebas). Devuelve 0.

### Eventos Python → vista

Un hilo `Emisor` (como `EventPump` de Joseante, simplificado) entrega como mucho
cada `INTERVALO_UI_MS = 100` con `window.evaluate_js("recibir(" + json + ")")` una
lista de eventos. De varios `progreso` seguidos solo queda el último. Tipos:

| type | campos | cuándo |
|---|---|---|
| `buscando` | — | empieza la búsqueda |
| `tarjetas` | `rutas: [str]` | varias tarjetas: elegir |
| `sin_tarjeta` | `mensaje` | ninguna, o la ruta dada no es tarjeta |
| `escaneando` | `ruta` | empieza el escaneo |
| `tarjeta` | `ruta`, `resumen` (dict de `nucleo.resumen_tarjeta`), `jornadas` (lista de `describir_jornada`), `escritorio` (str), `vacia` (bool) | escaneo hecho |
| `miniatura` | `indice`, `cual` (`"primero"` \| `"ultimo"`), `nombre`, `datos` (data URL JPEG o `null`) | tras `tarjeta`, una por el primer y el último clip de cada jornada (jornada de un clip: solo `primero`) |
| `aviso` | `texto` | cualquier `avisar` del núcleo |
| `progreso` | campos de `nucleo.Progreso` + `velocidad` (B/s del total copiado) y `eta` (s o null) | durante el volcado |
| `error` | `texto` | error de copia |
| `fin` | `ok`, `filas`, `errores: [str]`, `registro` (texto de la línea final: «Registro guardado en X» o el error) | volcado terminado |
| `cancelado` | — | volcado cancelado al cerrar |

### Api (métodos llamados desde JS; ninguno bloquea la vista más de un instante)

- `iniciar()` → lanza en hilo la búsqueda: con `ruta_argumento`, la valida
  (`es_tarjeta`, si no `sin_tarjeta` con el mensaje de la v1); sin él,
  `detectar_tarjetas`. Una tarjeta → escanea directamente.
- `usar_tarjeta(texto)` → `ruta_unidad(texto)`; si es tarjeta, escanea; si no,
  `sin_tarjeta` con «X no contiene la estructura Sony (PRIVATE\M4ROOT\CLIP).»
- `buscar_de_nuevo()` → repite la detección.
- `examinar(ruta_actual)` → diálogo nativo de carpeta (`webview.FOLDER_DIALOG`,
  directorio inicial = `ruta_actual` o Escritorio); devuelve la ruta o `""`.
- `revisar_destino(nombre, ruta)` → `{"destino": str, "existe": bool, "valido": bool}`
  con `sanear_nombre`; ruta vacía = Escritorio. Nombre vacío → `valido=False`.
- `preparar(nombre, ruta, indices)` → comprueba espacio de las jornadas marcadas:
  `{"ok": True}` o `{"ok": False, "mensaje": "Espacio insuficiente: se necesitan X y
  solo hay Y libres en Z"}`; si no se pudo comprobar, emite `aviso` (texto de la v1)
  y devuelve `{"ok": True}`.
- `volcar(nombre, ruta, indices)` → lanza el volcado en un hilo con las jornadas
  marcadas; al acabar, `fin` (incluye `guardar_registro`). Una sola vez por sesión.
- `salir()` → cierra la ventana.
- Al cerrar la ventana (`events.closing`) con un volcado en marcha: se pone el
  `threading.Event` de cancelación y se espera al hilo (máx. 5 s); el núcleo borra
  el `.part`.

Velocidad y ETA: `velocidad = total_hecho / segundos`; `eta =
(total_total - total_hecho) / velocidad` o `null` si no hay velocidad.

## Vista (`ui/index.html`, `ui/app.css`, `ui/app.js`, `ui/fonts/`)

Fuente: copiar `iosevka-latin-400-normal.woff2`, `iosevka-latin-600-normal.woff2` y
`OFL-iosevka.txt` de `F:\code\github\joseante\assets\ui\fonts\`. `font: 15px/22px
"Iosevka", "Cascadia Mono", Consolas, monospace`; sin ligaduras. Todo en ch y em
salvo grosores de línea (1px). `textContent` siempre (nunca `innerHTML` con datos).

Paleta (tokens en `:root`), la de la consola v1 sobre fondo de terminal:
`--bg #0C0C10`, `--bg-2 #15151C` (campos), `--bg-3 #1E1E28` (fila encima),
`--line #34344A`, `--fg #E6E6EE`, `--fg-2 #A6A6B8` (secundario), `--dim #8A8AA3`,
`--magenta #E879F9` (marco del banner, reglas, barras, acción principal),
`--cyan #67E8F9` (rótulos y bordes de tablas), `--green #4ADE80` (✔, completado),
`--yellow #FACC15` (avisos ⚠), `--red #F87171` (✖ errores). Contraste ≥ 4.5:1 del
texto sobre `--bg`.

Estructura, una columna centrada de `max-width: 96ch`, desplazamiento vertical del
contenido (no de la ventana), en este orden:

1. Banner: caja de doble línea (`border: 3px double var(--magenta)`), título
   «VOLCADO SONY» en negrita blanca centrado, debajo «Volcado de brutos y proxies
   de tarjeta SD al disco duro» en cyan, y «v2.0.0» en `--dim` abajo a la derecha
   sobre el borde (como el subtítulo de rich).
2. Sección tarjeta: línea de estado con prefijo de símbolo: spinner de texto
   (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` cada 80 ms, cyan) «Buscando tarjeta SD de Sony...» /
   «Escaneando la tarjeta...»; `✔` verde «Tarjeta SD detectada en E:\»; `!`
   amarillo «Se han detectado varias tarjetas:» + una fila por tarjeta con botón
   «Usar»; `✖` rojo + el mensaje + fila `▸ Unidad de la tarjeta [campo] [Usar]
   [Buscar de nuevo]`. Tarjeta vacía: `!` amarillo «La tarjeta no contiene ningún
   bruto en PRIVATE\M4ROOT\CLIP» y nada más debajo.
3. Resumen: tabla sin cabecera con borde redondeado cyan (`border-radius: 6px`),
   columna de rótulos de 18ch, rótulo en negrita y valor; filas Tarjeta, Brutos,
   Proxies, (huérfanos en amarillo con rótulo vacío), Jornadas (fechas en `--dim`).
4. Destino: filas `▸ Nombre de la carpeta Destino [campo]` y `▸ Ruta para la
   carpeta Destino [campo con placeholder = `escritorio` del evento `tarjeta`]
   [Examinar]`; debajo, en cuanto cambia algo (llamando a `revisar_destino`):
   verde «Destino: X» o amarillo «La carpeta X ya existe: se añadirá contenido
   (lo idéntico se omite).». El nombre solo se marca en rojo cuando el usuario lo
   ha tocado y lo ha dejado vacío. Al pintar la sección tras `tarjeta`, el nombre
   ya lleva la fecha local «AAAA.MM.DD - » (`nombrePorDefecto()`) y el cursor al
   final; el usuario escribe detrás.
5. Jornadas: regla «Selección por jornadas» (línea magenta con el texto en medio).
   Casilla maestra «Todas» (estado mixto `[-]`); una fila por jornada con casilla
   (marcada al empezar):
   `☑ Lote 1/3 · lunes 3 de noviembre de 2026 · 5 clips · 12.3 GB · 5 proxies` con
   «Lote i/n» en magenta negrita y la fecha en negrita; segunda línea en `--dim` con
    los nombres separados por dos espacios y «y N más...». Casillas dibujadas como
    texto (`[x]`/`[ ]` en Iosevka, la casilla real oculta pero accesible por teclado
    con foco visible). A la derecha, alineadas arriba y sin mover el texto, las
    miniaturas del primer y del último clip: 16:9 de 8ch de ancho, separadas 1ch,
    borde 1px `--line`, radio 2px; mientras llegan muestran «…» sobre `--bg-2`, y
    con `datos` nulo «sin imagen» en `--dim` a 11px. Cada miniatura es focusable
    (`tabindex=0`, `title` = nombre del clip); al pasar el ratón o al recibir foco
    se amplía en una capa flotante (`position: fixed`, `z-index` alto, 56ch, imagen
    16:9, borde `--cyan`, sombra) con pie «Primer clip · X» / «Último clip · X» en
    `--fg-2`, colocada junto a la miniatura y siempre dentro de la ventana (encima
    si no cabe debajo). Desaparece al salir el ratón o perder el foco; solo anima
    la opacidad (120 ms, sin animación con `prefers-reduced-motion`). Pulsar una
    miniatura no cambia la casilla de la jornada. Pie: «Seleccionado: N brutos +
    M proxies · X» y botón primario «Volcar» (magenta, texto oscuro), desactivado
    sin nombre de carpeta o sin jornadas marcadas.
6. Si `preparar` no da ok: `✖` rojo con el mensaje y botones «Continuar de todas
   formas» / «Cancelar».
7. Volcado: regla «Volcando N brutos + M proxies · X» (X = suma del campo
   numérico `necesario` de las jornadas marcadas); tres filas de barra (fichero con
   icono 🎬/🎞/📄 y nombre; lote; «TOTAL k/n»): rejilla `etiqueta 24ch | barra
   flexible (mínimo 12ch) | datos`; rótulo cyan negrita (recorta con …), barra de
   bloques de texto `█` magenta sobre `░` `--line` (verde al 100 %). Los datos van
   `white-space: nowrap` y sin cortar; si no caben, pasan a una segunda línea bajo
   la barra. En fichero y lote solo `%`, `X/Y GB` y `h:mm:ss` transcurrido; en TOTAL
   además `N MB/s` y `ETA h:mm:ss`. Errores debajo, en rojo con `✖`. Durante el
   volcado, destino y jornadas quedan desactivados.
8. Resultado: las barras y los errores del volcado NO se ocultan; debajo aparece una
   caja de doble línea verde con «✔ VOLCADO COMPLETADO» (texto blanco sobre verde) o
   roja con «VOLCADO TERMINADO CON ERRORES», la lista de errores, la tabla de `filas`
   (columna de rótulos de 18ch, borde verde o rojo) y la línea del registro en
   `--dim` (en rojo si falló). Botón «Salir».

Avisos (`aviso`): se añaden a una lista `⚠ texto` en amarillo justo bajo la
sección en curso. La vista se desplaza sola para que la sección en curso quede a
la vista. Teclado: Enter en los campos de destino = Volcar si está activo.

## Criterios de aceptación (tests/test_gui.py, sin ventana real)

1. `Api` con ventana falsa (objeto con `evaluate_js` que guarda el JSON): `iniciar`
   con ruta de tarjeta falsa emite `escaneando` y `tarjeta` con resumen y jornadas.
2. `iniciar` con ruta que no es tarjeta emite `sin_tarjeta`; `usar_tarjeta` con la
   buena emite `tarjeta`.
3. `revisar_destino` sanea el nombre, usa el Escritorio con ruta vacía y marca
   `existe`.
4. `volcar` con solo la jornada 2 marcada copia solo sus clips y emite `fin` con
   `ok=True`; el registro existe en el destino.
5. El emisor deja solo el último `progreso` de una ráfaga y conserva el orden del
   resto.
6. Comprobación manual de la sesión (no prueba): la vista con datos falsos.
7. Tras `iniciar` con tarjeta falsa con `THMBNL`, llegan eventos `miniatura` con
   data URL para el primero y el último de cada jornada; una jornada de un solo
   clip solo emite `primero`.
