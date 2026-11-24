#!/usr/bin/env python3
"""
Corrección de temperaturas de vuelos térmicos con puntos de terreno.

Implementa los cuatro pasos de la metodología del proyecto:

  1. Corrección por emisividad (si se convirtió con emisividad = 1):
         L(T_b) = ε·L(T_s) + (1 − ε)·L(T_r)   →   T_s = L⁻¹( [L(T_b) − (1 − ε)·L(T_r)] / ε )
     L: radiancia de Planck integrada en la banda del sensor (8–14 µm en el
     Mavic 3T). T_b: temperatura de brillo (ε = 1), T_r: temperatura aparente
     reflejada, ε: emisividad de la superficie. Por defecto se usa la radiancia
     de banda exacta (--metodo banda). La alternativa --metodo potencia usa
     L ∝ T^n con n = 4; en 0–50 °C el exponente local real de la banda va de
     5,0 a 4,3, pero la inversión con n = 4 difiere de la exacta en < 0,05 °C
     en casos típicos (ε ≥ 0,93).

  2. Corrección de deriva temporal, con los blancos de referencia sobrevolados al
     inicio y al final del vuelo:
         Δ(t) = Δ_ini + (Δ_fin − Δ_ini)·(t − t_ini)/(t_fin − t_ini)
         T_sin_deriva = T_dron − Δ(t)

  3. Calibración por línea empírica (mínimos cuadrados), con al menos 3 puntos
     que cubran el rango de temperaturas:
         T_terreno = a + b·T_dron

  4. Validación con puntos de verificación independientes: sesgo, MAE, RMSE, R².

Uso con un CSV de mediciones
----------------------------
    python correccion_temperaturas.py --mediciones mediciones.csv --salida resultados/

Columnas del CSV (separado por coma, decimales con punto):
    punto, rol, hora, t_dron, t_terreno, emisividad, t_reflejada
    - rol: "calibracion" o "verificacion"
    - hora: HH:MM:SS de la foto (EXIF) en que se midió el punto
    - t_dron: °C leída en el TIFF convertido con emisividad 1
    - t_terreno: °C medida en terreno (contacto/termocupla/radiómetro)
    - emisividad, t_reflejada: opcionales (si faltan, no se corrige emisividad)

Opcional: --referencias-deriva deriva.csv  (columnas: hora, t_dron, t_terreno)
con los pasos sobre el blanco de referencia al inicio y al final.

Opcional: --aplicar ortomosaico.tif  aplica la ecuación final al ortomosaico.
"""
import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

K = 273.15


# ---------- 1. Emisividad ----------
_H, _C, _KB = 6.62607015e-34, 2.99792458e8, 1.380649e-23
_LAM = np.linspace(8e-6, 14e-6, 601)          # banda del sensor del Mavic 3T (8–14 µm)
_TT = np.arange(200.0, 400.01, 0.01)          # tabla de búsqueda en K
_LL = None


def radiancia_banda(t_k):
    """Radiancia de Planck integrada en 8–14 µm (W·m⁻²·sr⁻¹)."""
    t = np.atleast_1d(np.asarray(t_k, float))[:, None]
    x = _H * _C / (_LAM[None, :] * _KB * t)
    esp = 2 * _H * _C**2 / _LAM[None, :]**5 / np.expm1(x)
    return np.trapezoid(esp, _LAM, axis=1) if hasattr(np, "trapezoid") else np.trapz(esp, _LAM, axis=1)


def _inv_banda(l):
    global _LL
    if _LL is None:
        _LL = radiancia_banda(_TT)
    return np.interp(l, _LL, _TT)


def corregir_emisividad(t_brillo_c, emisividad, t_reflejada_c, n=4.0, metodo="banda"):
    tb = np.asarray(t_brillo_c, dtype=float) + K
    tr = np.asarray(t_reflejada_c, dtype=float) + K
    e = np.asarray(emisividad, dtype=float)
    if metodo == "potencia":
        return ((tb**n - (1.0 - e) * tr**n) / e) ** (1.0 / n) - K
    forma = np.broadcast(tb, tr, e).shape
    lb = radiancia_banda(np.ravel(np.broadcast_to(tb, forma)))
    lr = radiancia_banda(np.ravel(np.broadcast_to(tr, forma)))
    ls = (lb - (1.0 - np.ravel(np.broadcast_to(e, forma))) * lr) / np.ravel(np.broadcast_to(e, forma))
    res = _inv_banda(ls).reshape(forma) - K
    return float(res) if res.shape == () else res


# ---------- 2. Deriva ----------
def a_segundos(hora):
    if isinstance(hora, (int, float)):
        return float(hora)
    h = datetime.strptime(hora.strip(), "%H:%M:%S")
    return h.hour * 3600 + h.minute * 60 + h.second


def ajustar_deriva(horas, t_dron, t_terreno):
    """Devuelve una función Δ(t) lineal a partir de ≥2 pasos sobre la referencia."""
    s = np.array([a_segundos(h) for h in horas])
    d = np.asarray(t_dron, float) - np.asarray(t_terreno, float)
    if len(s) < 2:
        return lambda t: np.full_like(np.asarray(t, float), d[0] if len(d) else 0.0)
    m, c = np.polyfit(s, d, 1)
    return lambda t: m * np.asarray([a_segundos(x) for x in np.atleast_1d(t)]) + c


# ---------- 3. Línea empírica ----------
def ajustar_linea_empirica(t_dron, t_terreno):
    x = np.asarray(t_dron, float)
    y = np.asarray(t_terreno, float)
    if len(x) < 3:
        raise ValueError("Se necesitan al menos 3 puntos de calibración.")
    b, a = np.polyfit(x, y, 1)
    return float(a), float(b)


# ---------- 4. Métricas ----------
def metricas(pred, obs):
    pred = np.asarray(pred, float)
    obs = np.asarray(obs, float)
    err = pred - obs
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((obs - obs.mean()) ** 2))
    return {
        "n": int(len(obs)),
        "sesgo_C": float(err.mean()),
        "MAE_C": float(np.abs(err).mean()),
        "RMSE_C": float(math.sqrt(np.mean(err**2))),
        "R2": float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
    }


def leer_csv(ruta):
    with open(ruta, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def num(v):
    return float(v) if v not in (None, "") else None


def procesar(filas, deriva=None, n=4.0, metodo="banda", usar_emisividad=True):
    for f in filas:
        t = num(f["t_dron"])
        e, tr = num(f.get("emisividad")), num(f.get("t_reflejada"))
        if usar_emisividad and e is not None and tr is not None:
            t = float(corregir_emisividad(t, e, tr, n, metodo))
        if deriva is not None:
            t = t - float(deriva([f["hora"]])[0])
        f["t_corr_previa"] = t
    cal = [f for f in filas if f["rol"].strip().lower().startswith("cal")]
    ver = [f for f in filas if f["rol"].strip().lower().startswith("ver")]
    a, b = ajustar_linea_empirica([f["t_corr_previa"] for f in cal], [num(f["t_terreno"]) for f in cal])
    res = {"a": a, "b": b, "ecuacion": f"T_terreno = {a:.3f} + {b:.4f} · T_dron",
           "calibracion": metricas([a + b * f["t_corr_previa"] for f in cal], [num(f["t_terreno"]) for f in cal]),
           "sin_calibrar_verificacion": None, "verificacion": None}
    if ver:
        obs = [num(f["t_terreno"]) for f in ver]
        res["sin_calibrar_verificacion"] = metricas([num(f["t_dron"]) for f in ver], obs)
        res["verificacion"] = metricas([a + b * f["t_corr_previa"] for f in ver], obs)
    for f in filas:
        f["t_final"] = a + b * f["t_corr_previa"]
    return res, filas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Corrección de temperaturas con puntos de terreno")
    ap.add_argument("--mediciones", required=True, type=Path)
    ap.add_argument("--referencias-deriva", type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--metodo", choices=["banda", "potencia"], default="banda",
                    help="Corrección de emisividad: radiancia de banda 8–14 µm (exacta) o potencia T^n")
    ap.add_argument("--n", type=float, default=4.0, help="Exponente para --metodo potencia (por defecto 4)")
    ap.add_argument("--sin-emisividad", action="store_true", help="No corregir por emisividad aunque el CSV la traiga")
    ap.add_argument("--aplicar", type=Path, help="Ortomosaico TIFF (°C) al que aplicar la ecuación")
    p = ap.parse_args(argv)

    filas = leer_csv(p.mediciones)
    deriva = None
    if p.referencias_deriva:
        r = leer_csv(p.referencias_deriva)
        deriva = ajustar_deriva([x["hora"] for x in r], [num(x["t_dron"]) for x in r], [num(x["t_terreno"]) for x in r])
    res, filas = procesar(filas, deriva, p.n, p.metodo, not p.sin_emisividad)

    p.salida.mkdir(parents=True, exist_ok=True)
    (p.salida / "ecuacion.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(p.salida / "mediciones_corregidas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(res["ecuacion"])
    for k in ("calibracion", "sin_calibrar_verificacion", "verificacion"):
        if res[k]:
            m = res[k]
            print(f"{k:28s} n={m['n']:2d}  sesgo={m['sesgo_C']:+.2f}  MAE={m['MAE_C']:.2f}  RMSE={m['RMSE_C']:.2f}  R²={m['R2']:.3f}")

    if p.aplicar:
        # Ojo: la ecuación se ajustó sobre valores ya corregidos por emisividad y deriva.
        # Aplíquela a un ortomosaico procesado con el mismo criterio (o sin esas
        # correcciones previas si tampoco se usaron en el CSV).
        destino = p.salida / (p.aplicar.stem + "_corregido.tif")
        try:
            import rasterio  # conserva la georreferencia del GeoTIFF
            with rasterio.open(p.aplicar) as src:
                orto = src.read(1).astype(np.float32)
                perfil = src.profile
                if src.nodata is not None:
                    orto[orto == src.nodata] = np.nan
            out = (res["a"] + res["b"] * orto).astype(np.float32)
            perfil.update(dtype="float32", nodata=np.nan, count=1)
            with rasterio.open(destino, "w", **perfil) as dst:
                dst.write(out, 1)
            print(f"Ortomosaico corregido (GeoTIFF): {destino}")
        except ImportError:
            import tifffile
            orto = tifffile.imread(p.aplicar).astype(np.float32)
            out = (res["a"] + res["b"] * orto).astype(np.float32)
            tifffile.imwrite(destino, out)
            print(f"Ortomosaico corregido: {destino} (SIN georreferencia: instale rasterio para conservarla)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
