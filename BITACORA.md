# BITACORA — VolcadoSony

- v2.0.0: app gráfica una ventana, estética consola. pywebview 6.2.1 + HTML/CSS/JS + Iosevka (como Joseante). Sin modo consola, sin rich.
- `volcadosony/nucleo.py` lógica sin UI (avisos/progreso por callbacks); `volcadosony/gui.py` Api + Emisor de eventos (100 ms); `volcadosony/ui/` vista; `volcado_sony.py` solo entrada (argumento opcional = tarjeta).
- Jornadas: casillas, todas marcadas al empezar. Destino: nombre + ruta (vacía = Escritorio, Examinar nativo).
- Orden de copia por clip: bruto → XML (`_xml\`) → proxy (`Proxies\`, `S03`→`_Proxy`), dentro de su lote de jornada.
- Pruebas: `python -m pytest -q` (35). desplegar.ps1 = pruebas + PyInstaller + copia a `C:\jaime\apps\volcado-sony`.
- Mac: código portable (detección en /Volumes, Escritorio ~/Desktop), sin probar ni empaquetar.
- Retomar: nada pendiente. Release v2.0.0 en GitHub sin publicar.
