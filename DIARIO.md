# DIARIO — VolcadoSony

## 2026-10-31 · fix: errores que se tragaban ahora avisan
- avisar() en amarillo: XML ilegible o sin fecha, carpeta/unidad ilegible, copystat, .part sin borrar, espacio sin comprobar. Registro fallido en rojo.
- preguntar con stdin cerrado sale con error (antes bucle infinito). Quedan pass solo en consola/escritorio/título.
- Verificado forzando fallos. Revisor Haiku: 1 bloqueante (sin pruebas, cubierto con comprobación manual), 3 importantes corregidos.

## 2026-10-31 · feat(volcar): proxy copiado justo tras su bruto
- Antes: todos los brutos y al final grupo PROXIES. Ahora cada clip: bruto, XML, proxy, en su lote.
- XML a subcarpeta `_xml\` (cambio previo sin commitear, entra en este commit). README ES/EN al día.
- Verificado con SD falsa: orden correcto, barras cuadran. Implementó DeepSeek (api4), revisó Haiku.
