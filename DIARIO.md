# DIARIO — VolcadoSony

## 2026-11-15 · feat: v2.0.0 interfaz gráfica estilo consola
- pywebview + HTML/CSS/JS con Iosevka (referencia Joseante). Una ventana: tarjeta, resumen, destino, jornadas con casillas, 3 barras, resultado.
- Lógica movida a volcadosony/nucleo.py; gui.py + ui/. 35 pruebas pytest. Portable a Mac en código, sin probar.
- Implementó DeepSeek (api4, 3 encargos); revisó Sonnet (0 bloqueantes, 4 importantes corregidos). Barras y espacio del ✔ retocados por la sesión. Verificado: maqueta en navegador + punta a punta con ventana oculta.

## 2026-10-31 · fix: errores que se tragaban ahora avisan
- avisar() en amarillo: XML ilegible o sin fecha, carpeta/unidad ilegible, copystat, .part sin borrar, espacio sin comprobar. Registro fallido en rojo.
- preguntar con stdin cerrado sale con error (antes bucle infinito). Quedan pass solo en consola/escritorio/título.
- Verificado forzando fallos. Revisor Haiku: 1 bloqueante (sin pruebas, cubierto con comprobación manual), 3 importantes corregidos.

## 2026-10-31 · feat(volcar): proxy copiado justo tras su bruto
- Antes: todos los brutos y al final grupo PROXIES. Ahora cada clip: bruto, XML, proxy, en su lote.
- XML a subcarpeta `_xml\` (cambio previo sin commitear, entra en este commit). README ES/EN al día.
- Verificado con SD falsa: orden correcto, barras cuadran. Implementó DeepSeek (api4), revisó Haiku.
