# VolcadoSony

**[Versión en español aquí](README.md)**

![Windows 11](https://img.shields.io/badge/Windows-11-0078D4?logo=windows&logoColor=white)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![MIT License](https://img.shields.io/badge/License-MIT-green)

Offload **Sony A7III / A7SIII** SD cards to your hard drive, in text mode with
a polished console UI: colors, triple progress bars (current file, batch,
total), transfer speed, elapsed time and ETA. The interface is in Spanish.

![VolcadoSony screenshot](docs/captura.svg)

## What it does

1. Auto-detects the SD card (scans all drives for
   `drive:\PRIVATE\M4ROOT\CLIP`). If several cards are present, it asks which
   one to use.
2. Asks for the **name** of the destination folder.
3. Asks for the destination **path** (Enter = Windows Desktop).
4. Asks whether to offload **everything** (Enter = yes, `n` = no).
   - If you answer `n`, it groups the footage into **batches per shooting
     day** (recording date) and offers each batch one by one. All selected
     batches go to the same destination folder.
5. Copies the camera originals (plus their camera metadata XML sidecars) to
   the destination folder, batch by batch in chronological order.
6. Copies the proxies of the copied clips into the `Proxies\` subfolder,
   renaming the `S03` suffix to `_Proxy` (e.g. `C0001S03.MP4` →
   `C0001_Proxy.MP4`). Orphan proxies (with no matching original) are skipped.
7. Writes a `volcado_YYYYMMDD_HHMMSS.txt` log in the destination with the
   details of every file.

## Download

Grab `VolcadoSony.exe` from the [**Releases**](../../releases) page. No
installation, no dependencies: double-click with the card inserted.

You can also run it from a console:

```
VolcadoSony.exe            # auto-detects the card
VolcadoSony.exe E:\        # force that drive as the source
```

Or straight with Python:

```
pip install -r requirements.txt
python volcado_sony.py
```

## How it works

- **Recording date**: read from the camera XML sidecar (`CXXXXM01.XML`,
  `CreationDate` field), which is reliable even when filesystem dates are
  not. Clips without an XML fall back to the file date.
- **Proxies**: looked up in `PRIVATE\M4ROOT\SUB` (their actual location on
  Sony cameras) and also in `PRIVATE\M4ROOT\CLIP`.
- **Safe copies**: each file is copied to a temporary `.part` file that is
  only renamed to its final name once the copy completes and the size
  matches. Original file timestamps are preserved.
- **Resumable**: files that already exist in the destination with the same
  size are skipped, so an interrupted offload can be relaunched without
  recopying anything.
- **Disk space**: free space at the destination is checked before starting.

## Building the .exe

```
pip install rich pyinstaller
pyinstaller --onefile --console --name VolcadoSony ^
    --exclude-module numpy --exclude-module PIL ^
    --exclude-module PyQt5 --exclude-module matplotlib --exclude-module IPython ^
    volcado_sony.py
```

The executable lands in `dist\VolcadoSony.exe` (~11 MB, self-contained).

## Configuration

Constants at the top of `volcado_sony.py`:

| Constant | Default | Meaning |
|---|---|---|
| `COPIAR_XML` | `True` | Copy the camera XML sidecars along with the originals |
| `CARPETA_PROXIES` | `"Proxies"` | Name of the proxies subfolder |
| `SUFIJO_PROXY_DESTINO` | `"_Proxy"` | Suffix used when renaming proxies |
| `CHUNK` | 8 MB | Copy block size |

## License

[MIT](LICENSE) — use it, modify it and share it freely.
