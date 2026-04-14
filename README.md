# PXRD Search & Match

Aplicación local en Python para difracción de rayos X por polvo (PXRD/XRD) con arquitectura modular y motor de búsqueda inspirado en el enfoque clásico de search & match basado en picos, pero implementado de forma abierta, mantenible y lista para evolucionar.

## Qué cambió

La versión anterior comparaba patrón experimental contra CIFs simulados de forma directa en cada corrida. Ahora el flujo usa una biblioteca local indexada:

1. se recorren CIFs locales
2. se simulan patrones teóricos con `pymatgen`
3. se extraen y almacenan picos relevantes
4. se indexan los picos más intensos en SQLite
5. el patrón experimental se transforma en un fingerprint compacto
6. la búsqueda usa prefiltrado rápido + scoring detallado e interpretable

Esto reduce trabajo repetido, separa claramente indexación y búsqueda, y deja base real para crecer hacia una herramienta comunitaria.

## Sync incremental desde COD

Se agregó soporte para integrar un mirror local de COD sin rehacer toda la base en cada actualización.

Flujo:

1. mantener un mirror local de COD
2. ejecutar sync remoto por `svn` o `rsync` si esas herramientas están instaladas
3. comparar estado actual contra un manifiesto local
4. reindexar solo CIFs nuevos o modificados
5. eliminar de SQLite entradas borradas del mirror

Servicios involucrados:

- [services/cod_sync.py](services/cod_sync.py)
- [services/indexing.py](services/indexing.py)

Métodos soportados:

- `svn` contra `svn://www.crystallography.net/cod`
- `rsync` contra `rsync://www.crystallography.net/cif/`

Importante:

- si no tenés `svn` o `rsync` instalados, igual podés usar el modo incremental local sobre un mirror ya descargado manualmente
- el entorno de desarrollo actual donde se hizo este refactor no tenía `svn` ni `rsync` en `PATH`, así que la app deja ambos modos pero no los ejecuta automáticamente sin esas herramientas

Extras agregados sobre este flujo:

- verificación de `svn` desde la app
- instalación de `svn` en Windows vía `winget` usando paquete `Slik.Subversion`
- filtro químico previo a indexación (`include_elements` / `exclude_elements`)
- indexación paralela con múltiples workers para mirrors grandes

## Arquitectura

```text
SerchMatch/
├── app/
│   └── streamlit_app.py
├── core/
│   ├── cif_utils.py
│   ├── io.py
│   ├── matching.py
│   ├── models.py
│   ├── peaks.py
│   ├── preprocessing.py
│   ├── scoring.py
│   └── simulation.py
├── database/
│   ├── builder.py
│   └── repository.py
├── services/
│   ├── indexing.py
│   ├── search.py
│   └── workflow.py
├── data/
│   ├── cif_library/
│   └── examples/
├── tests/
├── main.py
├── README.md
└── requirements.txt
```

### `core/`

- lectura de difractogramas
- preprocesamiento básico
- detección de picos experimentales
- simulación teórica desde CIF
- matching peak-based
- scoring interpretable
- modelos de datos
- interfaz lista para futuro `ProfileMatcher`

### `database/`

- construcción de biblioteca local
- persistencia SQLite
- indexación de picos intensos
- prefiltrado rápido de candidatos

### `services/`

- workflow de indexación
- workflow de search & match
- serialización para UI y exportes

### `app/`

- interfaz Streamlit

## Formato de biblioteca local

La primera implementación usa SQLite porque combina simplicidad local con mejor escalabilidad que JSON plano.

Tablas principales:

- `library_entries`: metadata por fase
- `peaks`: lista completa de picos teóricos
- `peak_index`: índice simple de top picos discretizados por bin de `2theta`

La capa `database/repository.py` encapsula acceso. Si más adelante querés migrar a otra base o agregar caché parcial de COD, el punto de extensión ya existe.

## Flujo Search & Match

### Fase 1: construir biblioteca

Para cada CIF:

- cargar estructura con `pymatgen`
- simular patrón teórico PXRD
- normalizar intensidades relativas
- guardar:
  - `source_id`
  - nombre de archivo
  - fórmula
  - sistema cristalino
  - grupo espacial
  - elementos
  - lista de picos
  - top picos
  - rango de `2theta`

### Fase 2: fingerprint experimental

Del difractograma experimental:

- carga robusta `.xy`, `.txt`, `.csv`
- preprocesamiento opcional
- detección de picos con `scipy.signal.find_peaks`
- normalización relativa
- selección de top N picos para prefilter

### Fase 3: búsqueda rápida de candidatos

#### Etapa A: prefilter

Se usan bins de `2theta` sobre los picos más intensos:

- coincidencia con top picos
- mínimo de picos compatibles
- compatibilidad de rango de `2theta`
- filtro opcional por elementos

#### Etapa B: scoring detallado

Para cada candidato:

- emparejamiento pico a pico dentro de tolerancia configurable
- score por posición
- score por intensidad relativa
- penalización por picos teóricos faltantes
- penalización por picos experimentales extra

## Score actual

El score final se normaliza a `0-100`.

```text
raw_score =
    w_pos * score_posicion
  + w_int * score_intensidad
  + w_match * fraccion_emparejada
  - w_missing * penalizacion_faltantes
  - w_extra * penalizacion_extra

score_total = clamp(raw_score * 100, 0, 100)
```

Pesos por defecto:

- `position = 0.45`
- `intensity = 0.25`
- `matched_fraction = 0.15`
- `missing_penalty = 0.10`
- `extra_penalty = 0.05`

Interpretación:

- `position_score`: cuán cerca cae cada pico experimental respecto al teórico
- `intensity_score`: similitud de intensidades relativas
- `matched_fraction`: qué fracción del patrón teórico quedó explicada
- `missing_penalty`: picos teóricos intensos ausentes
- `extra_penalty`: picos experimentales no explicados

No reemplaza Rietveld ni profile fitting completo. Sí entrega un ranking simple, razonable y auditable.

## Búsqueda multifase básica

Se implementó una primera versión ligera:

1. tomar mejor candidato
2. marcar picos experimentales explicados
3. buscar sobre residual no explicado
4. proponer combinaciones simples de dos fases

No hay refinamiento cuantitativo ni sustracción física completa de intensidades. Es una base útil para mezclas simples.

## Instalación

Requisitos:

- Python 3.11

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

### Ejecutar la app

```bash
python main.py
```

o:

```bash
streamlit run app/streamlit_app.py
```

### Flujo recomendado

1. elegir carpeta local de CIFs
2. reconstruir biblioteca SQLite
3. cargar difractograma experimental
4. ajustar preprocesamiento y detección de picos
5. ajustar tolerancia, prefilter y multifase
6. ejecutar search & match
7. revisar:
   - tabla de picos experimentales
   - ranking de candidatos
   - desglose de score
   - overlay experimental vs. picos teóricos
   - picos explicados y no explicados
   - combinaciones multifase simples

### Flujo COD recomendado

1. elegir carpeta para mirror local COD, por ejemplo `data/cod_mirror`
2. si tenés `svn`:

```bash
svn checkout svn://www.crystallography.net/cod data/cod_mirror
```

3. luego, dentro de la app:
   - usar `Sync incremental COD`
   - opcional: instalar o verificar `svn`
   - opcional: definir filtro químico y cantidad de workers
   - activar o no `Ejecutar sync remoto`
   - reindexar solo cambios

También se puede hacer por código:

```python
from core.models import LibraryBuildConfig
from services.indexing import sync_cod_library_incremental

report = sync_cod_library_incremental(
    sync_root="data/cod_mirror",
    database_path="data/reference_library.sqlite",
    config=LibraryBuildConfig(),
    method="svn",
    perform_remote_sync=True,
)
```

## Tests

Incluye tests mínimos para:

- construcción de biblioteca local
- sync incremental local estilo COD
- lectura de difractogramas
- extracción de fingerprint experimental
- matching controlado
- prefilter indexado

Ejecutar:

```bash
pytest
```

## Limitaciones actuales

- no hay profile fitting completo
- no hay refinamiento Rietveld
- multifase todavía es heurístico
- no hay deconvolución avanzada de picos
- no hay integración directa con COD remota
- no hay corrección instrumental sofisticada

## Próximos pasos razonables

- agregar caché parcial o descarga incremental desde COD
- mejorar scoring con términos de d-spacing y pesos por familia de picos
- sumar `ProfileMatcher`
- mejorar multifase con sustracción aproximada de contribuciones
- agregar filtros por química, sistema cristalino y metadatos
- preparar API o UI alternativa sin tocar núcleo científico

## Datos de ejemplo

- `data/examples/sample_experimental.xy`
- `data/examples/sample_experimental.csv`
- `data/cif_library/`

Con eso ya se puede reconstruir una biblioteca local y probar flujo completo.
