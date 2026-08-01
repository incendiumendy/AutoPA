import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("renders the finished AutoPA dashboard", async () => {
  const html = await readFile(
    new URL("../dist/client/index.html", import.meta.url),
    "utf8",
  );
  assert.match(html, /<html lang="de">/i);
  assert.match(html, /<title>AutoPA Live Dashboard<\/title>/i);
  assert.match(html, /Alles im gr(?:ü|\\u00fc)nen Bereich|Verbindung pr(?:ü|\\u00fc)fen/i);
  assert.match(html, /Materialprofil/i);
  assert.match(html, /Düsenprofil|D\\u00fcsenprofil/i);
  assert.match(html, /Heizbett/i);
  assert.match(html, /Geschwindigkeit/i);
  assert.match(html, /Düsendruck|D\\u00fcsendruck/i);
  assert.match(html, /Keine automatische Druckaktion/i);
  assert.match(html, /Zurück zu Mainsail|Zur\\u00fcck zu Mainsail/i);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("wires the Mainsail theme bridge into the rendered page", async () => {
  const html = await readFile(
    new URL("../dist/client/index.html", import.meta.url),
    "utf8",
  );
  const script = await readFile(
    new URL("../dist/client/theme.js", import.meta.url),
    "utf8",
  );
  const css = await readFile(
    new URL("../app/globals.css", import.meta.url),
    "utf8",
  );

  // The bridge shipped unreferenced for a while, so assert the whole chain:
  // the page loads it, it reads the Mainsail key, and the variables it sets
  // are the ones the stylesheet actually consumes.
  assert.match(html, /<script[^>]+src="\/theme\.js"/);
  assert.match(script, /uiSettings\.primary/);
  for (const variable of ["--primary", "--primary-rgb", "--primary-ink"]) {
    assert.match(script, new RegExp(`"${variable}"`));
    assert.match(css, new RegExp(`${variable}:`));
  }
  assert.match(css, /var\(--primary\)/);
  assert.match(css, /rgba\(var\(--primary-rgb\)/);

  // Status colours must not follow a user-chosen primary: a red Mainsail
  // theme must never make an ok or live state look like a warning.
  assert.match(css, /\.state-ok\s*\{\s*color:\s*var\(--green\)/);
  assert.match(css, /\.live-indicator\.is-live\s*\{\s*color:\s*var\(--green\)/);
});

test("confirms arming and sweeps by dialog, not by a typed phrase", async () => {
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );

  // The server still rejects anything but the phrase, so it must still be
  // sent. Only the operator stopped retyping it.
  assert.match(page, /const ARM_PHRASE = "AUTOPA VALIDIEREN"/);
  assert.match(page, /phrase: ARM_PHRASE/);

  // No phrase input may come back: a field people learn to copy is a worse
  // prompt than a dialog naming the concrete values.
  assert.doesNotMatch(page, /armPhrase|sweepPhrase/);
  assert.doesNotMatch(page, /placeholder="AUTOPA VALIDIEREN"/);

  // Both actions go through a confirm step that can be cancelled.
  for (const state of ["armConfirming", "sweepConfirming"]) {
    assert.match(page, new RegExp(`${state}\\s*\\?`));
    assert.match(page, new RegExp(`set${state[0].toUpperCase()}${state.slice(1)}\\(true\\)`));
    assert.match(page, new RegExp(`set${state[0].toUpperCase()}${state.slice(1)}\\(false\\)`));
  }
  assert.match(page, /armConfirmSummary/);
  assert.match(page, /sweepConfirmSummary/);
  assert.match(page, /Abbrechen/);
});

test("the sweep dialog counts values the way the server does", async () => {
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  // decimal_range() in src/autopa/sweep.py uses floor(span + 1e-9) + 1. The
  // dialog must not drop that epsilon: plain JS floating point turns
  // (1.4 - 0.2) / 0.2 into 5.999999999999999.
  assert.match(page, /Math\.floor\(span \+ 1e-9\) \+ 1/);

  const count = (from, to, step) =>
    Math.max(0, Math.floor((to - from) / step + 1e-9) + 1);
  // Values taken from the Python implementation for the same inputs.
  assert.equal(count(0.2, 1.4, 0.2), 7);
  assert.equal(count(0.0, 0.04, 0.01), 5);
  assert.equal(count(0.2, 1.0, 0.3), 3);
});

test("guides through the three calibration stages in working order", async () => {
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const css = await readFile(
    new URL("../app/globals.css", import.meta.url),
    "utf8",
  );

  // One card, not several: measuring and tracking are the same tuning job.
  const cards = page.match(/className="adaptive-card"/g) ?? [];
  assert.equal(cards.length, 1, "the whole flow lives in one card");

  // Order follows the work, not the printer state. PA has to settle before
  // retraction is measured, because it decides how much pressure stands in
  // the nozzle when a retraction starts, and the in-print controller only
  // makes sense once the three measurements exist.
  const order = [
    "Stufe 1 · Pressure Advance",
    "Stufe 2 · Rückzugslänge",
    "Stufe 3 · Rückzugsgeschwindigkeit",
    "Zum Schluss · nur im laufenden Druck",
  ].map((label) => page.indexOf(label));
  assert.ok(
    order.every((position) => position > 0),
    "every stage label is present",
  );
  assert.deepEqual(
    [...order].sort((a, b) => a - b),
    order,
    "stages appear in working order",
  );

  // A first-time visitor must not need the docs.
  assert.match(css, /\.card-intro \{/);
  assert.match(page, /className="card-intro"/);
  assert.match(page, /Die Reihenfolge ist nicht beliebig/);
  // The controller's tiny authority is the reason the stages come first.
  assert.match(page, /±0,01/);
  assert.match(page, /±0,30 mm/);

  // The mutually exclusive printer-state gates must survive the merge.
  assert.match(page, /printState !== "standby"/);
  assert.match(page, /nur während „printing“/);
});

test("every stage reports what it handed to the next one", async () => {
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const css = await readFile(
    new URL("../app/globals.css", import.meta.url),
    "utf8",
  );

  // Stages chain through the printer's runtime state: stage 1 applies PA,
  // stage 2 then measures at that PA and applies a length, stage 3 holds
  // that length. A silent result would leave the operator measuring against
  // a value nobody confirmed.
  const results = page.match(/<StageResult /g) ?? [];
  assert.equal(results.length, 3, "all three stages report their result");
  assert.match(page, /apply=\{status\.paSweep\.lastApply\}/);
  assert.match(page, /apply=\{status\.sweep\.lastApply\}/);
  assert.match(css, /\.stage-result \{/);

  // Runtime-only application is the whole safety story - say so.
  assert.match(page, /kein SAVE_CONFIG/);
  assert.match(page, /Klipper-Neustart/);

  // A refused recommendation must name its reason rather than stay blank.
  assert.match(page, /APPLY_SKIP_REASONS/);
  for (const reason of ["outside_bounds", "no_recommendation"]) {
    assert.match(page, new RegExp(reason));
  }
});

test("the speed stage is honest about what the sensor cannot see", async () => {
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );

  // There is no encoder, so a speed that grinds filament can still score
  // well on pressure. The UI has to say so, and must never auto-apply it.
  assert.match(page, /kein durchrutschendes oder/);
  assert.match(page, /nie automatisch übernommen/);
  assert.match(page, /auto_apply: false/);
  assert.match(page, /mode: "speed"/);
});

test("renders opt-in bounded control without direct printer commands", async () => {
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const route = await readFile(
    new URL("../app/api/status/route.ts", import.meta.url),
    "utf8",
  );
  assert.match(page, /printerAction:\s*"none"/);
  assert.match(page, /Profile & Filterregeln speichern/);
  assert.match(page, /Neues Filamentprofil hinzufügen/);
  assert.match(page, /Filamentart \/ Name/);
  assert.match(page, /Live-Daten aktiv/);
  assert.match(page, /SUNLU ABS Green/);
  assert.match(page, /Adaptive PA & Auto-Retract/);
  assert.match(page, /G-Code Context Engine/);
  assert.match(page, /PA-Messfenster aktiv/);
  assert.match(page, /Druckgeschwindigkeit/);
  assert.match(page, /Volumenstrom/);
  assert.match(page, /Dry-Run starten/);
  assert.match(page, /Live-Daten einschalten/);
  assert.match(page, /Live-Daten ausschalten/);
  assert.match(page, /Schaltet die passive ALPS-/);
  assert.match(page, /Chamber-Filter f(?:ü|Ã¼|\\u00fc)r dieses Material/);
  assert.match(page, /Kennung im Dateinamen/);
  assert.match(page, /Filterleistung/);
  assert.match(page, /Nachlauf/);
  assert.match(page, /AUTOPA VALIDIEREN/);
  assert.match(page, /firmware_retraction/);
  assert.doesNotMatch(page, /function PressureGauge|<PressureGauge/);
  assert.doesNotMatch(page, /Druck auf der D(?:üse|Ã¼se|\\u00fcse)/);
  assert.match(page, /Bewegung X \/ Y \/ Z/);
  assert.match(page, /X-Y-Bewegungskreuz/);
  assert.match(page, /Z-Bewegungsbalken/);
  assert.match(page, /Offset\/Schwerkraft entfernt/);
  assert.match(page, /relatives Signal/);
  assert.match(page, /formatSignedRelative/);
  assert.match(page, /DISPLAY_SMOOTHING_ALPHA/);
  assert.match(page, /smoothDisplayValue/);
  assert.doesNotMatch(page, /FLY-ALPS · LIVE/);
  assert.doesNotMatch(page, /monitor-policy|Lokale KI|Spaghetti-Erkennung/);
  assert.match(page, /mainsailUrl\.port === "7126"/);
  assert.doesNotMatch(page, /M104|M109|SET_PRESSURE_ADVANCE|PAUSE|CANCEL_PRINT/);
  assert.doesNotMatch(route, /M104|M109|SET_PRESSURE_ADVANCE|PAUSE|CANCEL_PRINT/);
});
