# Native Mainsail tile / Native Mainsail-Kachel

## Deutsch

AutoPA enthält zwei native Mainsail-Kacheln für die derzeit validierte
Mainsail-Version `2.18.2`. Sie werden von Mainsail wie eingebaute Panels
behandelt und können deshalb unter **Einstellungen → Dashboard** für Mobil,
Tablet, Desktop und Widescreen:

- zwischen den verfügbaren Spalten verschoben werden;
- ein- oder ausgeblendet werden;
- auf dem Dashboard zu- und aufgeklappt werden.

Die Kachel zeigt:

- erreichbaren bzw. frischen AutoPA-Status;
- Dry-Run-, Aus- oder bewaffneten Zustand;
- Temperatur, schwerkraftbereinigte Bewegung und relativen Düsendruck als
  kompakte Hauptwerte;
- aktuellen PA-Wert, Layer, Feature, Toolhead-Geschwindigkeit und Volumenstrom
  in einer einzigen platzsparenden Kontextzeile;
- ob das aktuelle PA-Messfenster freigegeben oder ignoriert wird sowie die
  Messqualität;
- ausschließlich AutoPA-Zustand und AutoPA-Bedienelemente.

Local Vision besitzt eine eigene, unabhängig verschiebbare Kachel. Sie zeigt
den Dienst- und Kalibrierungsstatus sowie den read-only geprüften Fahrplan.
Ein Start erfordert den Bestätigungshaken in der Kachel und anschließend einen
zweiten Dialog mit Bettgröße, sicherer Z-Höhe und allen fünf Messpunkten. Erst
danach ruft sie die Local-Vision-Kalibrierung auf. Deren serverseitige Sperren
bleiben maßgeblich: nur Leerlauf, live gelesene Achsgrenzen, normales `G28`
ohne Heizen und Fortschrittsmeldungen in der Mainsail-Konsole.

Die passive Live-Aufnahme kann direkt mit **Live ein** bzw. **Live aus**
geschaltet werden. Sie sendet keinen G-Code und führt weder Pause noch Abbruch
aus. Die Anzeige verwendet bewusst eine Ruhezone: relativer Düsendruck
innerhalb `±10 %` wird als `≈ 0` dargestellt, Bewegungen unter `0,20 m/s²`
werden visuell auf null gesetzt. Rohdaten und AutoPA-Auswertung bleiben davon
unverändert. Die ausführliche AutoPA-Seite skaliert die Bewegungsanzeige anhand
der letzten 60 Sekunden mit 50 % Reserve; die Druckanzeige nähert sich ihren
Grenzen weich an. Dadurch ist für die reine Anzeige keine manuelle Eichung
nötig.

Die AutoPA-Kachel zeigt keinen Local-Vision-Zustand mehr. Dadurch sind beide
Werkzeuge sichtbar getrennt und es gibt keine doppelte Local-Vision-Anzeige.

Die Kachel enthält außerdem einen kompakten Kalibrierungs-Block für
Firmware-Rückzug (mm) und Pressure Advance (K). Beide Sweeps werden direkt
aus der Kachel an Moonraker gesendet, ohne G-Code-Datei. Sie erfordern die
Bestätigungsphrase, den Druckerzustand `standby` und das serverseitige
Opt-in-Flag; während eines Drucks ist der Block sichtbar gesperrt und der
Server lehnt zusätzlich ab. Der zum Laufbeginn aktive Rückzugs- bzw. PA-Wert
wird am Ende automatisch wiederhergestellt.

Das Düsendruck-Fenster zeigt den geglätteten relativen Düsendruck als
vertikalen Balken mit Nullpunkt in der Mitte (Druck nach oben, Zug nach
unten) und dem Prozentwert daneben. Die Anzeige nutzt einen exponentiellen
Mittelwert, damit Sensorrauschen im Leerlauf nicht ausschlägt; ohne
Live-Daten zeigt das Fenster „—“. Rohdaten und Auswertung bleiben unverändert.

Über ein kleines Dropdown im Kachelkopf lässt sich die Ansicht umschalten:
`Auto` folgt dem Druckerzustand, `Druck` blendet den Sweep-Block aus,
`Test` zeigt ihn prominent oben.

Sie kann AutoPA öffnen, die passive Aufnahme schalten und ausschließlich
zwischen `off` und `dry_run` umschalten. Sie kann **keinen bewaffneten Modus
starten**, keine
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

Der getrennte Build bringt außerdem die Seitenleisten-Links **AutoPA** und
**Local Vision** selbst mit und vermeidet dabei Duplikate. Dafür muss
`.theme/navi.json` nicht verändert werden.

Auf RatOS sollte der fertige Build in einem eigenen, versionierten Webroot
installiert werden, zum Beispiel unter
`~/mainsail-autopa/releases/<version>`. Ein Symlink
`~/mainsail-autopa/current` zeigt auf die aktive Version und Nginx verwendet
diesen Symlink als `root`. Vor der Umschaltung werden `config.json` und die
Nginx-Site gesichert; `nginx -t` muss erfolgreich sein. So bleibt
`~/mainsail` vollständig unter Kontrolle des normalen Mainsail-Updaters und
ein Rollback besteht nur aus dem Zurücksetzen des Symlinks bzw. Webroots.

Ein Mainsail-Update aktualisiert den getrennten AutoPA-Webroot nicht
automatisch. Nach jeder Mainsail-Aktualisierung muss deshalb ein kompatibler
AutoPA-Build erzeugt, getestet und bewusst aktiviert werden.

## English

AutoPA includes two native dashboard tiles for the currently validated Mainsail
version `2.18.2`. Mainsail treats them like built-in panels, so they can be moved
between columns, shown or hidden per device class, and collapsed on the
dashboard.

The tile displays temperature, gravity-free motion and relative nozzle load as
its compact primary values. PA, executed layer and feature, Klipper toolhead
speed and volumetric flow share one context line. It also reports PA evidence
window and measurement quality. A visual deadband reports relative pressure
inside `±10%` and motion below `0.20 m/s²` as approximately zero without
altering raw data or controller evidence. The detailed AutoPA page auto-ranges
motion from the latest 60-second peak with 50% headroom and softly saturates
the pressure marker. This avoids hard edge hits without requiring display
calibration.

Local Vision has its own independently movable tile with service and
calibration status plus the read-only checked motion plan. Starting requires a
checkbox and a second dialog listing bed size, safe Z and all five points. The
server still enforces idle state, live axis limits, plain `G28` without heating
and Mainsail-console progress messages. The AutoPA tile no longer contains any
Local Vision row.

The tile also contains a compact calibration block for firmware retraction (mm)
and pressure advance (K). Both sweeps are sent straight to Moonraker without a
G-code file. They require the confirmation phrase, the printer state `standby`
and the server-side opt-in flag; during a print the block is visibly locked and
the server refuses as well. The retraction or PA value active at run start is
restored automatically at the end.

The pressure cell shows the smoothed relative nozzle load as a vertical bar
centered on zero (load up, tension down) with the percentage beside it. An
exponential moving average keeps idle sensor noise from swinging the display;
without live data the cell shows “—”. Raw data and analysis stay unchanged.

A small dropdown in the tile header switches the view: `Auto` follows the
printer state, `Print` hides the sweep block, `Test` brings it to the top.
It cannot arm runtime command application or bypass AutoPA's safety gates.

Mainsail has native sortable panels and macro groups but no stable external
plug-in API for an arbitrary live Vue panel. AutoPA therefore creates a
separate build from a clean, pinned upstream source tree. The upstream tree is
never modified.

The build intentionally does not modify the RatOS Theme repository or
`navi.json`. A later normal Mainsail update may overwrite the custom web
assets, so every new Mainsail release must be reviewed and explicitly added to
the compatibility list before rebuilding.

The separate build also supplies the **AutoPA** and **Local Vision** sidebar
links itself and avoids duplicates, so `.theme/navi.json` does not need to be
modified.

On RatOS, install the build in a separate versioned webroot such as
`~/mainsail-autopa/releases/<version>`. Point
`~/mainsail-autopa/current` at the active release and configure Nginx to use
that symlink as its root. Back up `config.json` and the Nginx site first, and
require a successful `nginx -t` before reloading Nginx. This keeps
`~/mainsail` under the normal Mainsail updater and makes rollback a symlink or
webroot change.

A normal Mainsail update does not update the separate AutoPA webroot. Rebuild,
test and deliberately activate a compatible AutoPA build after every Mainsail
upgrade.
