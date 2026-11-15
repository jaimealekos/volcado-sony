# Arquitectura — VolcadoSony 2

VolcadoSony vuelca brutos, XML y proxies de una tarjeta Sony (XAVC S/HS, estructura
`PRIVATE/M4ROOT`) a una carpeta del disco. Desde la versión 2 es una aplicación
gráfica de una sola ventana con estética de consola; el modo consola desaparece.

## Tecnología

- Ventana: pywebview 6.2.1 (WebView2 en Windows, WKWebView en macOS). La vista es
  HTML/CSS/JS sin dependencias, con la fuente Iosevka (OFL) empaquetada, igual que
  Joseante. Portable a macOS sin tocar la vista: lo específico de cada sistema vive
  en dos funciones de `nucleo` (detección de tarjetas y Escritorio).
- Empaquetado: PyInstaller (`VolcadoSony.spec`, `console=False`), un único .exe.

## Módulos

| Módulo | Fichero | Responsabilidad | Nivel |
|---|---|---|---|
| nucleo | `volcadosony/nucleo.py` | Lógica sin interfaz: detectar tarjetas, escanear clips, agrupar jornadas, comprobar espacio, copiar con progreso, escribir el registro. Comunica avisos y progreso por funciones de retorno. | normal |
| gui | `volcadosony/gui.py` + `volcadosony/ui/` | Ventana pywebview, clase `Api` expuesta a JS, hilo de volcado, entrega de eventos a la vista; vista HTML/CSS/JS. | normal |
| entrada | `volcado_sony.py` | Lee el argumento opcional (ruta de la tarjeta) y llama a `gui.run`. | trivial |

Dependencias: `entrada → gui → nucleo`. `nucleo` no importa nada de interfaz.

## Flujo (todo en la misma ventana, de arriba abajo)

1. Tarjeta: al abrir se busca sola (o se usa la ruta del argumento). Una: se usa.
   Varias: el usuario elige una. Ninguna: campo para escribir la unidad y botón
   para buscar de nuevo.
2. Resumen: tarjeta, brutos (clips y tamaño), proxies, proxies huérfanos, jornadas.
3. Destino: nombre de carpeta (obligatorio) y ruta base (por defecto el Escritorio,
   botón Examinar con diálogo nativo). Se indica si la carpeta ya existe.
4. Jornadas: una línea por jornada con casilla, todas marcadas al empezar.
5. Volcado: tres barras (fichero, lote, total) con porcentaje, bytes, velocidad,
   tiempo y ETA; errores en rojo debajo.
6. Resultado: mismo resumen que la versión de consola y registro `volcado_*.txt`
   en el destino.

Orden de copia por clip: bruto → XML (`_xml/`) → proxy (`Proxies/`, `S03`→`_Proxy`),
dentro de su lote de jornada, en orden cronológico. Sin cambios respecto a la v1.

## Pruebas

`python -m pytest -q`: `tests/test_nucleo.py` (tarjeta falsa en `tmp_path`) y
`tests/test_gui.py` (la `Api` con una ventana falsa que recoge los eventos; sin
abrir ventana real).
