# Compila VolcadoSony.exe y lo despliega en la carpeta de trabajo del usuario.
$ErrorActionPreference = 'Stop'
$destino = 'C:\jaime\apps\volcado-sony'
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm VolcadoSony.spec
if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación con PyInstaller: revisa la salida anterior.' }
New-Item -ItemType Directory -Force $destino | Out-Null
Copy-Item dist\VolcadoSony.exe $destino -Force
Write-Host "Desplegado en $destino"
