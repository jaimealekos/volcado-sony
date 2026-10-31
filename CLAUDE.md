# VolcadoSony

- Desarrollo en `F:\code\github\volcado-sony` (antes `D:\code\github`; la ruta antigua ya no existe).
- Despliegue: la versión de trabajo vive SIEMPRE en `C:\jaime\apps\volcado-sony`. Actualizarla tras cada cambio de código.
- Compilar y desplegar: `powershell -NoProfile -ExecutionPolicy Bypass -File desplegar.ps1` (PyInstaller con `VolcadoSony.spec` y copia del .exe al destino).
- Pruebas: no hay suite; verificar con `python volcado_sony.py` sobre una carpeta de prueba.
- `dist/` y `build/` están en .gitignore: el .exe se distribuye en GitHub Releases.
