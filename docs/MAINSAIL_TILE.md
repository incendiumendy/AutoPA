# Native Mainsail tile / Native Mainsail-Kachel

## Deutsch

AutoPA enthält eine native Mainsail-Kachel für die derzeit validierte
Mainsail-Version `2.18.2`. Sie wird von Mainsail wie ein eingebautes Panel
behandelt und kann deshalb unter **Einstellungen → Dashboard** für Mobil,
Tablet, Desktop und Widescreen:

- zwischen den verfügbaren Spalten verschoben werden;
- ein- oder ausgeblendet werden;
- auf dem Dashboard zu- und aufgeklappt werden.

Die Kachel zeigt:

- erreichbaren bzw. frischen AutoPA-Status;
- Dry-Run-, Aus- oder bewaffneten Zustand;
- relativen Düsendruck und aktuellen PA-Wert;
- ausgeführten Layer und G-Code-Feature;
- Klipper-Toolhead-Geschwindigkeit und Volumenstrom;
- ob das aktuelle PA-Messfenster freigegeben oder ignoriert wird.

Sie kann AutoPA öffnen und ausschließlich zwischen `off` und `dry_run`
umschalten. Sie kann **keinen bewaffneten Modus starten**, keine
Druckerbefehle freischalten und im bewaffneten Modus auch nicht die
Wiederherstellung umgehen. Das vollständige AutoPA-Sicherheitsmodell bleibt
maßgeblich.

### Warum ein eigener Build erforderlich ist

Mainsail unterstützt verschiebbare eingebaute Panels und Makrogruppen, stellt
aber keine stabile externe Plug-in-Schnittstelle für eine beliebige
Live-Vue-Kachel bereit. Eine Makrogruppe könnte keine AutoPA-Livewerte
darstellen. AutoPA erzeugt deshalb aus einem sauberen, festgelegten
Mainsail-Quellstand einen **separaten** Build. Der heruntergeladene
Originalquellcode wird nicht verändert.

### Lokal bauen

```powershell
git clone --depth 1 --branch v2.18.2 `
  https://github.com/mainsail-crew/mainsail.git `
  .reference/mainsail-v2.18.2

python scripts/mainsail_tile.py `
  .reference/mainsail-v2.18.2 `
  build/mainsail-autopa-v2.18.2-src

cd build/mainsail-autopa-v2.18.2-src
npm ci
npx vite build
```

Der fertige Webroot liegt anschließend unter `dist/`. Die Datei
`dist/autopa-integration.json` bestätigt Version, Panelname und die
`off_or_dry_run_only`-Richtlinie.

### Update- und RatOS-Grenze

Die Integration verändert weder das RatOS-Theme-Repository noch dessen
`navi.json`. Damit verursacht dieser Build nicht den früheren
„RatOS Theme: kompromittiert“-Hinweis. Er ersetzt später jedoch die
ausgelieferten Mainsail-Webdateien. Ein normales Mainsail-Update kann die
Kachel daher entfernen. Für jede neue Mainsail-Version muss zuerst die
Kompatibilität des Quellcodes geprüft, die unterstützte Version ausdrücklich
freigegeben und ein neuer Build erzeugt werden.

Die Installation auf dem Drucker bleibt blockiert, bis die bekannten
USB-/EXT4-Speicherfehler offline repariert und das Dateisystem geprüft wurden.

## English

AutoPA includes a native dashboard tile for the currently validated Mainsail
version `2.18.2`. Mainsail treats it like a built-in panel, so it can be moved
between columns, shown or hidden per device class, and collapsed on the
dashboard.

The tile displays AutoPA freshness, mode, relative nozzle load, PA, executed
layer and feature, Klipper toolhead speed, volumetric flow and PA evidence
window state. It can open AutoPA and switch only between `off` and `dry_run`.
It cannot arm runtime command application or bypass AutoPA's safety gates.

Mainsail has native sortable panels and macro groups but no stable external
plug-in API for an arbitrary live Vue panel. AutoPA therefore creates a
separate build from a clean, pinned upstream source tree. The upstream tree is
never modified.

The build intentionally does not modify the RatOS Theme repository or
`navi.json`. A later normal Mainsail update may overwrite the custom web
assets, so every new Mainsail release must be reviewed and explicitly added to
the compatibility list before rebuilding.

Printer installation remains blocked until the known USB/EXT4 storage faults
have been repaired offline and the filesystem has passed verification.
