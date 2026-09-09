[English](README.md) · [Français](README.fr.md) · **Español** · [Versiones](CHANGELOG.es.md)

# ScanDeck

HUD de exploración y exobiología para **Elite Dangerous Odyssey**.

Lee los journals del juego en tiempo real y se queda encima del escritorio. Tras el honk y los escaneos, lista los cuerpos, las especies posibles, los datos de Universal Cartographics / Vista Genomics aún sin vender y el progreso de los rangos de explorador / exobiólogo.

El HUD está ahora en **inglés, francés y español**. Los nombres del juego (familias de bios, tipos de planeta, rangos) siguen al cliente de Elite cuando es posible. La mayoría de las familias Odyssey se quedan en latín; la excepción francesa conocida es **Tussock → Touradon**.

Es un overlay de acompañamiento, no un mod. No se inyecta en el cliente.

Notas de versión: [Español](CHANGELOG.es.md) · [English](CHANGELOG.md) · [Français](CHANGELOG.fr.md) · [Releases](https://github.com/jr-hub-dev/ScanDeck/releases)

## Requisitos

- Elite Dangerous **Odyssey**
- Journals activados (por defecto: `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`)
- **Zip de Windows:** nada más
- **Desde el código:** Python 3.11+ con Tk. `openpyxl` es opcional (hoja de cálculo)

## Instalación

### Windows (recomendado)

1. Descarga **ScanDeck-windows.zip** en [Releases](https://github.com/jr-hub-dev/ScanDeck/releases).
2. Descomprime **toda** la carpeta en algún sitio (Escritorio, Documentos, …).
3. Ejecuta `ScanDeck.exe` **desde esa carpeta**. No saques el exe solo.
4. Si aparece SmartScreen: **Más información → Ejecutar de todas formas**.

Arranca ScanDeck **antes o durante** la partida. Al iniciar relee journals recientes y luego sigue el log en directo.

### Linux / macOS / Windows con Python

```bash
git clone https://github.com/jr-hub-dev/ScanDeck.git
cd ScanDeck
pip install -r requirements.txt
python3 -m scandeck
```

En Windows con Python: `python -m scandeck`. En Linux también puedes usar `./scandeck.sh`.

```text
python3 -m scandeck --lang auto   # predeterminado: SO, luego el cliente Elite
python3 -m scandeck --lang en
python3 -m scandeck --lang fr
python3 -m scandeck --lang es
```

## Primer arranque

Si el HUD no encuentra los journals, pulsa **Opciones** (abajo a la izquierda):

- **Idioma** — Auto / English / Français / Español. Más idiomas de la interfaz se podrán añadir más adelante; la lista en Opciones crecerá.
- **Carpeta de journals** — déjala vacía para detectar automáticamente, o Examina hasta la carpeta que contiene los `Journal.*.log`

Ubicaciones habituales:

| Plataforma | Carpeta |
|---|---|
| Windows | `Saved Games\Frontier Developments\Elite Dangerous` en tu perfil de usuario |
| Steam / Proton | `~/.steam/steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
| Wine / Heroic | en el prefijo, la misma ruta `Saved Games\Frontier Developments\Elite Dangerous` |

Los ajustes se guardan en `Documents\ScanDeck\config.json` (Windows) o `~/.local/share/ScanDeck/config.json` (Linux). Cambiar el idioma o los journals reinicia el HUD.

`--journal-dir` y `ED_JOURNAL_DIR` tienen prioridad sobre Opciones.

## Cómo funciona

Juega con normalidad. ScanDeck solo escucha los journals.

En la exobiología de Odyssey, un **género** (en inglés *genus*, plural *genera*) es la **familia** del bio — Bacterium, Stratum, Tussock, etc. No significa «general». La **especie** es el organismo concreto (por ejemplo Bacterium Aurasus). Solo hay una especie por género en cada planeta.

1. **Honk (escaneo de descubrimiento FSS)** — los cuerpos aparecen a la **izquierda**. Las señales bio no van en el honk; escanea cada planeta en el FSS.
2. **FSS de un planeta** — tipo, señales, una primera estimación de valor. Etiquetas: **carto** si ya está mapeado, **FF** si ya hay footfall.
3. **DSS (escaneo detallado de superficie)** — revela esos **géneros** (las familias), no la especie exacta. El panel **derecho** lista las especies compatibles y un veredicto aterrizar / pasar.
4. **Aterrizar** — Genetic Sampler: Log → Sample → Analyse (1/3, 2/3, hecho). El Codex / Nomad puede identificar una especie antes de muestrear.
5. **Vender** — Universal Cartographics y Vista Genomics. **UC A LA VENTA** (izquierda) es cartografía sin vender; **VISTA A LA VENTA** (derecha) es bio sin vender. Se vacían al vender. Pasan a verde cuando lo acumulado cubre lo que falta para el siguiente rango.

### Disposición del HUD

| Zona | Qué ves |
|---|---|
| Lista izquierda | Cuerpos del sistema actual |
| Panel derecho | Planeta seleccionado: veredicto, géneros, especies, progreso de escaneos |
| Carril extremo izquierdo | Rango de explorador |
| Carril extremo derecho | Rango de exobiólogo |
| Pie | **Abrir la hoja**, **Opciones**, versión (`v1.0.5`). Si hay una Release de GitHub más nueva, aparece **ACTUALIZACIÓN v…** — un clic abre la página de descarga. |

Haz clic en un cuerpo a la izquierda para abrirlo a la derecha. Los botones de copia junto al sistema / cuerpo copian ese nombre.

Los veredictos son una pista para aterrizar (alto valor, opcional, pasar), no una garantía de que la especie esté ahí.

### Hoja de cálculo

**Abrir la hoja** escribe `scandeck.xlsx` junto a la config (Documents / ScanDeck en Windows). Una fila por planeta × género DSS, actualizada al muestrear. Hace falta `openpyxl` (incluido en el zip de Windows).

## Lo que ScanDeck no sabe

- Un planeta compatible **no** garantiza esa especie.
- El DSS confirma el **género** (la familia), no la especie, hasta que hablen el sampler o el Nomad.
- `ScanOrganic Log` es una identificación, no un muestreo terminado.
- Las reglas de aparición vienen de [SrvSurvey](https://github.com/njthomson/SrvSurvey) / [Canonn](https://canonn.science/codex/vista-genomics-price-list/) (observaciones), no de Frontier. Detalles: [`data/SOURCES.md`](data/SOURCES.md).
- Los valores de escaneo siguen tablas de la comunidad (cartografía estilo MattG / EDDI; precios Vista de Canonn). Bonus First Logged / First Footfall bio: ×5.
