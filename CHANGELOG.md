# Changelog / Änderungsprotokoll

## Unveröffentlicht / Unreleased

### Deutsch

- passiver Recorder-Manager im Dashboard, der sich an einen laufenden Druck
  anhängen und die synchronisierte Aufnahme am Druckende sauber stoppen kann;
- eigene Start-/Stop-Endpunkte ohne Drucker-G-Code sowie eine unabhängige
  Druckende-Überwachung mit zwölf Stunden Maximaldauer;
- eingeschränkter Schreibzugriff des gehärteten Dashboard-Dienstes nur auf
  `~/printer_data/autopa`.
- kompaktere native Mainsail-Kachel mit Temperatur, Bewegung, Düsendruck,
  einzeiligem G-Code-Kontext und sicherem Live-Aufnahme-Schalter;
- visuelle Ruhezonen sowie automatische Bewegungs-Skalierung mit Reserve und
  weich begrenzter Druckanzeige, ohne Rohdaten oder Regler-Evidenz zu verändern;
- geglättete Sensoranzeigen und weiche Marker-Übergänge, die ausschließlich die
  Darstellung betreffen;
- verifizierte und zweisprachig dokumentierte FLY-ALPS-Verbindung über den
  USB-Passthrough des EBB42 Gen2 einschließlich Stabilitätsprüfung und
  Rückfallweg;
- optionale, getrennt freigeschaltete Chamber-Filter-Regeln je Materialprofil
  mit Dateinamen-Kennung, validiertem `fan_generic`, Leistung, Nachlauf und
  Wiederherstellung nach einem Dienstneustart.

### English

- passive dashboard recorder manager that can attach to a running print and
  cleanly stop the synchronized capture when the print ends;
- dedicated start/stop endpoints with no printer G-code and an independent
  print-end monitor with a twelve-hour maximum duration;
- restricted write access for the hardened dashboard service, limited to
  `~/printer_data/autopa`.
- a more compact native Mainsail tile with temperature, motion, nozzle load,
  one-line G-code context and a safe live-capture switch;
- visual deadbands, reserved motion auto-ranging and softly saturated pressure
  indication without modifying raw samples or controller evidence;
- smoothed sensor readouts and fluid marker transitions that affect presentation
  only;
- validated bilingual documentation for connecting FLY-ALPS through the EBB42
  Gen2 USB passthrough, including stability checks and fallback guidance;
- optional, independently locked chamber-filter rules per material profile,
  with filename token, validated `fan_generic`, speed, post-run and recovery
  after a service restart.

## v0.1.0-alpha.1 - 2026-07-26

### Deutsch

Erste öffentliche Alpha-Version von AutoPA für Klipper und RatOS.

#### Enthalten

- synchronisierte Aufzeichnung der Düsenkraft eines Mellow FLY-ALPS und der
  realen Werkzeugkopfbewegung auf Klippers `print_time`-Zeitachse;
- optionale Bewegungsdaten von LIS2DW, LIS3DH, ADXL345 und MPU9250;
- Qualitätsprüfung, Mehrpunkt-Kalibrierung, PA-Sweeps, Material- und
  Temperaturvergleiche sowie beratende Filamentdruck-Erkennung;
- G-Code Context Engine für den tatsächlich ausgeführten Layer, Z-Wert,
  Feature-Typ und das Objekt;
- begrenzte adaptive PA- und Auto-Retract-Logik mit Dry-Run als Standard,
  getrennten Freigaben und automatischer Wiederherstellung;
- lokales Dashboard und native, verschiebbare AutoPA-Kachel für
  Mainsail `2.18.2`;
- optionaler, rein lesender LocalVision-Zustand in der AutoPA-Kachel;
- zweisprachige Dokumentation für RatOS und gewöhnliche
  Klipper/Moonraker-Installationen.

#### Bekannte Grenzen

- Die Datenerfassung und Zeitsynchronisierung wurden bisher auf einem
  RatOS-Drucker validiert.
- Adaptive PA-Änderungen und Auto-Retract sind noch nicht durch einen
  vollständigen Testdruck validiert. Zuerst ausschließlich Dry-Run verwenden.
- Die native Mainsail-Kachel ist an Mainsail `2.18.2` gebunden und muss für
  neuere Versionen erneut geprüft und gebaut werden.
- Fehlende, veraltete oder ungültige Sensordaten unterdrücken Regelaktionen;
  sie dürfen einen Druck nicht selbstständig abbrechen.

### English

First public alpha release of AutoPA for Klipper and RatOS.

#### Included

- synchronized acquisition of Mellow FLY-ALPS nozzle force and real toolhead
  motion on Klipper's `print_time` clock;
- optional motion data from LIS2DW, LIS3DH, ADXL345 and MPU9250;
- quality checks, multi-point calibration, PA sweeps, material and temperature
  comparisons, and advisory filament-pressure detection;
- a G-code Context Engine for the actually executed layer, Z height, feature
  type and object;
- bounded adaptive PA and Auto-Retract logic with dry-run by default,
  independent unlocks and automatic restoration;
- a local dashboard and native movable AutoPA tile for Mainsail `2.18.2`;
- optional read-only LocalVision health in the AutoPA tile;
- bilingual documentation for RatOS and regular Klipper/Moonraker systems.

#### Known limitations

- Acquisition and time synchronization have currently been validated on one
  RatOS printer.
- Adaptive PA changes and Auto-Retract have not yet been validated by a full
  test print. Use dry-run first.
- The native Mainsail tile is pinned to Mainsail `2.18.2` and must be reviewed
  and rebuilt for newer versions.
- Missing, stale or invalid sensor data suppresses control actions and must
  not abort a print by itself.
