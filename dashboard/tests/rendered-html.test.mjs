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

test("keeps the local dashboard read-only by design", async () => {
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const route = await readFile(
    new URL("../app/api/status/route.ts", import.meta.url),
    "utf8",
  );
  assert.match(page, /printerAction:\s*"none"/);
  assert.match(page, /Profile lokal speichern/);
  assert.match(page, /Neues Filamentprofil hinzufügen/);
  assert.match(page, /Filamentart \/ Name/);
  assert.match(page, /Live-Daten aktiv/);
  assert.match(page, /SUNLU ABS Green/);
  assert.doesNotMatch(page, /monitor-policy|Lokale KI|Spaghetti-Erkennung/);
  assert.match(page, /mainsailUrl\.port === "7126"/);
  assert.doesNotMatch(page, /M104|M109|SET_PRESSURE_ADVANCE|PAUSE|CANCEL_PRINT/);
  assert.doesNotMatch(route, /M104|M109|SET_PRESSURE_ADVANCE|PAUSE|CANCEL_PRINT/);
});
