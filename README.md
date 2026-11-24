# Termografía aérea de áreas verdes urbanas

Documento de trabajo del proyecto de investigación sobre el efecto de parques y plazas urbanas en la temperatura de superficie, medido con termografía aérea (DJI Mavic 3T, planificación en Dronelink).

**Página:** abrir `index.html` (publicada con GitHub Pages).

## Contenido

- Justificación del traslape 80/80 sobre la cámara térmica.
- Matriz interactiva de 280 combinaciones de vuelo (altura, traslapes, ángulo de cámara, tipo de vuelo), con descarga en CSV.
- Superficies de captura y tamaños mínimos de blancos según el GSD.
- Plan de la primera campaña y listas de chequeo (Dronelink, DJI Pilot 2, DGAC).
- Conversión R-JPEG → TIFF radiométrico y metodología de corrección de temperaturas.

## Scripts (`scripts/`)

| Archivo | Uso |
|---|---|
| `convertir_rjpeg_a_tiff.py` | Convierte por lotes los R-JPEG (`*_T.JPG`) a TIFF float32 en °C con el DJI Thermal SDK y copia los metadatos con ExifTool. |
| `correccion_temperaturas.py` | Corrección por emisividad, deriva y línea empírica; métricas de validación; aplicación a un ortomosaico. |
| `ejemplo_mediciones.csv`, `ejemplo_deriva.csv` | Plantillas de mediciones de terreno (datos simulados). |

Requisitos: Python 3.9+, `numpy`, `tifffile` (opcional `rasterio`), DJI Thermal SDK y ExifTool.

> Los cálculos usan especificaciones publicadas por el fabricante. Verificar con el equipo antes de volar y contrastar siempre con la normativa DGAC vigente.
