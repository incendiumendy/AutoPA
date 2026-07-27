# Dateinamen-gesteuerter Chamber-Filter

[Deutsch](#deutsch) | [English](#english)

## Deutsch

AutoPA kann einen vorhandenen Klipper-`[fan_generic]` anhand einer eindeutigen
Kennung im G-Code-Dateinamen einschalten. Diese Funktion ist ein eigener
Controller und nicht Teil von Adaptive PA, Auto-Retract oder der passiven
Messaufnahme.

### Materialprofil

Jedes Materialprofil kann optional speichern:

- **Filter erforderlich**: Regel für dieses Material aktivieren;
- **Dateikennung**: literaler, nicht als regulärer Ausdruck interpretierter
  Text, zum Beispiel `[ABS]`, `[ASA]` oder `[FILTER]`;
- **Klipper-Lüfter**: Auswahl aus den wirklich vorhandenen
  `fan_generic`-Objekten;
- **Leistung**: 10 bis 100 Prozent;
- **Nachlauf**: 0 bis 120 Minuten.

Die Kennung wird ohne Beachtung der Groß-/Kleinschreibung im Basisnamen der
Druckdatei gesucht. Ein ABS-Profil mit `[ABS]` passt beispielsweise zu:

```text
halter_[ABS]_0.3mm.gcode
```

Eine Datei ohne die exakte Kennung aktiviert diese Regel nicht. Damit wird
vermieden, dass ein zufälliger Bestandteil eines Modellnamens einen Filter
einschaltet.

### Klipper-Befehl und getrennte Freigabe

Klipper stellt für `[fan_generic chamber_filter]` folgenden Befehl bereit:

```text
SET_FAN_SPEED FAN=chamber_filter SPEED=0.800
```

AutoPA akzeptiert nur Lüfternamen, die Klippers aktive Konfiguration tatsächlich
als `fan_generic` meldet, und Geschwindigkeiten von `0.1` bis `1.0`.

Die ausgelieferte systemd-Konfiguration setzt:

```text
AUTOPA_ALLOW_FILTER_COMMANDS=0
```

Damit können Profile und Treffer zunächst ohne Lüfteraktion geprüft werden.
Diese Freigabe ist unabhängig von `AUTOPA_ALLOW_PRINTER_COMMANDS`; sie erlaubt
ausschließlich validierte `SET_FAN_SPEED`-Befehle für den Chamber-Filter.

### Laufzeitverhalten

- Startet AutoPA während eines bereits laufenden Drucks, wird der aktuelle
  Dateiname ebenfalls geprüft.
- Bei `printing` und `paused` bleibt der passende Filter aktiv.
- Bei `complete`, `cancelled`, `error` oder `standby` beginnt der konfigurierte
  Nachlauf.
- Nach Ablauf wird nur der zuvor von AutoPA aktivierte Lüfter auf `0` gesetzt.
- Ein Moonraker- oder Controllerfehler pausiert oder beendet den Druck nicht.
- Bei einem Überwachungsfehler wird ein laufender Filter nicht vorschnell
  ausgeschaltet.
- Der aktive Zustand wird unter `/var/lib/autopa` gespeichert, damit ein
  Dienstneustart während oder kurz nach einem Druck wiederhergestellt werden
  kann.

### Gesundheitsschutz

Ein Umluftfilter ist keine Garantie für ungefährliche Raumluft und kein Ersatz
für geeignete Einhausung, Quellabsaugung oder Frischluft. NIOSH empfiehlt
technische Schutzmaßnahmen wie geeignete Lüftung und HEPA-Filtration sowie
emissionsärmere Materialien. Hinweise:

- [Klipper `fan_generic` und `SET_FAN_SPEED`](https://www.klipper3d.org/G-Codes.html#fan_generic)
- [NIOSH: Approaches to safe 3D printing](https://www.cdc.gov/niosh/docs/2024-103/default.html)
- [EPA: 3D printing research and emissions](https://www.epa.gov/chemical-research/3d-printing-research-epa)

## English

AutoPA can switch an existing Klipper `[fan_generic]` from an explicit token
in the G-code filename. This is an independent controller, separate from
Adaptive PA, Auto-Retract and passive data capture.

Each material profile can store whether filtration is required, a literal
case-insensitive filename token, a fan selected from Klipper's real
`fan_generic` objects, a speed from 10 to 100 percent and a post-run duration
from 0 to 120 minutes.

The shipped service keeps `AUTOPA_ALLOW_FILTER_COMMANDS=0`. Profiles and
filename matches can therefore be validated before any fan command is allowed.
This lock is independent from adaptive printer commands and permits only
validated `SET_FAN_SPEED` calls.

The controller also detects a print already in progress, keeps filtration
active while paused, starts post-run timing at terminal print states and
recovers its active state after a service restart. Monitoring failures never
pause or cancel a print and never turn an active filter off early.

A recirculating filter does not guarantee safe room air and does not replace
appropriate enclosure, source extraction or fresh-air ventilation. See the
official Klipper, NIOSH and EPA links in the German section above.
