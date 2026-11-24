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
| `convertir_rjpeg_a_tiff.py` | Convierte por lotes los R-JPEG (`*_T.JPG`) a TIFF float32 en °C con el DJI Thermal SDK (motor `thermal_parser` por defecto, o `dji_irp`), valida los rangos del SDK y copia los metadatos con ExifTool. |
| `correccion_temperaturas.py` | Corrección por emisividad (radiancia de banda 8–14 µm), deriva y línea empírica; métricas de validación; aplicación a un ortomosaico. |
| `ejemplo_mediciones.csv`, `ejemplo_deriva.csv` | Plantillas de mediciones de terreno (datos simulados). |

Requisitos: Windows o Linux (el SDK de DJI no existe para macOS), Python 3.9+, `numpy`, `tifffile`, `thermal-parser` (opcional `rasterio`) y ExifTool.

Estado: los scripts se probaron con simuladores del SDK; falta la prueba con el SDK real y fotos propias. Ver la sección "Registro de verificación" de la página.

> Los cálculos usan especificaciones publicadas por el fabricante. Verificar con el equipo antes de volar y contrastar siempre con la normativa DGAC vigente.
