# VolcadoSony

**[Versión en español aquí](README.md)**

![Windows 11](https://img.shields.io/badge/Windows-11-0078D4?logo=windows&logoColor=white)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![MIT License](https://img.shields.io/badge/License-MIT-green)

Offload **Sony camera** memory cards to your hard drive, in a single window
with a console look: triple progress bars (current file, batch, total),
transfer speed, elapsed time and ETA. The interface is in Spanish.

Works with **any Sony camera that records XAVC S / XAVC HS** — Alpha, ZV,
RX, FX3/FX30, compacts and 4K Handycams — since they all share the same card
structure. [Full list here](#compatible-cameras).

![VolcadoSony screenshot](docs/captura.jpg)

## What it does

Everything happens in the same window, top to bottom:

1. Auto-detects the SD card (scans all drives for `PRIVATE\M4ROOT\CLIP`). If
   several cards are present you pick one; if none is found you can type the
   drive or search again.
2. Shows the summary: originals, proxies, orphan proxies and shooting days.
3. Asks for the destination folder **name** and its **path** (empty = Desktop;
   *Examinar* button to browse).
4. **Shooting days** (recording date) are listed with checkboxes, all ticked
   at start: untick the ones you don't want and press *Volcar*. If there is
   not enough free space it warns you and lets you continue or cancel.
5. Copies the camera originals batch by batch in chronological order; each
   original is followed by its camera metadata XML sidecar (into the `_xml\`
   subfolder) and its proxy (into the `Proxies\` subfolder, renaming the `S03`
   suffix to `_Proxy`, e.g. `C0001S03.MP4` → `C0001_Proxy.MP4`). Orphan
   proxies (with no matching original) are skipped.
6. Writes a `volcado_YYYYMMDD_HHMMSS.txt` log in the destination with the
   details of every file.

## Compatible cameras

It works with **any Sony camera recording XAVC S, XAVC S-I or XAVC HS**:
they all store the originals in `PRIVATE\M4ROOT\CLIP` and the proxies in
`PRIVATE\M4ROOT\SUB`.

- **Cinema Line**: FX3, FX30
- **Full-frame Alpha**: A7S, A7S II, A7S III · A7 II\*, A7 III, A7 IV ·
  A7R II, A7R III, A7R IV, A7R V · A7C, A7C II, A7CR · A9, A9 II, A9 III ·
  A1, A1 II
- **APS-C Alpha**: A6100, A6300, A6400, A6500, A6600, A6700
- **ZV series**: ZV-1, ZV-1 II, ZV-1F, ZV-E10, ZV-E10 II, ZV-E1
- **RX series**: RX100 III to VII · RX10\* and RX10 II to IV · RX0, RX0 II ·
  RX1R II
- **Travel compacts**: HX95, HX99, WX700, WX800
- **4K Handycam**: FDR-AX33, AX40, AX43, AX45, AX53, AX60, AX100, AX700
  (and AXP projector variants)
- **Compact pro camcorders**: HXR-NX80, PXW-Z90 (in XAVC S mode)
- **A-mount**: A99 II

\* The original A7 II and RX10 need firmware 2.0, which added XAVC S.

Not every model records proxies (only those with *Proxy Recording*); on the
rest there is simply nothing to copy into `Proxies\`.

**Not compatible**: the FX6, FX9, Burano and Venice cinema cameras and XDCAM
gear use a different structure (`PRIVATE\XDROOT`, MXF files), and models that
only record AVCHD/MP4 (A6000, A5100, original RX100s...) never create the
`M4ROOT` folder.

## Download

Grab `VolcadoSony.exe` from the [**Releases**](../../releases) page. No
installation, no dependencies: double-click with the card inserted.

It needs the Microsoft Edge WebView2 Runtime (built into Windows 11). The
source drive can optionally be passed as an argument:

```
VolcadoSony.exe E:\        # use that drive as the source
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
pip install -r requirements.txt pyinstaller pytest
powershell -NoProfile -ExecutionPolicy Bypass -File desplegar.ps1
```

`desplegar.ps1` runs the tests (`python -m pytest -q`), builds with
`VolcadoSony.spec` and leaves `dist\VolcadoSony.exe`.

## Mac

The UI is HTML/CSS/JS on top of pywebview, which uses WebKit on macOS, so the
same code should run there (`python volcado_sony.py`; cards are looked up in
`/Volumes`). It has not been tested on a Mac and there is no Mac package.

## Configuration

Constants at the top of `volcadosony/nucleo.py`:

| Constant | Default | Meaning |
|---|---|---|
| `COPIAR_XML` | `True` | Copy the camera XML sidecars into the `_xml\` subfolder |
| `CARPETA_XML` | `"_xml"` | Name of the XML sidecars subfolder |
| `CARPETA_PROXIES` | `"Proxies"` | Name of the proxies subfolder |
| `SUFIJO_PROXY_DESTINO` | `"_Proxy"` | Suffix used when renaming proxies |
| `CHUNK` | 8 MB | Copy block size |

## License

[MIT](LICENSE) — use it, modify it and share it freely.
