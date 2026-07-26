# Changelog / Änderungsprotokoll

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
