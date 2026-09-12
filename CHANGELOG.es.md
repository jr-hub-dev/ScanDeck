[English](CHANGELOG.md) · [Français](CHANGELOG.fr.md) · **Español**

# Notas de versión

Qué ha cambiado para los jugadores. Zips de Windows: [Releases](https://github.com/jr-hub-dev/ScanDeck/releases).

El enlace de GitHub « Full Changelog » es un **diff de código**, no estas notas.

## 1.0.6 — 2026-09-12

### Añadido
- Fenómenos estelares notables: banda cian en la lista izquierda tras el honk; el nombre del Codex después de escanearlos
- Hoja **explo**: mundos similares a la Tierra, mundos acuáticos, mundos de amoníaco y fenómenos estelares (una fila por hallazgo)
- UC / Vista a la venta muestran **base** y **First logged** en una línea, más una línea **FC** (lo que queda tras tripulación + tasa del fleet carrier)

### Cambiado
- Los importes usan **Md** desde mil millones; cada uno pasa a verde por su cuenta cuando cubre el siguiente rango

## 1.0.5 — 2026-09-09

### Corregido
- Vender en Universal Cartographics actualiza el restante hasta el siguiente rango de explorador (antes se quedaba en el último % del journal)

## 1.0.4 — 2026-09-08

### Cambiado
- Las líneas sin vender se llaman **UC A LA VENTA** (cartografía, izquierda) y **VISTA A LA VENTA** (bio, derecha)

## 1.0.3 — 2026-09-08

### Añadido
- Icono de la app (planeta cian / anillos de escaneo) en el HUD, la barra de tareas y `ScanDeck.exe` en Windows

### Corregido
- Cierre al arrancar con Python 3.14 (`wm_class`)

## 1.0.2 — 2026-09-08

### Añadido
- Número de versión en el pie del HUD
- Si hay una Release más nueva, aparece **ACTUALIZACIÓN** al lado — un clic abre la página de descarga

## 1.0.1 — 2026-09-08

### Corregido
- `ScanDeck.exe` (Windows) se cerraba al instante al arrancar

## 1.0.0 — 2026-09-08

Primera versión pública.

### Añadido
- HUD: cuerpos tras el FSS, géneros (familias de bios) tras el DSS, especies posibles, veredicto aterrizar / pasar
- Progreso del Genetic Sampler, IDs Nomad, cartografía y Vista Genomics sin vender, carriles de rango explorador / exobiólogo
- Hoja opcional de muestras DSS
- Opciones: idioma (inglés, francés, español) y carpeta de journals
- Zip de Windows (sin Python) y ejecución desde el código
