# Changelog / Änderungsprotokoll

## Unveröffentlicht / Unreleased

### Deutsch

- überwachter Firmware-Rückzugs-Sweep (`retract_sweep`) mit markierten
  `G10`/Wartezeit/`G11`-Zyklen, Pflicht-`--restore-retract` und
  fail-closed-Auswertung (`retract_analyze`) nach Restdüsendruck und
  Wiederanfahrverhalten; das Auswertungs-Artefakt verändert den Drucker
  grundsätzlich nie selbst.

- Rückzugs-Sweep direkt aus dem Dashboard (Karte „Rückzugs-Sweep"): sendet
  den begrenzten Sweep per Moonraker an den Drucker, ganz ohne G-Code-Datei;
  erfordert die Bestätigungsphrase, den Druckerzustand `standby` und das
  Opt-in-Flag `AUTOPA_ALLOW_PRINTER_COMMANDS=1`; der Restore-Wert wird
  automatisch aus `firmware_retraction.retract_length` gelesen.

- Test-Sweep-Block in der nativen Mainsail-Kachel: Firmware-Rückzug (mm) und
  Pressure Advance (K) direkt aus der Kachel senden; neuer `pa_runner` mit
  den Endpunkten `/api/pa-sweep` und `/api/pa-sweep/run` nach denselben
  Sicherheitsregeln (Phrase, `standby`, Opt-in-Flag, automatische
  Wiederherstellung des aktiven Werts); sichtbare Sperre während eines Drucks
  in Kachel und Dashboard.

- Düsendruck-Fenster der Mainsail-Kachel als vertikaler Balken mit
  Nullpunkt-Mitte und Prozentwert, geglättet per exponentiellem Mittelwert
  gegen Sensorrauschen im Leerlauf; Ansichts-Dropdown im Kachelkopf
  (`Auto`/`Druck`/`Test`) für druck- bzw. testorientierte Darstellung.

- begrenzte Testposition und Druck-Prime für beide Kalibrier-Sweeps
  (`start_x`/`start_y` 0–500 mm, `start_z` 10–300 mm, `prime_e` 0–20 mm),
  einstellbar in der Mainsail-Kachel (Felder „Ziel-Z" und „Prime") und über
  die API; Ziel-Z hebt die Düse vor der Extrusion sicher an, sodass kein
  Auffangbehälter nötig ist — eine freie Fallzone genügt, eine einfache
  Auffangschale wird trotzdem empfohlen.

- begrenzte Auto-Übernahme der Sweep-Empfehlungen: Der Dienst nimmt den
  Sweep automatisch auf, wertet ihn aus und übernimmt den empfohlenen Wert
  nur zur Laufzeit (`SET_RETRACTION`/`SET_PRESSURE_ADVANCE`, niemals
  `SAVE_CONFIG`), wenn er innerhalb der einstellbaren Grenze liegt
  (Rückzug ±1,5 mm, PA ±0,09; hart begrenzt auf ±3,0 mm bzw. ±0,2); bei
  eindeutiger Auswertung, andernfalls wird der Grund in der Kachel gezeigt
  und nichts verändert.

- vollautomatischer Sweep-Loop im Dienst (Aufnahme → Zeitausrichtung →
  Qualitäts-Gate → Auswertung → begrenzte Übernahme) mit langem,
  sweepdeckendem Skript-Timeout; Homing-Vorabprüfung (X/Y/Z) vor jedem
  Sweep; der Z-Hub entfällt, wenn der Düsenabstand bereits ausreicht, und
  fährt sonst nur weg von der Düse; das Qualitäts-Gate wertet
  USB-Batch-Bursts (Ankunfts-RMS bis 25 ms, Lücken bis 25 ms) nicht mehr
  als Warnung, weil die Ausrichtung Ankunftszeiten durch ein gleichmäßiges
  Index-Raster ersetzt; die Bestätigungsphrase in der Mainsail-Kachel ist
  durch eine Bestätigungsbox mit Zusammenfassung ersetzt.

- Gateway-Timeout-Verständnis in der Mainsail-Kachel: Läuft die
  Sweep-Bestätigung in einen HTTP-504/Timeout, zeigt die Kachel einen
  erklärenden Hinweis statt des roten Statuscodes — der Sweep läuft
  serverseitig weiter und der Status aktualisiert sich automatisch;
  empfohlenes Proxy-Lese-Timeout von 300 s dokumentiert (nginx
  `proxy_read_timeout 300s;`); Prime-Standard der Kachel auf 10 mm erhöht.

- zweistufige Prime vor jedem Kalibrier-Sweep: Nach der Hauptextrusion und
  einer kurzen Pause baut eine langsame Nachfüll-Extrusion (25 % der Prime,
  1–4 mm, `prime_settle_e`) stabilen Düsendruck direkt vor dem ersten
  Messzyklus auf; das reduziert Messfehler durch Ooze nach dem Aufheizen
  (leere Schmelzkammer) bei beiden Sweeps.

- Fehlerbehebung: `GET /api/sweep` sendete nach der JSON-Antwort zusätzlich
  die statische `index.html` in dieselbe Verbindung (fehlendes `return`).
  Weil die Kachel nur `Content-Length` Bytes liest und dann schließt,
  erzeugte jede Abfrage einen `BrokenPipeError`-Traceback im Dienstprotokoll
  (rund 6.100 in vier Stunden auf dem validierten Drucker). Zusätzlich wird
  ein Verbindungsabbruch während einer Antwort jetzt allgemein abgefangen
  statt protokolliert.

- Fehlerbehebung: Die Ratenbegrenzung des adaptiven Reglers unterdrückte
  das erste Kommando auf einer gerade gestarteten Maschine.
  `last_command_at` und `last_retraction_query_at` waren mit `0.0`
  vorbelegt, `time.monotonic()` ist unter Linux aber die Zeit seit dem
  Systemstart — der Bootzeitpunkt wurde damit als echter, sehr junger
  Zeitstempel gelesen. Lief der Drucker weniger als
  `min_update_interval_s` (Standard 30 s), verwarf der Regler die erste
  Übernahme stillschweigend. Beide Werte nutzen jetzt `None` als
  Kennzeichen für „noch nicht geschehen".

- Messkurve je Stufe: Unter jeder Stufe steht jetzt die Kostenkurve über
  alle gemessenen Werte statt nur der empfohlenen Zahl. Der beste Wert ist
  hervorgehoben, Kandidaten ohne genügend verwertbare Zyklen bleiben als
  Lücke sichtbar. Liegt der beste Wert am Rand des gemessenen Bereichs,
  weist die Karte darauf hin — das Optimum kann dann außerhalb liegen und
  der Bereich sollte erweitert werden.

- Fehlerbehebung: Die Ergebniszeile zeigte bei Stufe 1 „Übernommen: ? →
  0.09 K". Die beiden Runner schreiben unterschiedliche Schlüssel
  (`previous`/`appliedValue` gegenüber `previousMm`/`appliedMm`); die
  Oberfläche kannte nur eine Schreibweise.

- `SAVE_CONFIG` ersetzt jetzt den Start-Button einer Stufe, sobald diese
  einen Wert übernommen hat, statt zusätzlich darunter zu stehen. Der
  Dialog stellt klar, dass Klipper dabei **alle** aktiven Werte schreibt,
  nicht nur den dieser Stufe.

- Der Sweep übernimmt eine laufende Live-Aufnahme jetzt selbst, statt den
  Start abzulehnen: Die Vorschau ist ein passiver Recorder, Starten und
  Stoppen senden keinen G-Code. Nach der Auswertung wird sie wieder
  eingeschaltet — auch dann, wenn der Sweep abgelehnt wurde. Eine an einen
  laufenden Druck gebundene Aufnahme wird nie angetastet.

- Während einer laufenden Auswertung lässt sich keine weitere Stufe starten,
  und die Karte zeigt „Daten werden ausgewertet …". Zuvor liefen die
  Pipelines überlappend: Eine Stufe las am Ende den *aktuellen*
  Datensatznamen und wertete damit die Messung der nächsten Stufe aus.

- Jede Stufe merkt sich den Datensatz, den sie selbst angelegt hat.

- Stufe 2 und Stufe 3 haben eigene Ergebnis-Slots. Sie teilen sich einen
  Runner; mit nur einem Slot löschte die spätere Stufe das Ergebnis der
  früheren und die Karte blieb leer.

- Ablehnungen von Klipper erreichen jetzt die Oberfläche. Ein `HTTPError`
  aus Moonraker beendete zuvor den Request-Thread, der Browser bekam eine
  leere Antwort und es war nicht erkennbar, warum nichts passierte. Kalte
  Düse und fehlendes Homing werden im Klartext erklärt.

- Klarere Statusmeldungen: „Am Drucker bleiben!" stand dort, wo das Ergebnis
  erscheint, und las sich wie eines. Ergebnisse unterscheiden jetzt sichtbar
  zwischen „noch nie gelaufen", „wird ausgewertet" und „fertig".

- Vorfüllen zwischen den Kandidatenwerten: Beide Sweeps füllen die Düse
  jetzt nicht nur vor dem ersten Zyklus, sondern auch zwischen je zwei
  Werten neu. Ohne das startet jeder Kandidat aus dem Zustand des vorigen —
  ein langer Rückzug leert die Kammer, der nächste Wert misst ins Leere und
  der Fehler schaukelt sich auf. Genau daran scheiterte ein Längen-Sweep ab
  0,6 mm mit `pressure_amplitude_below_3x_noise_mad`. Das Prime-Feld ist
  jetzt auch im Dashboard vorhanden (Standard 10 mm); zuvor sendete es
  immer 0.

- Ein Sweep läuft nicht mehr los, wenn er seine eigene Aufnahme nicht
  anlegen kann. Zuvor extrudierte er den kompletten Lauf und meldete erst
  danach `no_capture_dataset`. Eine laufende Live-Vorschau ist dabei kein
  Hindernis mehr — sie wird übernommen (siehe oben).

- Die Pipeline wertet nur noch Datensätze aus, die der Sweep selbst gestartet
  hat. Der Capture-Manager meldet nach dem Stoppen weiter den vorherigen
  Datensatznamen; ohne diese Prüfung hätte ein Sweep mit fehlgeschlagenem
  Recorder die Daten des vorherigen Laufs ausgewertet und dessen Empfehlung
  übernommen.

- Die Rückzugsanalyse weist Datensätze zurück, die einen Längen- und einen
  Geschwindigkeits-Sweep enthalten. Zuvor galt der erste Modus-Marker für den
  ganzen Datensatz — Geschwindigkeiten von 20–60 mm/s wären als Rückzugslängen
  gerankt worden.

- `SAVE_CONFIG` im Dashboard: einzeln bestätigte, ausdrücklich angeforderte
  Möglichkeit, die aktiven Laufzeitwerte dauerhaft zu schreiben. Nur im
  Standby, mit Bestätigungsdialog, der den Klipper-Neustart benennt. Die
  automatische Pipeline erreicht diesen Pfad nie.

- Ergebnis-Anzeige je Kalibrierstufe: Jede Stufe zeigt jetzt, was mit ihrer
  Empfehlung geschehen ist — übernommen (mit Vorher/Nachher und dem Hinweis,
  dass es nur zur Laufzeit gilt), abgelehnt samt Grund und Grenze, oder als
  Empfehlung zum selbst Eintragen. Die Stufen reichen ihre Werte über den
  Laufzeitzustand des Druckers weiter; ohne sichtbares Ergebnis misst Stufe 2
  gegen einen Pressure Advance, den niemand bestätigt hat. `lastApply` wurde
  von beiden Runnern schon geliefert, aber nirgends angezeigt.

- Das Ergebnis eines Geschwindigkeits-Sweeps wird nicht mehr als
  „kein Ergebnis" verworfen. Die Pipeline unterscheidet jetzt zwischen einer
  fehlenden Empfehlung und einer, die sie nicht selbst anwenden darf, und
  meldet die empfohlene Geschwindigkeit als Hinweis (`record_advisory`).

- Rückzugsgeschwindigkeits-Sweep: `retract_sweep` kann jetzt statt der Länge
  die Geschwindigkeit variieren und setzt dafür `RETRACT_SPEED` und
  `UNRETRACT_SPEED` gemeinsam (5–120 mm/s), mit Wiederherstellung beider
  Werte am Ende. Bisher wurde die Geschwindigkeit nie gesetzt — der
  Parameter diente ausschließlich der Laufzeitschätzung, obwohl die
  Materialzähigkeit sie zu einer der wichtigsten Größen macht.

- Die Auswertung meldet das Ergebnis eines Geschwindigkeits-Sweeps als
  `retract_speed_mm_s` statt als `retract_length_mm`. Dadurch greift die
  begrenzte Auto-Übernahme von selbst nicht mehr — sie sucht ausschließlich
  die Länge — und eine Geschwindigkeit kann konstruktionsbedingt nie als
  Länge an `SET_RETRACTION` gehen.

- Dashboard: Die Abstimmkarte führt jetzt als Assistent durch drei Stufen
  (Pressure Advance → Rückzugslänge → Rückzugsgeschwindigkeit) und stellt
  den Nachregler ans Ende. Die Reihenfolge folgt der Arbeit statt dem
  Druckerzustand: PA bestimmt, wie viel Druck beim Rückzug ansteht. Jede
  Stufe erklärt, was sie misst; die Karte ist ohne vorherige Doku
  verständlich. Der PA-Sweep ist damit erstmals auch im Dashboard verfügbar.

- Dashboard: „Rückzugs-Sweep" und „Adaptive PA & Auto-Retract" liegen jetzt
  in einer Karte, getrennt in Phase 1 (nur im laufenden Druck) und Phase 2
  (nur im Standby). Beide regeln dieselbe Größe in entgegengesetzten
  Druckerzuständen und konnten nie gleichzeitig aktiv sein; als zwei
  gleich aussehende Karten nebeneinander war das nicht erkennbar.

- Dashboard: die getippte Bestätigungsphrase „AUTOPA VALIDIEREN" ist durch
  einen Bestätigungsdialog ersetzt, der die konkreten Werte nennt — wie in
  der Mainsail-Kachel bereits üblich. Der serverseitige Phrasen-Gate in
  `/api/control/arm` und `/api/sweep/run` bleibt unverändert; die Phrase
  wird weiterhin gesendet, nur nicht mehr abgetippt.

- Mainsail-Farbbrücke im Dashboard: `dashboard/public/theme.js` liest die
  aktive Primärfarbe aus der Moonraker-Datenbank
  (`mainsail` / `uiSettings.primary`) und setzt `--primary`,
  `--primary-rgb` und `--primary-ink`. Marken- und Bedienflächen
  (Markenzeichen, Primärschaltflächen, Profil-Schaltfläche, Umschalter,
  Hintergrundschimmer) folgen jetzt dieser Farbe; Statusfarben bleiben
  bewusst fest, damit eine frei gewählte Primärfarbe niemals einen
  Warn- wie einen OK-Zustand aussehen lässt. Ist Moonraker nicht
  erreichbar, gilt weiterhin der RatOS-Standard `#99f321`. Das Skript lag
  zuvor ungenutzt im Build und wurde von keiner Seite geladen.

- Zugriffsprotokoll des Dashboards wird sofort geschrieben (`flush=True`).
  Da systemd die Standardausgabe über eine Pipe einliest, puffert Python
  blockweise; die Zeilen erreichten das Journal dadurch erst Minuten später
  in Schüben, während Tracebacks über stderr sofort ankamen.

- eigenständige, verschiebbare Local-Vision-Kachel in Mainsail mit sicher
  bestätigter automatischer Kamerakalibrierung; die frühere
  Local-Vision-Zeile wurde vollständig aus der AutoPA-Kachel entfernt;
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
- doppelte Düsendruck-Detailkarte aus dem AutoPA-Dashboard entfernt; der
  Messwert erscheint nur noch in der primären FLY-ALPS-Karte;
- optionale, getrennt freigeschaltete Chamber-Filter-Regeln je Materialprofil
  mit Dateinamen-Kennung, validiertem `fan_generic`, Leistung, Nachlauf und
  Wiederherstellung nach einem Dienstneustart.

### English

- supervised firmware-retraction sweep (`retract_sweep`) with marked
  `G10`/dwell/`G11` cycles, mandatory `--restore-retract` and
  fail-closed analysis (`retract_analyze`) ranking residual nozzle
  pressure and restart behavior; the analysis artifact itself never
  modifies the printer.

- dashboard-driven retraction sweep ("Rückzugs-Sweep" card): sends the
  bounded sweep through Moonraker without any G-code file; requires the
  confirmation phrase, the printer state `standby` and the opt-in flag
  `AUTOPA_ALLOW_PRINTER_COMMANDS=1`; the restore value is read
  automatically from `firmware_retraction.retract_length`.

- test-sweep block in the native Mainsail tile: send firmware-retraction (mm)
  and pressure-advance (K) sweeps directly from the tile; new `pa_runner`
  with `/api/pa-sweep` and `/api/pa-sweep/run` endpoints under the same
  safety rules (phrase, `standby`, opt-in flag, automatic restore of the
  active value); visible lock during a print in both the tile and the
  dashboard.

- pressure cell of the Mainsail tile as a vertical zero-centered bar with
  percentage readout, smoothed by an exponential moving average against idle
  sensor noise; view dropdown in the tile header (`Auto`/`Print`/`Test`) for
  print- or test-focused layouts.

- bounded test position and print prime for both calibration sweeps
  (`start_x`/`start_y` 0–500 mm, `start_z` 10–300 mm, `prime_e` 0–20 mm),
  configurable in the Mainsail tile ("target Z" and "prime" fields) and via
  the API; target Z safely raises the nozzle before extrusion, so no purge
  bin is required — a clear drop zone is sufficient, though a simple catch
  tray is still recommended.

- bounded auto-apply of sweep recommendations: the service automatically
  captures the sweep, analyzes it, and applies the recommended value at
  runtime only (`SET_RETRACTION`/`SET_PRESSURE_ADVANCE`, never
  `SAVE_CONFIG`) when it stays within the configurable limit (retraction
  ±1.5 mm, PA ±0.09; hard-capped at ±3.0 mm and ±0.2); only on a conclusive
  analysis — otherwise the tile shows the reason and nothing changes.

- fully automatic sweep loop in the service (capture → time alignment →
  quality gate → analysis → bounded apply) with a long script timeout
  covering the whole sweep; homing pre-check (X/Y/Z) before every sweep;
  the Z lift is skipped when the nozzle gap is already sufficient and
  otherwise only moves away from the nozzle; the quality gate no longer
  treats USB bulk batching (arrival RMS up to 25 ms, gaps up to 25 ms) as
  a warning because alignment replaces arrival times with a uniform
  sample-index grid; the confirmation phrase in the Mainsail tile was
  replaced by a confirmation box with a run summary.

- gateway-timeout awareness in the Mainsail tile: when the sweep
  acknowledgement runs into an HTTP 504/timeout, the tile shows an
  explanatory note instead of the raw status code — the sweep keeps
  running server-side and the status refreshes automatically; a recommended
  300 s proxy read timeout is documented (nginx `proxy_read_timeout 300s;`);
  the tile's prime default was raised to 10 mm.

- two-stage prime before every calibration sweep: after the main extrusion
  and a short dwell, a slow settle extrusion (25 % of the prime, 1–4 mm,
  `prime_settle_e`) rebuilds stable nozzle pressure right before the first
  measured cycle; this reduces measurement errors caused by ooze after
  heat-up (empty melt chamber) in both sweeps.

- bug fix: `GET /api/sweep` appended the static `index.html` to its JSON
  response on the same connection (a missing `return`). Because the tile
  reads only `Content-Length` bytes and then closes, every poll produced a
  `BrokenPipeError` traceback in the service log (about 6,100 in four hours
  on the validated printer). A client disconnect during a response is now
  also caught generally instead of being logged.

- bug fix: the adaptive controller's rate limiter suppressed the first
  command on a machine that had just started. `last_command_at` and
  `last_retraction_query_at` were seeded with `0.0`, but `time.monotonic()`
  is seconds since boot on Linux, so boot time was read as a real and very
  recent timestamp. While the printer had been up for less than
  `min_update_interval_s` (30 s by default) the controller silently
  discarded the first apply. Both now use `None` to mean "has not happened
  yet".

- per-stage cost curve: each stage now shows the cost across all measured
  values instead of only the recommended number. The best value is
  highlighted and candidates without enough usable cycles stay visible as
  gaps. When the best value sits at the edge of the measured range the card
  says so - the optimum may lie outside it and the range should be widened.

- bug fix: the result line showed "Übernommen: ? → 0.09 K" for stage 1. The
  two runners write different keys (`previous`/`appliedValue` versus
  `previousMm`/`appliedMm`) and the interface only knew one spelling.

- `SAVE_CONFIG` now replaces a stage's start button once that stage applied a
  value, instead of sitting below it as a second action. The dialog states
  that Klipper writes **all** active values, not just this stage's.

- a sweep now takes over a running live capture instead of refusing to
  start: the preview is a passive recorder and starting or stopping it sends
  no G-code. It is switched back on after the analysis, including when the
  sweep was rejected. A capture bound to a running print is never touched.

- no second stage can start while an analysis is running, and the card shows
  "Daten werden ausgewertet …". The pipelines used to overlap: a stage read
  the *current* dataset name at the end and analyzed the next stage's
  measurement with it.

- each stage now remembers the dataset it created itself.

- stage 2 and stage 3 have their own result slots. They share one runner, so
  a single slot let the later stage erase the earlier one's result and the
  card went blank.

- Klipper's rejections now reach the interface. An `HTTPError` from Moonraker
  killed the request thread, the browser saw an empty reply and there was no
  way to tell why nothing happened. A cold nozzle and missing homing are
  explained in plain language.

- clearer status messages: "Am Drucker bleiben!" sat where the result
  appears and read like one. Results now visibly distinguish never-run,
  analyzing and finished.

- reprime between candidates: both sweeps now refill the nozzle not only
  before the first cycle but between every pair of values. Without it each
  candidate starts from whatever the previous one left behind - a long
  retraction empties the chamber, the next value measures into a void and the
  error compounds. That is exactly how a length sweep lost everything from
  0.6 mm upwards to `pressure_amplitude_below_3x_noise_mad`. The prime field
  now exists in the dashboard too (default 10 mm); it previously always sent
  zero.

- a sweep no longer starts when it cannot create its own recording. It used
  to extrude through the whole run and only then report
  `no_capture_dataset`. A running live preview is no longer an obstacle - it
  is taken over instead (see above).

- the pipeline only analyzes datasets the sweep started itself. The capture
  manager keeps reporting the previous dataset name after a stop, so without
  this check a sweep whose recorder failed to start would have analyzed the
  previous run's data and applied its recommendation.

- the retraction analysis rejects datasets holding both a length and a speed
  sweep. The first mode marker used to apply to the whole dataset, so speeds
  of 20-60 mm/s would have been ranked as retract lengths.

- `SAVE_CONFIG` in the dashboard: a separately confirmed, explicitly
  requested way to persist the active runtime values. Standby only, behind a
  dialog naming the Klipper restart. The automatic pipeline never reaches it.

- per-stage result line: every calibration stage now shows what happened to
  its recommendation - applied, with before/after and the note that it only
  holds at runtime; refused, with the reason and the bound; or reported for
  manual entry. The stages hand their values to each other through the
  printer's runtime state, so without a visible result stage 2 measures
  against a pressure advance nobody confirmed. `lastApply` was already served
  by both runners but displayed nowhere.

- a retraction-speed result is no longer discarded as "no recommendation".
  The pipeline now separates a missing recommendation from one it may not
  apply itself, and reports the recommended speed as an advisory
  (`record_advisory`).

- retraction-speed sweep: `retract_sweep` can now vary the speed instead of
  the length, setting `RETRACT_SPEED` and `UNRETRACT_SPEED` together
  (5-120 mm/s) and restoring both at the end. The speed was previously never
  set at all - the parameter only fed the duration estimate - even though
  material viscosity makes it one of the most important variables.

- the analysis reports a speed sweep's winner as `retract_speed_mm_s` rather
  than `retract_length_mm`. The bounded auto-apply path looks up the length
  key only, so it now fails closed by construction and a speed can never be
  sent to `SET_RETRACTION RETRACT_LENGTH`.

- dashboard: the tuning card now guides through three stages (pressure
  advance -> retract length -> retract speed) and places the in-print
  controller last. The order follows the work rather than the printer state,
  because PA decides how much pressure stands in the nozzle when a retraction
  starts. Each stage explains what it measures, so the card is usable without
  reading the docs first, and the PA sweep is available in the dashboard for
  the first time.

- dashboard: "Rückzugs-Sweep" and "Adaptive PA & Auto-Retract" now share one
  card, split into phase 1 (only while printing) and phase 2 (only in
  standby). Both tune the same quantity in opposite printer states and could
  never be active at the same time, which was impossible to tell from two
  identical-looking cards side by side.

- dashboard: the typed confirmation phrase "AUTOPA VALIDIEREN" is replaced by
  a confirmation dialog naming the concrete values, matching what the Mainsail
  tile already did. The server-side phrase gate on `/api/control/arm` and
  `/api/sweep/run` is unchanged; the phrase is still sent, just no longer
  retyped.

- Mainsail colour bridge in the dashboard: `dashboard/public/theme.js`
  reads the active primary colour from the Moonraker database
  (`mainsail` / `uiSettings.primary`) and sets `--primary`,
  `--primary-rgb` and `--primary-ink`. Brand and interactive surfaces
  (brand mark, primary buttons, add-profile button, toggles, background
  glow) now follow that colour; status colours stay fixed on purpose so a
  freely chosen primary can never make a warning look like an ok state.
  When Moonraker is unreachable the RatOS default `#99f321` still applies.
  The script previously sat unused in the build and was loaded by nothing.

- the dashboard access log is now flushed immediately (`flush=True`).
  systemd reads standard output through a pipe, so Python block-buffers it
  and the lines only reached the journal minutes later in bursts, while
  tracebacks on stderr arrived at once.

- separate movable Local Vision tile in Mainsail with explicitly confirmed
  automatic camera calibration; the former Local Vision row was completely
  removed from the AutoPA tile;
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
- removed the duplicate nozzle-load detail card so the value appears only in
  the primary FLY-ALPS card;
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
