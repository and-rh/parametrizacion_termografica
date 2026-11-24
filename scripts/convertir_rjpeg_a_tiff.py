#!/usr/bin/env python3
"""
Convierte imágenes térmicas R-JPEG de DJI (Mavic 3T y otros) a TIFF de 32 bits
con temperatura en °C por píxel, conservando los metadatos (GPS, orientación,
cámara) para poder usarlas en fotogrametría (Metashape, WebODM, Pix4D).

Requisitos
----------
1. DJI Thermal SDK (TSDK), gratuito, descargado desde el sitio oficial de DJI:
   https://www.dji.com/downloads/softwares/dji-thermal-sdk
   Se usa el ejecutable de ejemplo `dji_irp` (Linux) o `dji_irp.exe` (Windows)
   que viene en la carpeta utility/bin/<plataforma>/release_x64/ del SDK.
2. Python 3.9+ con:  pip install numpy tifffile
3. ExifTool (para copiar metadatos):  https://exiftool.org/

Uso
---
    python convertir_rjpeg_a_tiff.py --entrada fotos_vuelo/ --salida tiff/ \
        --dji-irp "C:/dji_thermal_sdk/utility/bin/windows/release_x64/dji_irp.exe" \
        --emisividad 1.0 --distancia 40 --humedad 60 --reflejada 20

Recomendación: convertir con emisividad 1.0 y corregir después cada superficie
con su emisividad real (ver correccion_temperaturas.py). Así todas las imágenes
quedan con el mismo criterio y la corrección por material se hace con un mapa
de coberturas, no a ciegas.

Notas
-----
* El Mavic 3T graba las térmicas como ..._T.JPG (R-JPEG) y las RGB como ..._V.JPG.
  El script procesa solo las que terminan en _T (cámbialo con --patron).
* Las opciones de `dji_irp` pueden variar entre versiones del SDK: revisa
  `dji_irp -h` en tu versión. Las usadas aquí son las de los ejemplos del TSDK:
  -s (entrada), -a measure (acción), -o (salida), --measurefmt float32,
  --distance, --humidity, --emissivity, --reflection.
* Rangos que acepta el SDK (aprox.): distancia 1–25 m, humedad 20–100 %,
  emisividad 0,10–1,00, temperatura reflejada −40 a 500 °C. Si vuelas sobre
  25 m, usa 25 (el SDK no corrige más allá) y deja la diferencia a la
  calibración con puntos de terreno.
"""
import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import tifffile

ANCHO, ALTO = 640, 512  # resolución térmica del Mavic 3T


def ejecutar_dji_irp(dji_irp, entrada, salida_raw, p):
    cmd = [
        str(dji_irp), "-s", str(entrada), "-a", "measure", "-o", str(salida_raw),
        "--measurefmt", "float32",
        "--distance", str(p.distancia),
        "--humidity", str(p.humedad),
        "--emissivity", str(p.emisividad),
        "--reflection", str(p.reflejada),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(salida_raw).exists():
        raise RuntimeError(f"dji_irp falló ({r.returncode}): {r.stdout.strip()} {r.stderr.strip()}")


def leer_raw(ruta, ancho=ANCHO, alto=ALTO):
    datos = np.fromfile(ruta, dtype=np.float32)
    if datos.size != ancho * alto:
        raise ValueError(f"Tamaño inesperado: {datos.size} valores (se esperaban {ancho*alto}). "
                         "Revisa --ancho/--alto o el formato de salida del SDK.")
    return datos.reshape(alto, ancho)


def escribir_tiff(ruta, temperatura):
    tifffile.imwrite(ruta, temperatura.astype(np.float32), photometric="minisblack")


def copiar_metadatos(exiftool, origen, destino):
    """Copia EXIF/XMP (GPS, cámara, gimbal) del R-JPEG al TIFF."""
    cmd = [exiftool, "-overwrite_original", "-tagsfromfile", str(origen),
           "-all:all", "-xmp:all", "-exif:all", str(destino)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"exiftool falló: {r.stderr.strip()}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="R-JPEG DJI → TIFF float32 en °C")
    ap.add_argument("--entrada", required=True, type=Path, help="Carpeta con R-JPEG")
    ap.add_argument("--salida", required=True, type=Path, help="Carpeta de TIFF de salida")
    ap.add_argument("--dji-irp", required=True, type=Path, help="Ruta al ejecutable dji_irp del DJI Thermal SDK")
    ap.add_argument("--exiftool", default="exiftool", help="Ruta a exiftool (por defecto, el del PATH)")
    ap.add_argument("--patron", default="*_T.JPG", help="Patrón de archivos térmicos (por defecto *_T.JPG)")
    ap.add_argument("--emisividad", type=float, default=1.0)
    ap.add_argument("--distancia", type=float, default=25.0, help="m (máx. que acepta el SDK: 25)")
    ap.add_argument("--humedad", type=float, default=60.0, help="% humedad relativa")
    ap.add_argument("--reflejada", type=float, default=20.0, help="°C temperatura aparente reflejada")
    ap.add_argument("--ancho", type=int, default=ANCHO)
    ap.add_argument("--alto", type=int, default=ALTO)
    p = ap.parse_args(argv)

    if not p.dji_irp.exists():
        sys.exit(f"No se encontró dji_irp en {p.dji_irp}")
    exiftool = shutil.which(p.exiftool) or (p.exiftool if Path(p.exiftool).exists() else None)
    if not exiftool:
        print("AVISO: no se encontró exiftool; los TIFF quedarán SIN GPS ni metadatos.", file=sys.stderr)

    archivos = sorted(set(p.entrada.glob(p.patron)) | set(p.entrada.glob(p.patron.lower())))
    if not archivos:
        sys.exit(f"No hay archivos que coincidan con {p.patron} en {p.entrada}")
    p.salida.mkdir(parents=True, exist_ok=True)

    registro = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, f in enumerate(archivos, 1):
            raw = Path(tmp) / (f.stem + ".raw")
            tif = p.salida / (f.stem + ".tif")
            try:
                ejecutar_dji_irp(p.dji_irp, f, raw, p)
                t = leer_raw(raw, p.ancho, p.alto)
                escribir_tiff(tif, t)
                if exiftool:
                    copiar_metadatos(exiftool, f, tif)
                registro.append([f.name, "ok", f"{t.min():.2f}", f"{t.mean():.2f}", f"{t.max():.2f}"])
                print(f"[{i}/{len(archivos)}] {f.name}: {t.min():.1f} a {t.max():.1f} °C")
            except Exception as e:  # sigue con el resto y deja constancia
                registro.append([f.name, f"error: {e}", "", "", ""])
                print(f"[{i}/{len(archivos)}] {f.name}: ERROR {e}", file=sys.stderr)

    with open(p.salida / "registro_conversion.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["archivo", "estado", "t_min_C", "t_media_C", "t_max_C"])
        w.writerows(registro)
        w.writerow([])
        w.writerow(["parametros", f"emisividad={p.emisividad}", f"distancia={p.distancia}",
                    f"humedad={p.humedad}", f"reflejada={p.reflejada}"])
    errores = sum(1 for r in registro if r[1] != "ok")
    print(f"Listo: {len(registro) - errores} convertidas, {errores} con error. Registro en {p.salida/'registro_conversion.csv'}")
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
