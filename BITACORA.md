# BITACORA — VolcadoSony

- v2.0.0: app gráfica una ventana, estética consola. pywebview 6.2.1 + HTML/CSS/JS + Iosevka (como Joseante). Sin modo consola, sin rich.
- `volcadosony/nucleo.py` lógica sin UI (avisos/progreso por callbacks); `volcadosony/gui.py` Api + Emisor de eventos (100 ms); `volcadosony/ui/` vista; `volcado_sony.py` solo entrada (argumento opcional = tarjeta).
- Jornadas: casillas, todas marcadas al empezar. Destino: nombre + ruta (vacía = Escritorio, Examinar nativo).
- Orden de copia por clip: bruto → XML (`_xml\`) → proxy (`Proxies\`, `S03`→`_Proxy`), dentro de su lote de jornada.
- Pruebas: `python -m pytest -q` (48). desplegar.ps1 = pruebas + PyInstaller + copia a `C:\jaime\apps\volcado-sony`.
- 15/11 tareas 1-4: nombre destino precargado `AAAA.MM.DD - `; miniaturas primero/último por jornada (THMBNL\<stem>T01.JPG, si no ffmpeg) con ampliación; Pausar + Detener conservar/borrar (borra solo estado "copiado", nunca "omitido"/"reemplazado" ni fuera del destino); barras en `ui/barras.js|css` (bloques por octavos; total = tira de película negativo→revelado con las miniaturas).
- Prueba real con ventana oculta: script e2e que ralentiza `nucleo.volcar` para poder pausar.
- Mac: código portable (detección en /Volumes, Escritorio ~/Desktop), sin probar ni empaquetar.
- Retomar: nada pendiente. Versión sigue 2.0.0; release en GitHub sin publicar.
