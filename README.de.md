# AutoPA für Mellow FLY-ALPS und Klipper

[English](README.md) | [Deutsch](README.de.md) | [Änderungsprotokoll](CHANGELOG.md)

AutoPA zeichnet die Düsenkraft eines Mellow FLY-ALPS zusammen mit der realen
Werkzeugkopfbeschleunigung eines LIS2DW auf einem EBB42 Gen2 auf. Beide
Datenströme werden über Klippers `print_time`-Zeitbasis synchronisiert und für
überwachte, sensorgestützte Pressure-Advance-Messungen verwendet.

![AutoPA-Dashboard mit Drucker-, Sensor- und Messstatus](docs/images/autopa-dashboard.png)

Das optionale lokale Dashboard zeigt Düsenkraft, Bewegung, Temperatur,
Pressure Advance, Messqualität sowie bearbeitbare Testprofile für
PLA/ABS/PETG/ASA/TPU. Gegenüber dem Drucker bleibt es absichtlich nur lesend.
Der Düsendruck wird relativ zum gelernten Nullpunkt auf einer
`− / 0 / +`-Skala dargestellt. Die Bewegungsanzeige trennt die
schwerkraftbereinigte X/Y-Richtung und Z-Auslenkung.
Weitere Informationen stehen in der
[Dashboard-Dokumentation](docs/DASHBOARD.md).

Der passive Recorder-Manager kann Live-Daten per Klick auch im Standby
einschalten, sich an einen bereits laufenden oder später beginnenden Druck
anhängen, ohne offenen Browser weiterlaufen und die synchronisierte
ALPS-/Bewegungsaufnahme am Druckende sauber stoppen. Beim Ein- oder Ausschalten
dieser Messung wird kein G-Code an den Drucker gesendet.

Materialprofile können außerdem einen getrennt gesperrten, über den Dateinamen
ausgelösten Klipper-Chamber-Filter mit auswählbarem `fan_generic`, Leistung und
Nachlaufzeit definieren. Siehe
[Chamber-Filter-Dokumentation](docs/CHAMBER_FILTER.md).

AutoPA unterstützt gewöhnliche Klipper/Moonraker-Installationen und RatOS. Es
ersetzt keine RatOS-Konfigurationsdateien.

> Status: experimentelles Entwicklungsprojekt. Aufnahme und Zeitsynchronisation
> wurden auf einem RatOS-Drucker validiert. Automatische PA-Empfehlungen sind
> noch nicht vollständig validiert und dürfen nicht unbeaufsichtigt übernommen
> werden.

## Validierte Hardware

- Rat Rig V-Core 3 300 mit RatOS
- Mellow FLY-ALPS Firmware `2.0.0`, USB über einen stabilen/aktiven Hub
- BTT EBB42 Gen2 über USB
- LIS2DW des EBB42 als `lis2dw toolboard_t0`
- digitales ALPS-Probe-Signal an EBB42 PA5 (Enable) und PA4 (Trigger)

## Empfohlene Architektur

```text
Raspberry Pi / RatOS oder Klipper
|- USB-Hub -> Mellow FLY-ALPS mit Werksfirmware
|             |- USB-CDC-Kraftdatenstrom (~2,6 kHz)
|             `- digitales Trigger-Signal bleibt mit dem EBB42 verbunden
`- USB -> EBB42 Gen2
              |- normale Toolboard-Funktionen
              `- LIS2DW-Beschleunigungsdaten (~386 Hz)
```

Das EBB42 ist ein USB-Gerät und kein USB-Host oder Hub. Das ALPS benötigt daher
eine eigene USB-Verbindung zum Raspberry Pi oder zu einem guten aktiven Hub.
Eine passive USB-Verbindung vom ALPS zum USB-Anschluss des EBB42 darf nicht
gecrimpt werden.

Die direkte ALPS-Pi-Verbindung war am validierten Drucker instabil. Ein USB-Hub
stellte den zuverlässigen Betrieb wieder her. Siehe
[USB-Stabilität](docs/USB_STABILITY.md).

## Warum das ALPS nicht geflasht wird

Die öffentliche Mellow-Werksfirmware liefert Kraftmesswerte über USB, während
der digitale Probe-Ausgang weiter funktioniert. Das wurde vor und nach einer
gemeinsamen ALPS/LIS2DW-Aufnahme geprüft.

Klipper auf das ALPS zu flashen würde das Verhalten des digitalen Probe-Ausgangs
entfernen. Dieser Pfad bleibt deshalb nur als experimentelle Referenz unter
`firmware/`, `backport/` und `config/ALPS-load-cell.cfg.example` erhalten. Er
darf erst verwendet werden, wenn ein vollständiger und unabhängig geprüfter
`load_cell_probe`-Ersatz oder ein anderer Z-Probe vorhanden ist.

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
| maximaler Restfehler | 0,0021 ms |
| abgeleitete synchronisierte Zeilen | 3.853 |
| digitaler Probe-Status | unverändert |

Ein zweiter Lauf über fünf Sekunden bestätigte den kompletten Markerpfad:

- 12.986 Kraft- und 1.944 Beschleunigungsmesswerte
- keine Fehler oder Überläufe
- ein `AUTOPA_MARK`-Ereignis in `events.csv`
- maximaler Restfehler der Zeitanpassung 0,00035 ms
- Klipper blieb bereit/Standby und der Probe-Status unverändert

Rohdaten des Druckers und lokale Sicherungen werden absichtlich nicht in Git
gespeichert.

## Projektstruktur

```text
src/autopa/
  alps_serial.py     Leser für das Mellow-USB-Protokoll
  sync_recorder.py   gemeinsame ALPS-/Beschleunigungsmessung
  align.py           Zuordnung monotone Zeit zu Klipper print_time
  diagnose.py        bewegungsfreie Live- und Sicherheitsprüfung
  calibration.py     maschinenspezifische Mehrpunktkalibrierung
  filament.py        beratende Erkennung von Druckverlust/Filamentfehlern
  material.py        Filamentkonsistenz und Temperaturvergleich
  temperature_plan.py sichere Testdateien je Temperatur
  dashboard.py       lokaler Nur-Lese-Status- und Webserver
  quality.py         Aufnahme- und Leerlaufdiagnose
  sweep.py           begrenzter Klipper-PA-Testgenerator
klipper/extras/
  autopa_clock.py    Zeitbasis, exakte Marker und Sicherheitsprüfung
config/
  autopa.cfg         minimale Klipper-Einbindung
docs/                Installation, Protokoll, Kompatibilität und Sicherheit
tests/               Unit-Tests ohne externe Abhängigkeiten
dashboard/           responsive Weboberfläche und statischer Build
```

## Sicheren Werksfirmware-Modus installieren

Für diesen Modus wird auf Klipper-Seite nur
`klipper/extras/autopa_clock.py` benötigt. Die Erweiterung:

- meldet die Zuordnung von Linux-Monotonic-Zeit zu Klipper `print_time`
- zeichnet exakte `AUTOPA_MARK`-Grenzen auf
- prüft mit `AUTOPA_VALIDATE` Homing, Z-Abstand, X-Verfahrweg und die
  Extrusionsbereitschaft des Hotends
- kann Soll- und Isttemperatur innerhalb einer Toleranz prüfen

Sie liest oder verändert den Probe nicht, bewegt keine Achse, verändert PA
nicht und flasht keinen Mikrocontroller. Siehe
[Installation des Werksfirmware-Modus](docs/INSTALL_FACTORY_MODE.md).

Nach Änderungen an einer bereits importierten Klipper-Python-Erweiterung ist
ein echter Neustart des Klipper-Dienstes nötig. Ein G-Code-`RESTART` lädt die
Konfiguration neu, behält aber importierte Python-Module im selben Prozess.

## Aufzeichnen und synchronisieren

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

Der Recorder speichert Rohkraft, Beschleunigung, Batch-Diagnose, Zeitpaare,
G-Code-Ereignisse und ein Manifest. Synchronisierung und Qualitätsanalyse
erstellen neue abgeleitete Dateien und verändern niemals die Rohdaten.

Der Bewegungskanal ist optional. AutoPA unterstützt LIS2DW, LIS3DH, ADXL345 und
MPU9250; `--accelerometer-type none` aktiviert eine reine Kraftmessung. Siehe
[optionale Beschleunigungssensoren](docs/ACCELEROMETERS.md).

Mehrere akzeptierte Läufe können gemeinsam analysiert werden:

```sh
PYTHONPATH=src python3 -m autopa.analyze \
  ~/printer_data/autopa/<datensatz-1> \
  ~/printer_data/autopa/<datensatz-2> \
  --output ~/printer_data/autopa/combined-analysis.json
```

Jeder PA-Wert benötigt weiterhin mindestens drei akzeptierte Zyklen. Das
Ergebnis bleibt experimentell und setzt `apply_automatically` immer auf
`false`.

Andere ALPS-Boards und Hotend-Mechaniken können eine optionale
Mehrpunktkalibrierung für Offset, Polarität und Counts-Kraft-Umrechnung
verwenden. PA-Metriken bleiben auch ohne diese Kalibrierung lokal normiert.
Siehe [maschinenspezifische Kalibrierung](docs/CALIBRATION.md).

## Überwachten Smoke-Test erzeugen

Zuerst muss der aktuelle PA-Wert aus Klipper ausgelesen werden. Er wird als
`--restore-advance` benötigt, damit die Datei den Ausgangswert wiederherstellt.

```sh
PYTHONPATH=src python3 -m autopa.sweep \
  --k-start 0.01 \
  --k-stop 0.05 \
  --k-step 0.02 \
  --cycles 3 \
  --restore-advance 0.03 \
  --output autopa-smoke.gcode
```

Vor jedem Test:

- X/Y/Z homen
- Düse mindestens 10 mm über dem Bett frei positionieren
- Filament auf eine sichere Extrusionstemperatur bringen
- Auffangbehälter unter die Düse stellen
- freien +X-Verfahrweg prüfen
- beim Drucker bleiben und Not-Aus bereithalten
- Recorder vor der G-Code-Datei starten

`AUTOPA_VALIDATE` lehnt den Test ab, wenn Achsen nicht gehomt sind, Z zu niedrig
ist, die X-Bewegung den Achsbereich überschreiten würde oder das Hotend zu kalt
ist.

## Überwachten Rückzugs-Sweep erzeugen

`retract_sweep` variiert die Rückzugslänge von Klippers
`[firmware_retraction]` über markierte `G10`/Wartezeit/`G11`-Zyklen.
`retract_analyze` bewertet die Werte anhand des Restdüsendrucks und
des Wiederanfahrverhaltens. Der aktuelle Rückzugswert ist als
`--restore-retract` Pflicht, damit die Datei ihn am Ende wiederherstellt:

```sh
PYTHONPATH=src python3 -m autopa.retract_sweep \r
  --r-start 0.2 \r
  --r-stop 1.4 \r
  --r-step 0.2 \r
  --cycles 5 \r
  --restore-retract 0.8 \r
  --output autopa-retract-smoke.gcode
```

Die Empfehlung ist fail-closed, experimentell und wird niemals
automatisch übernommen. Siehe
[Rückzugs-Sweep-Dokumentation](docs/RETRACT_SWEEP.md).

## Sicherheitsgrenzen

- Normales Drucken ist Fail-open: Recorder- oder Sensorfehler pausieren oder
  beenden keinen Druck.
- Die Analyse ist Fail-closed: fehlende, verspätete, abgeschnittene oder
  unplausible Daten unterdrücken eine PA-Empfehlung.
- AutoPA verändert PA niemals automatisch.
- Eine Empfehlung enthält Konfidenz und Nachweise pro Zyklus.
- Die Übernahme bleibt eine separate, vom Benutzer bestätigte Aktion.
- Normales Z-Probing verwendet weiterhin das digitale ALPS-Werkssignal.
- `TEST_RESONANCES` läuft nicht während des Drucks; LIS2DW wird nur passiv
  aufgezeichnet.
- Ein AutoPA-Update darf RatOS, Klipper, Moonraker oder MCU-Firmware nicht
  aktualisieren.

Die vollständigen Regeln stehen unter
[Fail-open-Drucken](docs/FAIL_OPEN.md).

AutoPA kann außerdem befohlene Extrusion und gemessenen Düsendruck vergleichen.
Ein anhaltender Druckabfall kann auf gerissenes, leeres oder durchrutschendes
Filament hinweisen, bleibt aber ohne zusätzlichen Schalter oder Encoder nur
beratend. Siehe
[Filament-Druckverlust-Erkennung](docs/FILAMENT_MONITOR.md).

Temperaturabhängiges PA-Verhalten lässt sich über mindestens drei stabile
Testtemperaturen vergleichen. Das Ergebnis ist ein experimentelles,
sensorbasiertes Prozessfenster und ersetzt keine Prüfung von Stringing,
Materialabbau oder Schichthaftung. Siehe
[Material- und Temperaturcharakterisierung](docs/MATERIAL_TEMPERATURE.md).

## Inspiration und Quellenangaben

AutoPA ist eine unabhängige Implementierung mit eigener Git-Historie und **kein
Fork** von PrusaPATuner, KAPAT, Klipper oder RatOS. Die experimentelle Richtung
wurde von
[CNCKitchen/PrusaPATuner](https://github.com/CNCKitchen/PrusaPATuner) und
[vzagranichnyy/KAPAT](https://github.com/vzagranichnyy/KAPAT) inspiriert. Deren
Quelldateien sind nicht Bestandteil von AutoPA.

PrusaPATuner inspirierte die Load-Cell-basierte PA-Forschung und
Analysemethoden; KAPAT dient als Inspiration und Vergleich für einen
Klipper/Mellow-ALPS-Aufbau. AutoPA verwendet eine eigene Implementierung für
Befehle, Zeitbasis, Erfassung und Analyse.

Unter `backport/klipper/` liegen GPLv3-lizenzierte,
von Klipper abgeleitete Backport-Dateien mit beibehaltenen
Copyright-Hinweisen. Der genaue Umfang steht in den
[Drittanbieter-Hinweisen](THIRD_PARTY_NOTICES.md).

- [Mellow FLY-ALPS Webtool](https://mellow.klipper.cn/en/docs/ToolsDoc/fly-alps-tool/)
- [Klipper Pressure Advance](https://www.klipper3d.org/Pressure_Advance.html)
- [Klipper Resonanzmessung und LIS2DW](https://www.klipper3d.org/Measuring_Resonances.html)
- [Klipper G-Code-Referenz](https://www.klipper3d.org/G-Codes.html)
- [KAPAT Klipper-Experiment](https://github.com/vzagranichnyy/KAPAT)
- [FLY-ALPS-/ADS131M02-Entwicklungsthread](https://klipper.discourse.group/t/strain-gauge-load-cell-based-endstops/2134/622)
