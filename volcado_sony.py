#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
VolcadoSony — Volcado de tarjetas de cámaras Sony (XAVC S / XAVC HS) al disco.

Uso:
    VolcadoSony.exe            -> busca sola la tarjeta SD
    VolcadoSony.exe X:\        -> usa esa unidad o ruta como tarjeta de origen
"""

import sys

from volcadosony.gui import run


def main() -> int:
    argumento = sys.argv[1] if len(sys.argv) > 1 else None
    return run(argumento)


if __name__ == "__main__":
    sys.exit(main())
