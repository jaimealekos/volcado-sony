# VolcadoSony

- Desarrollo en `F:\code\github\volcado-sony` (antes `D:\code\github`; la ruta antigua ya no existe).
- Despliegue: la versión de trabajo vive SIEMPRE en `C:\jaime\apps\volcado-sony`. Actualizarla tras cada cambio de código.
- Compilar y desplegar: `powershell -NoProfile -ExecutionPolicy Bypass -File desplegar.ps1` (PyInstaller con `VolcadoSony.spec` y copia del .exe al destino).
- Pruebas: `python -m pytest -q` (desplegar.ps1 las ejecuta antes de compilar).
- `dist/` y `build/` están en .gitignore: el .exe se distribuye en GitHub Releases.
- App gráfica pywebview (WebView2; WebKit en Mac). Vista en `volcadosony/ui/`, lógica en `volcadosony/nucleo.py`. Ver docs/ARQUITECTURA.md.
- Prueba con ventana real sin mostrarla: variable `VOLCADO_VENTANA_OCULTA=1` y pilotar con `webview.windows[0].evaluate_js`. Ver la vista: servir `ui/` por http con un `window.pywebview.api` falso.
