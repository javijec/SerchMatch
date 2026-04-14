# XRD Search & Match

Aplicación local en Python para análisis de difracción de rayos X por polvo (PXRD/XRD), pensada como herramienta personal de investigación desde el día 1, pero diseñada con una arquitectura modular que permita evolucionarla hacia un proyecto open-source útil para cristalografía y ciencia de materiales.

## Objetivo

Esta primera versión permite:

- cargar difractogramas experimentales en `.xy`, `.txt` o `.csv`
- detectar automáticamente columnas de `2theta` e `intensity`
- visualizar el patrón experimental
- aplicar preprocesamiento básico
- detectar picos con `scipy.signal.find_peaks`
- cargar CIFs locales
- simular patrones teóricos con `pymatgen`
- comparar patrón experimental vs. candidatos teóricos
- obtener un ranking ordenado de fases candidatas
- superponer visualmente el patrón experimental y los patrones teóricos
- exportar resultados a `csv` o `json`

## Estado actual

La app es funcional para uso local y sirve como base de trabajo mantenible. No es una demo con resultados inventados: el flujo usa lectura real de datos, detección real de picos, simulación real desde CIF y un scoring inicial interpretable.

## Estructura del proyecto

```text
xrd_search_match/
├── app/
│   ├── __init__.py
│   └── streamlit_app.py
├── core/
│   ├── __init__.py
│   ├── cif_utils.py
│   ├── io.py
│   ├── matching.py
│   ├── models.py
│   ├── peaks.py
│   ├── preprocessing.py
│   ├── scoring.py
│   └── simulation.py
├── data/
│   ├── cif_library/
│   │   ├── NaCl.cif
│   │   └── Si.cif
│   └── examples/
│       ├── sample_experimental.csv
│       └── sample_experimental.xy
├── services/
│   ├── __init__.py
│   └── workflow.py
├── tests/
│   ├── conftest.py
│   ├── test_io.py
│   ├── test_matching.py
│   └── test_peaks.py
├── main.py
├── README.md
└── requirements.txt
```

## Arquitectura

### `core/`

Contiene el núcleo científico y de dominio:

- `io.py`: carga de difractogramas y exportación de resultados
- `preprocessing.py`: normalización, suavizado y corrección simple de fondo
- `peaks.py`: detección de picos
- `cif_utils.py`: validación y carga de estructuras CIF
- `simulation.py`: generación de patrones teóricos con `pymatgen`
- `scoring.py`: cálculo del score de similitud
- `matching.py`: ranking de candidatos
- `models.py`: dataclasses compartidas

### `services/`

Orquesta el flujo completo de análisis sin mezclar UI con lógica científica.

### `app/`

Interfaz Streamlit simple y orientada a trabajo científico local.

## Instalación

Requisitos:

- Python 3.11
- entorno local con compilación compatible para dependencias científicas

Instalación recomendada:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

### Lanzar la aplicación

```bash
python main.py
```

o directamente:

```bash
streamlit run app/streamlit_app.py
```

### Flujo de trabajo dentro de la app

1. Cargar un difractograma experimental.
2. Cargar uno o más CIFs candidatos.
3. Ajustar preprocesamiento, detección de picos y parámetros de matching.
4. Ejecutar el análisis.
5. Revisar:
   - difractograma procesado
   - picos detectados
   - ranking de fases
   - superposición experimental vs. candidatos
   - detalle del candidato seleccionado
6. Exportar el ranking a CSV o JSON.

## Ejemplos mínimos incluidos

- Patrón experimental sintético:
  - [`data/examples/sample_experimental.xy`](data/examples/sample_experimental.xy)
  - [`data/examples/sample_experimental.csv`](data/examples/sample_experimental.csv)
- CIFs de ejemplo:
  - [`data/cif_library/NaCl.cif`](data/cif_library/NaCl.cif)
  - [`data/cif_library/Si.cif`](data/cif_library/Si.cif)

Podés abrir la app y probar directamente con esos archivos.

## Algoritmo inicial de search & match

La estrategia implementada en esta primera versión es deliberadamente simple, pero científicamente razonable para una base de trabajo local:

1. Se detectan picos experimentales sobre el patrón preprocesado.
2. Se simulan picos teóricos desde cada CIF con `pymatgen`.
3. Se filtran picos teóricos poco intensos usando un umbral configurable.
4. Cada pico teórico importante busca su mejor pico experimental dentro de una tolerancia en `2theta`.
5. Para cada coincidencia se calcula:
   - similitud posicional
   - similitud de intensidad relativa
6. Se penalizan implícitamente los picos teóricos importantes no encontrados.
7. El score final se normaliza entre 0 y 100.

### Componentes del score

- `position_score`: promedio de similitud por posición de pico
- `intensity_score`: promedio de similitud de intensidades relativas
- `missing_penalty`: fracción de picos teóricos importantes no encontrados

La combinación final usa pesos configurables desde la interfaz:

```text
score = promedio_ponderado(
    position_score,
    intensity_score,
    matched_fraction
) * 100
```

Esto no reemplaza algoritmos comerciales avanzados ni búsqueda multifase, pero sí deja una base clara para iterar.

## Interfaz

La UI Streamlit está organizada en:

- `Sidebar`
  - carga de patrón experimental
  - carga de CIFs
  - parámetros de preprocesamiento
  - parámetros de detección de picos
  - parámetros de matching
- `Área principal`
  - difractograma procesado
  - tabla de picos detectados
  - ranking de candidatos
  - superposición visual
  - detalle y desglose de score del candidato seleccionado
  - exportación de resultados

## Tests

Se incluyen tests unitarios básicos para:

- lectura de datos
- detección de picos
- ranking/matching simple

Ejecutar:

```bash
pytest
```

## Limitaciones de esta primera versión

- No incluye refinamiento de perfil ni ajuste de fondo avanzado.
- No implementa deconvolución ni fitting completo de picos.
- No realiza búsqueda multifase automática.
- No integra bases de datos cristalográficas grandes.
- El scoring es inicial y está pensado para ser entendible y extensible, no definitivo.
- La app es local y no está empaquetada todavía como instalador distribuible.

## Robustez y extensibilidad previstas

El diseño está preparado para crecer en varias direcciones:

- reemplazar CIFs locales por una base de datos indexada
- mejorar el scoring con métricas híbridas pico-perfil
- incorporar matching multifase
- agregar exportes enriquecidos y reportes
- reutilizar el núcleo científico desde otra UI
- evolucionar a aplicación de escritorio o servicio web más robusto

## Next steps

- Incorporar comparación por perfil completo además del matching por picos.
- Agregar lectura de más formatos instrumentales y metadatos asociados.
- Separar una capa de repositorio para bibliotecas grandes de CIFs.
- Implementar cache de patrones teóricos simulados para acelerar búsquedas repetidas.
- Añadir búsqueda multifase iterativa con sustracción aproximada de contribuciones.
- Mejorar la exportación con tablas de picos emparejados y gráficos.
- Sumar validaciones más fuertes para CIFs problemáticos y patrones con formatos ambiguos.
- Empaquetar la app para distribución reproducible.
