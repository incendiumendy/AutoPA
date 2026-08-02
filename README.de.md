# AutoPA für Mellow FLY-ALPS und Klipper

[English](README.md) | [Deutsch](README.de.md) | [Änderungsprotokoll](CHANGELOG.md)

[![tests](https://github.com/incendiumendy/AutoPA/actions/workflows/tests.yml/badge.svg)](https://github.com/incendiumendy/AutoPA/actions/workflows/tests.yml)

AutoPA zeichnet den Düsendruck eines Mellow FLY-ALPS gemeinsam mit der echten
Werkzeugkopfbeschleunigung des LIS2DW auf einem EBB42 Gen2 auf. Beide
Datenströme werden auf Klippers `print_time`-Zeitachse ausgerichtet und dienen
als Grundlage für beaufsichtigte, sensorgestützte Pressure-Advance-Sweeps.

![AutoPA-Dashboard mit Drucker-, Sensor- und Messstatus](docs/images/autopa-dashboard.png)

Ein optionales lokales Dashboard zeigt Düsendruck, Bewegung, Temperatur,
Pressure Advance, Messqualität und bearbeitbare Testprofile für PLA, ABS,
PETG, ASA und TPU in Echtzeit. Sein experimenteller Regler startet
grundsätzlich als kommandofreier Dry-Run und benötigt zwei voneinander
unabhängige Freigaben, bevor er begrenzte Änderungen zur Laufzeit vornehmen
darf. Der Düsendruck erscheint relativ zum gelernten Basiswert auf einer
vorzeichenbehafteten `− / 0 / +`-Skala; die Bewegungsanzeige trennt die
schwerkraftbereinigte X/Y-Richtung von der Z-Auslenkung. Siehe
[lokales Live-Dashboard](docs/DASHBOARD.md).

Der passive Recorder-Manager schaltet Live-Daten im Leerlauf per Klick ein,
hängt sich an einen bereits laufenden oder erst später startenden Druck an,
läuft ohne geöffneten Browser weiter und beendet die synchronisierte
ALPS-/Bewegungsaufnahme sauber am Druckende. Das Starten und Stoppen dieser
Messung sendet keinerlei G-Code an den Drucker.

Materialprofile können zusätzlich eine eigenständig gesperrte, über den
Dateinamen ausgelöste Klipper-Kammerfilterregel definieren, mit wählbarem
`fan_generic`, Leistung und Nachlaufzeit. Siehe
[Kammerfilter-Dokumentation](docs/CHAMBER_FILTER.md).

Das Projekt richtet sich sowohl an gewöhnliche Klipper/Moonraker-Installationen
als auch an RatOS. Es ersetzt keine RatOS-Konfigurationsdateien.

> Status: experimentelles Entwicklungsprojekt. Erfassung und Zeitausrichtung
> sind auf einem RatOS-Drucker validiert. Adaptive PA und Auto-Retract sind
> noch **nicht** im Druck validiert und müssen zuerst im Dry-Run bewertet
> werden. Niemals unbeaufsichtigt anwenden.

## Validierte Hardware

- Rat Rig V-Core 3 300 mit RatOS
- Mellow FLY-ALPS Firmware `2.0.0`, USB über die validierte
  EBB42-Gen2-Durchleitung oder einen aktiven, stabilen Hub
- BTT EBB42 Gen2 über USB
- LIS2DW des EBB42 als `lis2dw toolboard_t0`
- vorhandener digitaler ALPS-Taster an den EBB42-Pins PA5 (Enable) und
  PA4 (Trigger)

## Bevorzugte Architektur

```text
Raspberry Pi / RatOS oder Klipper
`- stabile USB-Anbindung -> EBB USB Adapter -> EBB42 Gen2 (USB-Modus)
   |- normale Toolboard-Funktionen und LIS2DW-Beschleunigung
   `- USB-Durchleitung -> Mellow FLY-ALPS mit Werksfirmware
      |- USB-CDC-Kraftdatenstrom
      `- digitaler Trigger bleibt mit dem EBB42 verbunden
```

Die Durchleitung des EBB42 **Gen2** folgt dem gewählten Kommunikationsmodus und
kann die ALPS-USB-Verbindung mitführen, solange das Board im USB-Modus läuft.
Genau dieser Pfad wurde mit stabilen EBB42- und ALPS-Geräte-IDs, laufender
AutoPA-Erfassung und einer zehnminütigen Abbruchüberwachung validiert. Das ist
keine allgemeine Aussage über ältere EBB-Revisionen. Siehe die zweisprachige
[Anleitung zur EBB42-Gen2-USB-Durchleitung](docs/EBB42_GEN2_USB_PASSTHROUGH.md).

Die direkte Verbindung vom ALPS zum Pi war auf der validierten Maschine
instabil. Ein USB-Hub stellte den zuverlässigen Betrieb wieder her; der später
geprüfte Weg über die EBB42-Gen2-Durchleitung war ebenfalls stabil. Siehe
[USB-Stabilität](docs/USB_STABILITY.md).

## Warum das ALPS nicht geflasht wird

Die öffentliche Mellow-Firmware liefert Kraftmesswerte über USB, während ihr
digitaler Tasterausgang weiterhin funktioniert. Das wurde vor und nach einer
kombinierten zehnsekündigen ALPS-/LIS2DW-Aufnahme überprüft.

Klipper auf das ALPS zu flashen würde das Werksverhalten des digitalen Tasters
entfernen. Dieser Weg bleibt deshalb ausschließlich als experimentelle Referenz
unter `firmware/`, `backport/` und `config/ALPS-load-cell.cfg.example`
erhalten. Er darf erst genutzt werden, wenn ein vollständiger und unabhängig
validierter Ersatz für `load_cell_probe` oder ein anderer Z-Taster vorliegt.

## Aktuell validiertes Ergebnis

Der erste kombinierte Leerlaufdatensatz ergab:

| Prüfung | Ergebnis |
| --- | ---: |
| ALPS-Firmware | 2.0.0 |
| ALPS-Kraftmesswerte | 25.970 in 10 s |
| ALPS-Abtastrate | 2.596,98 Hz |
| LIS2DW-Beschleunigungswerte | 3.880 in etwa 10 s |
| LIS2DW-Abtastrate | 385,87 Hz |
| LIS2DW-Fehler / Überläufe | 0 / 0 |
| RMS-Restfehler der Zeitanpassung | 0,0011 ms |
| maximaler Restfehler der Zeitanpassung | 0,0021 ms |
| abgeleitete ausgerichtete Zeilen | 3.853 |
| Zustand des digitalen Tasters | unverändert |

Ein zweiter Lauf über fünf Sekunden bestätigte den vollständigen Markerpfad:

- 12.986 Kraft- und 1.944 Beschleunigungsmesswerte;
- null Fehler und null Überläufe;
- ein in `events.csv` erhaltenes `AUTOPA_MARK`-Ereignis;
- maximaler Restfehler der Zeitanpassung 0,00035 ms;
- Klipper blieb im Zustand ready/standby, der Tasterzustand unverändert.

Rohdatensätze der Maschine und Druckersicherungen bleiben bewusst außerhalb
von Git.

## Aufbau des Repositorys

```text
src/autopa/
  alps_serial.py     Leser für das Mellow-USB-Protokoll
  sync_recorder.py   gleichzeitige ALPS-/LIS2DW-Aufnahme
  align.py           Zuordnung von monotoner Zeit zu Klippers print_time
  diagnose.py        bewegungslose Live- und Sicherheitsprüfungen
  calibration.py     maschinenspezifische Mehrpunkt-Kraftkalibrierung
  filament.py        Hinweis auf verlorenen Extrusionsdruck
  material.py        Filamentkonsistenz und Temperaturvergleich
  temperature_plan.py sichere Sweep-Dateien je Temperatur
  dashboard.py       lokaler Status- und Regelserver mit Opt-in-Grenzen
  adaptive.py        Dry-Run-Schätzer und abgesicherter PA-/Rückzugsregler
  gcode_context.py   sicherer Slicer-Kontextparser und Kopie-Instrumentierung
  quality.py         Erfassungs- und Leerlaufdiagnose
  sweep.py           Generator für begrenzte Klipper-PA-Sweeps
klipper/extras/
  autopa_clock.py    Zeitendpunkt, exakte G-Code-Marker und Sicherheitsprüfung
config/
  autopa.cfg         minimale Klipper-Einbindung
docs/                Installation, Protokoll, Kompatibilität, Sicherheit
tests/               Unit-Tests ohne externe Abhängigkeiten
dashboard/           responsive Weboberfläche und statischer Produktionsbuild
integrations/mainsail  native, verschiebbare AutoPA- und Local-Vision-Kacheln
```

## Sicheren Werksfirmware-Modus installieren

Auf Klipper-Seite wird für diesen Modus einzig
`klipper/extras/autopa_clock.py` benötigt. Die Erweiterung

- meldet die Zuordnung zwischen Linux-Monotonic- und Klipper-`print_time`;
- zeichnet exakte `AUTOPA_MARK`-Grenzen auf;
- stellt `AUTOPA_VALIDATE` bereit, um Homing, Z-Abstand, X-Verfahrweg und die
  Extrusionsbereitschaft des Hotends zu prüfen;
- vergleicht auf Wunsch die angeforderte Düsentemperatur und den Messwert
  innerhalb einer konfigurierten Toleranz mit dem temperaturgebundenen Sweep.

Sie liest oder verändert den Taster nicht, bewegt keine Achse, ändert PA nicht
und flasht keinen Mikrocontroller. Siehe
[Installation des Werksfirmware-Modus](docs/INSTALL_FACTORY_MODE.md).

Nach Änderungen an einer bereits importierten Klipper-Python-Erweiterung ist
ein echter Neustart des Klipper-Dienstes nötig. Ein G-Code-`RESTART` lädt zwar
die Konfiguration neu, behält importierte Python-Module aber im selben Prozess
im Cache.

## Aufzeichnen und ausrichten

Auf dem Raspberry Pi:

```sh
cd ~/printer_data/autopa-project
PYTHONPATH=src python3 -m autopa.sync_recorder \
  --alps-device /dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_DEINE_ID-if00 \
  --accelerometer-type lis2dw \
  --accelerometer toolboard_t0 \
  --duration 10 \
  --name idle_10s

PYTHONPATH=src python3 -m autopa.align \
  ~/printer_data/autopa/<datensatz>

PYTHONPATH=src python3 -m autopa.quality \
  ~/printer_data/autopa/<datensatz>

PYTHONPATH=src python3 -m autopa.analyze \
  ~/printer_data/autopa/<datensatz>
```

Der Recorder schreibt Rohwerte der Kraft und Beschleunigung, Batch-Diagnosen,
Zeitpaare, G-Code-Ereignisse und ein Manifest. Ausrichtung und Qualitätsanalyse
erzeugen neue abgeleitete Dateien und überschreiben die Rohdaten niemals.

Der Bewegungskanal ist optional. AutoPA unterstützt Klippers Datenendpunkte
für LIS2DW, LIS3DH, ADXL345 und MPU9250; `--accelerometer-type none` erlaubt
eine reine Kraftaufnahme. Siehe
[optionale Beschleunigungssensoren](docs/ACCELEROMETERS.md).

## Exakten G-Code-Kontext ergänzen

AutoPA kann eine getrennte, instrumentierte Kopie einer gewöhnlichen gesliceten
Datei erzeugen:

```sh
PYTHONPATH=src python3 -m autopa.gcode_context \
  model.gcode model.autopa.gcode
```

Die Quelldatei wird dabei nie verändert. Die Kontextmarker benennen die
gerade ausgeführte Schicht, die Z-Höhe, das Slicer-Feature und das Objekt auf
Klippers echter `print_time`-Achse, statt sich auf Moonrakers durch Look-ahead
verfälschte Dateiposition zu verlassen. Fehlender oder nicht unterstützter
Kontext unterbricht niemals einen Druck; er unterdrückt stattdessen die
kontextgestützte PA-Auswertung. Siehe die zweisprachige
[Anleitung zur G-Code-Kontext-Engine](docs/GCODE_CONTEXT.md).

Für Mainsail `2.18.2` liefert AutoPA außerdem getrennte native Kacheln für
AutoPA und Local Vision, die sich mit Mainsails normalen
Dashboard-Einstellungen verschieben, ausblenden und einklappen lassen. Die
AutoPA-Kachel zeigt ausschließlich kompakte Live- und Kontextdaten. Die
Local-Vision-Kachel bietet die beaufsichtigte Kamerakalibrierung hinter einer
eigenen Checkbox, einem Bestätigungsdialog und serverseitigen
Bewegungssperren. Siehe [native Mainsail-Kacheln](docs/MAINSAIL_TILE.md).

Mehrere qualitätsgeprüfte Läufe lassen sich zusammenfassen, ohne verworfene
Daten aufzunehmen:

```sh
PYTHONPATH=src python3 -m autopa.analyze \
  ~/printer_data/autopa/<datensatz-1> \
  ~/printer_data/autopa/<datensatz-2> \
  --output ~/printer_data/autopa/combined-analysis.json
```

Jeder PA-Wert benötigt weiterhin mindestens drei einbezogene Zyklen. Das
Ergebnis bleibt experimentell und setzt `apply_automatically` immer auf
`false`.

Abweichende ALPS-Boards und Hotend-Mechaniken können eine optionale
Mehrpunktkalibrierung für Offset, Polarität und die Umrechnung von Counts in
Kraft nutzen. Die PA-Kennwerte bleiben auch ohne sie lokal normiert. Siehe
[maschinenspezifische Kalibrierung](docs/CALIBRATION.md).

## Beaufsichtigten Smoke-Sweep erzeugen

Zuerst den aktuellen PA-Wert aus Klipper auslesen. Er ist als
`--restore-advance` verpflichtend, damit die erzeugte Datei diesen Wert am Ende
wiederherstellt.

```sh
PYTHONPATH=src python3 -m autopa.sweep \
  --k-start 0.01 \
  --k-stop 0.05 \
  --k-step 0.02 \
  --cycles 3 \
  --restore-advance 0.03 \
  --output autopa-smoke.gcode
```

Das Beispiel unterstellt, dass der Drucker aktuell auf `0.03` steht; ersetze
`--restore-advance` immer durch den Wert, den dein eigener Drucker meldet. Der
Lauf verbraucht 25,2 mm Filament und dauert etwa 11,25 Sekunden, ohne
Beschleunigungs- und Befehlsaufwand. Jeder Zyklus

1. fährt X um +8 mm in einer Sekunde und extrudiert dabei langsam;
2. fährt X in 0,25 Sekunden um −8 mm zurück und extrudiert dabei schnell;
3. endet exakt auf der X-Startkoordinate.

Der X-Anteil ist erforderlich, weil die validierte Klipper-Version Pressure
Advance nur bei positiver Extrusion mit gleichzeitiger X- oder Y-Bewegung
aktiviert. Außerdem liefert er dem LIS2DW ein echtes Bewegungssignal, um
mechanische Artefakte verwerfen zu können.

Vor jedem Sweep:

- X/Y/Z homen;
- die Düse frei in der Luft positionieren, mindestens 10 mm über dem Bett;
- das eingelegte Filament auf eine sichere Extrusionstemperatur bringen;
- einen Auffangbehälter unter der Düse platzieren;
- prüfen, dass der angeforderte +X-Verfahrweg innerhalb des Bauraums bleibt;
- am Drucker bleiben und den Not-Aus griffbereit halten;
- den Recorder starten, bevor der erzeugte G-Code ausgeführt wird.

`AUTOPA_VALIDATE` weist die Datei ab, wenn Achsen nicht gehomt sind, Z zu
niedrig steht, die +X-Bewegung die Achsgrenze überschreiten würde oder das
Hotend zu kalt ist.

## Beaufsichtigten Rückzugs-Sweep erzeugen

`retract_sweep` variiert die Rückzugslängen von Klippers
`[firmware_retraction]` über markierte `G10`/Wartezeit/`G11`-Zyklen, und
`retract_analyze` bewertet sie nach verbleibendem Düsendruck und
Wiederanfahrverhalten. Die aktuelle Rückzugslänge ist als `--restore-retract`
verpflichtend, damit die Datei sie am Ende wiederherstellt:

```sh
PYTHONPATH=src python3 -m autopa.retract_sweep \
  --r-start 0.2 \
  --r-stop 1.4 \
  --r-step 0.2 \
  --cycles 5 \
  --restore-retract 0.8 \
  --output autopa-retract-smoke.gcode
```

Die Empfehlung ist fail-closed, experimentell und wird niemals automatisch
übernommen. Siehe
[beaufsichtigter Firmware-Rückzugs-Sweep](docs/RETRACT_SWEEP.md).

## Projektgrenzen

- Normales Drucken ist fail-open: Aufnahme- oder Sensorfehler pausieren,
  brechen oder stoppen niemals einen Druck.
- Die Auswertung ist fail-closed: fehlende, verspätete, übersteuerte oder
  unplausible Daten unterdrücken die PA-Empfehlung.
- Auch die kontextgestützte PA ist fail-closed: Nur ein zulässiger
  Feature-Marker, dessen Klipper-`print_time` bereits erreicht ist, darf ein
  PA-Nachweisfenster öffnen.
- Aufnahme und Dry-Run verändern PA und Rückzug nie.
- Jede Übernahme gilt nur zur Laufzeit, und AutoPA schreibt die
  Druckerkonfiguration nie. Klippers `SAVE_CONFIG` kann Pressure Advance und
  Firmware-Rückzug ohnehin nicht sichern: In den Autosave-Block gelangt nur,
  was ein Modul über `configfile.set()` anmeldet — weder `extruder.py` noch
  `firmware_retraction.py` tut das. Das Dashboard zeigt stattdessen die
  Konfigurationszeilen zum Eintragen.
- Die Auswertung liefert zunächst eine Empfehlung mit Konfidenz und Nachweisen
  je Zyklus.
- Die experimentelle Übernahme im laufenden Betrieb wird separat freigegeben,
  ist nur vorübergehend scharfgeschaltet, ratenbegrenzt, in der Gesamtabweichung
  begrenzt und wird beim Entschärfen oder nach dem Druck auf die
  Ausgangswerte der Laufzeit zurückgesetzt.
- Auto-Retract wirkt ausschließlich auf Klippers `[firmware_retraction]` sowie
  auf gesliceten `G10`/`G11`; rohe Extruder-Rückzugsbewegungen in einer
  gewöhnlichen G-Code-Datei kann es nicht umschreiben.
- Normales Tasten läuft weiterhin über das digitale ALPS-Werkssignal.
- `TEST_RESONANCES` wird während des Drucks nicht ausgeführt; AutoPA zeichnet
  LIS2DW-Werte nur passiv auf.
- Ein Projektupdate darf ausschließlich AutoPA-Dateien und den eigenen Dienst
  aktualisieren. RatOS, Klipper, Moonraker und MCU-Firmware sind
  ausgenommen.

Die vollständigen Regeln und die aktuellen Qualitätsschwellen stehen unter
[Fail-open-Drucken](docs/FAIL_OPEN.md).
Das Validierungsverfahren und die harten Regelgrenzen sind unter
[Adaptive PA und Auto-Retract](docs/ADAPTIVE_CONTROL.md) dokumentiert.

AutoPA kann außerdem die von Klipper befohlene Extrusion mit dem gemessenen
Düsendruck vergleichen. Ein anhaltender Druckeinbruch kann auf gerissenes,
leeres oder durchrutschendes Filament hindeuten, bleibt aber ein Hinweis und
kann die genaue Ursache ohne zusätzlichen Filamentschalter oder
Bewegungsencoder nicht bestimmen. Siehe
[Erkennung von Filament-Druckverlust](docs/FILAMENT_MONITOR.md).

Temperaturabhängiges PA-Verhalten lässt sich über mindestens drei stabile
Testtemperaturen vergleichen. Das Ergebnis ist ein experimentelles,
sensorbasiertes Prozessfenster und ersetzt keine Prüfung auf Stringing,
thermischen Abbau und Schichthaftung. Siehe
[Material- und Temperaturcharakterisierung](docs/MATERIAL_TEMPERATURE.md).

## Quellen und Danksagung

AutoPA ist eine eigenständige Implementierung mit eigener Git-Historie. Es ist
**kein Fork** von PrusaPATuner, KAPAT, Klipper oder RatOS. Die experimentelle
Ausrichtung ist von
[CNCKitchen/PrusaPATuner](https://github.com/CNCKitchen/PrusaPATuner) und
[vzagranichnyy/KAPAT](https://github.com/vzagranichnyy/KAPAT) inspiriert; deren
Quelldateien sind in AutoPA nicht enthalten.

Testform und geplante Auswertung vergleichen Sprungantwort, Phasenverzug und
Integralfläche — angeregt durch die Load-Cell-basierte PA-Forschung in
PrusaPATuner und das Klipper/Mellow-ALPS-Experiment in KAPAT. PrusaPATuner
zielt auf die Buddy-Firmware, während KAPAT einen Klipper-spezifischen Weg
zeigt. AutoPA verwendet eigene Befehle, eine eigene Zeitbasis sowie eine eigene
Erfassung und Auswertung.

Die Dateien unter `backport/klipper/` enthalten GPLv3-lizenziertes, von Klipper
abgeleitetes Backport-Material mit den beibehaltenen
Urheberrechtsvermerken. Der genaue Umfang und die Links stehen in den
[Drittanbieter-Hinweisen](THIRD_PARTY_NOTICES.md).

- [Mellow FLY-ALPS Webtool](https://mellow.klipper.cn/en/docs/ToolsDoc/fly-alps-tool/)
- [Klipper Pressure Advance](https://www.klipper3d.org/Pressure_Advance.html)
- [Klipper Resonanzmessung und LIS2DW](https://www.klipper3d.org/Measuring_Resonances.html)
- [Klipper G-Code-Referenz](https://www.klipper3d.org/G-Codes.html)
- [KAPAT Klipper-Experiment](https://github.com/vzagranichnyy/KAPAT)
- [FLY-ALPS-/ADS131M02-Entwicklungsthread](https://klipper.discourse.group/t/strain-gauge-load-cell-based-endstops/2134/622)
