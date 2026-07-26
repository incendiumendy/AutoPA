# G-Code Context Engine / G-Code-Kontext-Engine

## Deutsch

Die Context Engine verbindet den semantischen Inhalt einer Slicer-Datei mit
der tatsächlich ausgeführten Klipper-Zeitachse. Dadurch kennt AutoPA nicht nur
die momentane Extruderbewegung, sondern auch Layer, Z-Höhe, Druckfeature und
Objekt.

### Sicherer Ablauf

Das Original wird niemals verändert. Der lokale Befehl erzeugt eine neue
G-Code-Datei und eine JSON-Prüfdatei:

```sh
PYTHONPATH=src python3 -m autopa.gcode_context \
  original.gcode original.autopa.gcode
```

Ohne `--force` wird auch eine vorhandene Ausgabedatei nicht überschrieben.
Eingabe und Ausgabe dürfen niemals dieselbe Datei sein. Die JSON-Prüfdatei
enthält SHA-256-Prüfsummen, Markeranzahl, erkannte Layer, Features und Objekte.

Die Engine versteht derzeit verbreitete Kommentare von PrusaSlicer,
OrcaSlicer, SuperSlicer und Cura, unter anderem:

- `;LAYER_CHANGE`, `;LAYER:<n>`, `;Z:<höhe>`;
- `;TYPE:External perimeter`, `;TYPE:WALL-OUTER` und ähnliche Feature-Namen;
- `EXCLUDE_OBJECT_START NAME=...` und `EXCLUDE_OBJECT_END`.

Sie fügt nur vor der ersten Bewegung nach einem Kontextwechsel einen kompakten
`AUTOPA_MARK EVENT=context ...` ein. Der Klipper-Zusatz versieht diesen Marker
beim Einreihen mit `toolhead.get_last_move_time()`. AutoPA aktiviert den neuen
Kontext erst, wenn diese `print_time` tatsächlich erreicht ist. Ein Marker,
der nur im Look-ahead liegt, zählt daher noch nicht.

### PA-Messfenster

Für die erste Dry-Run-Version gelten Außenwand, Innenwand, Infill, massives
Infill und Lückenfüllung als auswertbare PA-Fenster. Support, Brücken,
Skirt/Brim, Glätten und unbekannte Features werden angezeigt, aber nicht für
eine PA-Änderung verwendet. Positive Extrusion, Temperatur, Sensoralter,
Abtastrate und Beschleunigungsqualität bleiben zusätzliche Pflichtbedingungen.

Fehlende oder ungültige Context-Marker sind **fail-open für den Druck** und
**fail-closed für AutoPA**: Der Druck läuft weiter, aber die kontextabhängige
PA-Auswertung und jede daraus abgeleitete Änderung werden unterdrückt. Die
Engine sendet selbst weder Pause noch Abbruch, Bewegung, Heizerbefehl oder
`SAVE_CONFIG`.

Das Dashboard zeigt den ausgeführten Layer, Z, Feature, Objekt, die aus
Klippers Toolhead-`trapq` rekonstruierte Druckgeschwindigkeit, die zeitgleiche
Filamentgeschwindigkeit aus der Extruder-`trapq`, den daraus berechneten
Volumenstrom sowie den Status des PA-Messfensters.

## English

The Context Engine joins slicer semantics with Klipper's actually executed
timeline. AutoPA therefore knows the current layer, Z height, print feature and
object in addition to the reconstructed extruder motion.

The command above always creates a separate instrumented G-code file plus a
JSON verification sidecar. It refuses to overwrite the source and, unless
`--force` is given, refuses to replace an existing output.

Only one compact `AUTOPA_MARK EVENT=context ...` is inserted before the first
move following a semantic context change. Klipper assigns
`toolhead.get_last_move_time()` when the marker enters the motion queue. AutoPA
does not activate the transition until its `print_time` has actually been
reached, so a future look-ahead marker cannot mislabel current sensor samples.

The initial dry-run allows PA evidence from external/internal perimeters,
infill, solid infill and gap fill. Support, bridges, skirt/brim, ironing and
unknown features remain visible but are excluded from PA decisions.

Missing or invalid context is **fail-open for printing** and **fail-closed for
AutoPA**: printing continues, while context-assisted PA evaluation and any
derived runtime change are suppressed. The engine never pauses or cancels a
print and never sends movement, heater or `SAVE_CONFIG` commands.

## Current boundary

This is an offline/local implementation and has not yet been deployed to the
printer. Keep it in dry-run until storage integrity is restored and a
supervised synthetic-file test has passed on the target Klipper installation.
