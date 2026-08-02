"use client";

import type { PointerEvent as ReactPointerEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  CAM_STORAGE_KEY,
  type CamBox,
  isMeasurableViewport,
  clampCamBox,
  defaultCamBox,
  snapCamBox,
} from "./camera-box";

type SignalState = "ok" | "waiting" | "warning" | "error";

type DashboardStatus = {
  timestamp: string;
  demo: boolean;
  printer: {
    connected: boolean;
    state: string;
    printState: string;
    temperature: number | null;
    target: number | null;
    pressureAdvance: number | null;
    smoothTime: number | null;
    nozzleDiameter: number | null;
    filamentDiameter: number | null;
    maxExtrudeCrossSection: number | null;
    firmwareRetractionAvailable: boolean;
    retractLength: number | null;
    retractSpeed: number | null;
  };
  capture: {
    state: SignalState;
    dataset: string | null;
    ageSeconds: number | null;
    manager?: {
      state: string;
      active: boolean;
      canStart: boolean;
      canStop: boolean;
      dataset: string | null;
      mode?: "disabled" | "live_preview" | "print_bound";
      attachedToPrint: boolean;
      stopReason: string | null;
      error: string | null;
      monitorError: string | null;
      printerAction: "none";
    };
  };
  sensors: {
    alps: {
      state: SignalState;
      value: number | null;
      baseline: number | null;
      delta: number | null;
      normalized: number | null;
      sampleRate: number | null;
    };
    accelerometer: {
      enabled: boolean;
      type: string;
      name: string | null;
      state: SignalState;
      magnitude: number | null;
      motionX: number | null;
      motionY: number | null;
      motionZ: number | null;
      rmsX: number | null;
      rmsY: number | null;
      rmsZ: number | null;
      sampleRate: number | null;
    };
  };
  quality: {
    state: SignalState;
    message: string;
  };
  safety: {
    printerAction: string;
  };
  control: {
    mode: "off" | "dry_run" | "apply";
    allowPrinterCommands: boolean;
    armed: boolean;
    armedSecondsRemaining: number;
    adaptivePAEnabled: boolean;
    autoRetractEnabled: boolean;
    suggestedPA: number | null;
    suggestedRetractMm: number | null;
    paConfidence: string;
    retractConfidence: string;
    paWindows: number;
    retractEvents: number;
    reason: string | null;
    gcodeContext: {
      active: boolean;
      layer: number | null;
      z_mm: number | null;
      feature: string;
      object: string | null;
      source_line?: number | null;
      pa_eligible: boolean;
      eligibility_reason: string;
      print_time?: number | null;
    } | null;
    paContextEligible: boolean;
    extruderVelocityMmS: number | null;
    toolheadVelocityMmS: number | null;
    volumetricFlowMm3S: number | null;
    contextPrintTime: number | null;
    commandCount: number;
    lastCommand: string | null;
    lastError: string | null;
  };
  chamberFilter: {
    state: string;
    allowCommands: boolean;
    availableFans: string[];
    filename: string | null;
    matchedProfile: {
      name: string;
      filter_tag: string;
      filter_fan: string;
      filter_speed_percent: number;
      filter_post_run_minutes: number;
    } | null;
    activeFan: string | null;
    activeSpeedPercent: number | null;
    postRunSecondsRemaining: number;
    configuredProfiles: number;
    lastCommand: string | null;
    lastError: string | null;
    commandCount: number;
    printerAction: "none" | "chamber_filter_only";
  };
  sweep: SweepStatus;
  paSweep: SweepStatus;
};

type SweepLastRun = {
  startedAt: string;
  // "length" varies RETRACT_LENGTH, "speed" holds the length and varies
  // RETRACT_SPEED/UNRETRACT_SPEED. The PA sweep reports kValues instead.
  mode?: "length" | "speed";
  retractValues?: number[];
  speedValues?: number[] | null;
  kValues?: number[];
  heldRetractMm?: number | null;
  cycles: number;
  restoreRetractMm?: number;
  estimatedDurationS: number;
  filamentLengthMm: number;
  scriptLines: number;
};

// What the post-sweep pipeline did with the analysis: applied the value at
// runtime, refused it with a reason, or - for a speed sweep - reported it as
// an advisory because this runner may not send a speed.
type SweepApply = {
  applied: boolean;
  advisory?: boolean;
  reason?: string;
  runtimeOnly?: boolean;
  previousMm?: number | null;
  appliedMm?: number | null;
  appliedValue?: number | null;
  previousValue?: number | null;
  previous?: number | null;
  recommendedMm?: number | null;
  recommended?: number | null;
  currentMm?: number | null;
  current?: number | null;
  deviationMm?: number | null;
  deviation?: number | null;
  boundMm?: number | null;
  bound?: number | null;
  recommendedSpeedMmS?: number | null;
  sweptVariable?: string | null;
  source?: string | null;
  at?: string;
};

type SweepAnalysis = {
  busy: boolean;
  stage: string | null;
  percent: number;
  secondsRemaining: number;
  step: string | null;
};

type SweepStatus = {
  allowPrinterCommands: boolean;
  confirmationPhraseRequired: boolean;
  lastRun: SweepLastRun | null;
  lastApply: SweepApply | null;
  lastAnalysis?: StageAnalysis | null;
  // Stage 2 and stage 3 share the retract runner, so each keeps its own slot.
  lastApplyByMode?: Record<string, SweepApply | null>;
  lastRunByMode?: Record<string, SweepLastRun | null>;
  lastAnalysisByMode?: Record<string, StageAnalysis | null>;
  analysis?: SweepAnalysis;
  // Set while the printer is executing this stage's script. Moonraker only
  // answers once the whole script has run, so this is the only signal the
  // page has while the sweep is under way.
  running?: StageProgress | null;
  lastError: string | null;
  printerAction: "none";
};

type MaterialProfile = {
  id: string;
  name: string;
  manufacturer: string;
  minTemperature: number;
  maxTemperature: number;
  temperatureStep: number;
  minBedTemperature: number;
  maxBedTemperature: number;
  minPrintSpeed: number;
  maxPrintSpeed: number;
  paStart: number;
  paStop: number;
  paStep: number;
  cycles: number;
  filterEnabled: boolean;
  filterTag: string;
  filterFan: string;
  filterSpeedPercent: number;
  filterPostRunMinutes: number;
};

const FILTER_DEFAULTS = {
  filterEnabled: false,
  filterFan: "chamber_filter",
  filterSpeedPercent: 100,
  filterPostRunMinutes: 20,
};

type PlotPoint = {
  pressure: number;
  motionX: number;
  motionY: number;
  motionZ: number;
  temperature: number;
  target: number;
};

const DEFAULT_PROFILES: MaterialProfile[] = [
  {
    id: "pla",
    name: "PLA",
    manufacturer: "Generischer Startwert",
    minTemperature: 195,
    maxTemperature: 220,
    temperatureStep: 5,
    minBedTemperature: 50,
    maxBedTemperature: 65,
    minPrintSpeed: 40,
    maxPrintSpeed: 180,
    paStart: 0.01,
    paStop: 0.05,
    paStep: 0.01,
    cycles: 3,
    ...FILTER_DEFAULTS,
    filterTag: "[PLA]",
  },
  {
    id: "petg",
    name: "PETG",
    manufacturer: "Generischer Startwert",
    minTemperature: 225,
    maxTemperature: 250,
    temperatureStep: 5,
    minBedTemperature: 70,
    maxBedTemperature: 90,
    minPrintSpeed: 40,
    maxPrintSpeed: 160,
    paStart: 0.01,
    paStop: 0.06,
    paStep: 0.01,
    cycles: 3,
    ...FILTER_DEFAULTS,
    filterTag: "[PETG]",
  },
  {
    id: "abs",
    name: "ABS",
    manufacturer: "SUNLU ABS Green · 1,75 mm",
    minTemperature: 250,
    maxTemperature: 280,
    temperatureStep: 5,
    minBedTemperature: 80,
    maxBedTemperature: 100,
    minPrintSpeed: 50,
    maxPrintSpeed: 200,
    paStart: 0.01,
    paStop: 0.06,
    paStep: 0.01,
    cycles: 3,
    ...FILTER_DEFAULTS,
    filterTag: "[ABS]",
  },
  {
    id: "asa",
    name: "ASA",
    manufacturer: "Generischer Startwert",
    minTemperature: 240,
    maxTemperature: 265,
    temperatureStep: 5,
    minBedTemperature: 90,
    maxBedTemperature: 110,
    minPrintSpeed: 40,
    maxPrintSpeed: 150,
    paStart: 0.01,
    paStop: 0.06,
    paStep: 0.01,
    cycles: 3,
    ...FILTER_DEFAULTS,
    filterTag: "[ASA]",
  },
  {
    id: "tpu",
    name: "TPU",
    manufacturer: "Generischer Startwert",
    minTemperature: 210,
    maxTemperature: 235,
    temperatureStep: 5,
    minBedTemperature: 35,
    maxBedTemperature: 60,
    minPrintSpeed: 20,
    maxPrintSpeed: 80,
    paStart: 0.01,
    paStop: 0.12,
    paStep: 0.02,
    cycles: 3,
    ...FILTER_DEFAULTS,
    filterTag: "[TPU]",
  },
];

const EMPTY_STATUS: DashboardStatus = {
  timestamp: "1970-01-01T00:00:00.000Z",
  demo: true,
  printer: {
    connected: false,
    state: "Verbindung wird aufgebaut",
    printState: "unbekannt",
    temperature: null,
    target: null,
    pressureAdvance: null,
    smoothTime: null,
    nozzleDiameter: null,
    filamentDiameter: null,
    maxExtrudeCrossSection: null,
    firmwareRetractionAvailable: false,
    retractLength: null,
    retractSpeed: null,
  },
  capture: {
    state: "waiting",
    dataset: null,
    ageSeconds: null,
    manager: {
      state: "disabled",
      active: false,
      canStart: false,
      canStop: false,
      dataset: null,
      attachedToPrint: false,
      stopReason: null,
      error: null,
      monitorError: null,
      printerAction: "none",
    },
  },
  sensors: {
    alps: {
      state: "waiting",
      value: null,
      baseline: null,
      delta: null,
      normalized: null,
      sampleRate: null,
    },
    accelerometer: {
      enabled: true,
      type: "lis2dw",
      name: null,
      state: "waiting",
      magnitude: null,
      motionX: null,
      motionY: null,
      motionZ: null,
      rmsX: null,
      rmsY: null,
      rmsZ: null,
      sampleRate: null,
    },
  },
  quality: {
    state: "waiting",
    message: "Warte auf den ersten Status",
  },
  safety: { printerAction: "none" },
  control: {
    mode: "off",
    allowPrinterCommands: false,
    armed: false,
    armedSecondsRemaining: 0,
    adaptivePAEnabled: false,
    autoRetractEnabled: false,
    suggestedPA: null,
    suggestedRetractMm: null,
    paConfidence: "waiting",
    retractConfidence: "waiting",
    paWindows: 0,
    retractEvents: 0,
    reason: "waiting_for_live_data",
    gcodeContext: null,
    paContextEligible: false,
    extruderVelocityMmS: null,
    toolheadVelocityMmS: null,
    volumetricFlowMm3S: null,
    contextPrintTime: null,
    commandCount: 0,
    lastCommand: null,
    lastError: null,
  },
  chamberFilter: {
    state: "disabled",
    allowCommands: false,
    availableFans: [],
    filename: null,
    matchedProfile: null,
    activeFan: null,
    activeSpeedPercent: null,
    postRunSecondsRemaining: 0,
    configuredProfiles: 0,
    lastCommand: null,
    lastError: null,
    commandCount: 0,
    printerAction: "none",
  },
  sweep: {
    allowPrinterCommands: false,
    confirmationPhraseRequired: true,
    lastRun: null,
    lastApply: null,
    lastError: null,
    printerAction: "none",
  },
  paSweep: {
    allowPrinterCommands: false,
    confirmationPhraseRequired: true,
    lastRun: null,
    lastApply: null,
    lastError: null,
    printerAction: "none",
  },
};

const STATUS_LABEL: Record<SignalState, string> = {
  ok: "OK",
  waiting: "Wartet",
  warning: "Prüfen",
  error: "Fehler",
};

function formatNumber(value: number | null, digits = 1) {
  return value === null || Number.isNaN(value) ? "—" : value.toFixed(digits);
}

// The server checks this phrase on /api/control/arm, /api/sweep/run and
// /api/pa-sweep/run and rejects anything else. The dashboard no longer makes
// the operator retype it: a confirmation dialog that names what is about to
// happen is a better safety prompt than a phrase people learn to copy. The
// server-side gate is unchanged.
const ARM_PHRASE = "AUTOPA VALIDIEREN";

// Mirrors decimal_range() in src/autopa/sweep.py, epsilon included. Without
// it (1.4 - 0.2) / 0.2 evaluates to 5.999999999999999 and a dialog would
// promise six values while the printer runs seven. A confirmation that states
// a wrong number is worse than none.
const APPLY_SKIP_REASONS: Record<string, string> = {
  outside_bounds:
    "Empfehlung lag außerhalb der erlaubten Abweichung und wurde verworfen.",
  values_unavailable: "Ist- oder Sollwert war nicht lesbar.",
  no_recommendation:
    "Kein auswertbares Ergebnis — die Analyse ist fail-closed und schweigt lieber.",
  no_capture_dataset: "Es wurde kein Messdatensatz aufgezeichnet.",
  analysis_failed: "Die Auswertung ist fehlgeschlagen.",
  auto_apply_disabled: "Auto-Übernahme war für diesen Lauf abgeschaltet.",
};

// Turns a stage result into one sentence. Every stage hands its value to the
// next through the printer's runtime state, so the operator has to be able to
// see what actually landed - otherwise stage 2 silently measures against a
// pressure advance nobody confirmed.
function describeStageResult(
  apply: SweepApply | null,
  unit: string,
): { text: string; tone: "ok" | "info" | "warn" } | null {
  if (!apply) return null;
  if (apply.advisory) {
    const value = apply.recommendedSpeedMmS;
    return {
      tone: "info",
      text:
        value === null || value === undefined
          ? "Ergebnis liegt vor, wird aber nicht automatisch übernommen."
          : `Empfehlung: ${value} mm/s. Wird bewusst nicht automatisch übernommen — bitte selbst in [firmware_retraction] eintragen.`,
    };
  }
  if (apply.applied) {
    // The two runners disagree on key names: the retract runner writes
    // previousMm/appliedMm, the PA runner previous/appliedValue. Reading only
    // one set rendered the other stage's before-value as "?".
    const from = apply.previousMm ?? apply.previousValue ?? apply.previous;
    const to = apply.appliedMm ?? apply.appliedValue;
    return {
      tone: "ok",
      text: `Übernommen: ${from ?? "?"} → ${to ?? "?"} ${unit}. Nur zur Laufzeit, kein SAVE_CONFIG — nach einem Klipper-Neustart ist der alte Wert zurück.`,
    };
  }
  const reason =
    APPLY_SKIP_REASONS[apply.reason ?? ""] ??
    `Nicht übernommen (${apply.reason ?? "unbekannt"}).`;
  const recommended = apply.recommendedMm ?? apply.recommended;
  const current = apply.currentMm ?? apply.current;
  const bound = apply.boundMm ?? apply.bound;
  const detail =
    recommended !== null && recommended !== undefined
      ? ` Empfohlen war ${recommended} ${unit} bei aktuell ${current ?? "?"} ${unit} (Grenze ±${bound ?? "?"}).`
      : "";
  return { tone: "warn", text: reason + detail };
}

type AnalysisPoint = {
  value: number;
  cost: number | null;
  cyclesIncluded: number | null;
  cyclesTotal: number | null;
};

type StageAnalysis = {
  sweptVariable: string;
  points: AnalysisPoint[];
  best: number | null;
  bestAtRangeEdge: boolean;
  qualityGatePassed: boolean;
};

// The cost curve behind the recommendation. A bare number reads as
// authoritative even when the curve is noisy or its winner sits at the edge
// of the swept range, where the real optimum may lie outside what was
// measured at all.
function StageChart({
  analysis,
  unit,
}: {
  analysis: StageAnalysis | null | undefined;
  unit: string;
}) {
  if (!analysis || analysis.points.length < 2) return null;
  const points = analysis.points;
  const costs = points
    .map((p) => p.cost)
    .filter((c): c is number => c !== null);
  if (costs.length < 2) return null;

  const width = 100;
  const height = 34;
  const max = Math.max(...costs);
  const min = Math.min(...costs);
  const span = max - min || 1;
  const step = width / points.length;
  const bestPoint = points.find((p) => p.value === analysis.best);
  const bestCost =
    bestPoint?.cost !== null && bestPoint?.cost !== undefined
      ? bestPoint.cost.toFixed(3)
      : "—";
  // Lower cost is better, so the best value is drawn tallest.
  const barHeight = (cost: number) =>
    Math.max(2, ((max - cost) / span) * (height - 6) + 3);

  return (
    <div className="stage-chart">
      <div className="stage-chart-head">
        <span>Messkurve — höherer Balken ist besser</span>
        {analysis.bestAtRangeEdge && (
          <span className="stage-chart-edge">Bester Wert am Rand</span>
        )}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"
           role="img" aria-label="Kosten je gemessenem Wert">
        {points.map((point, index) => {
          const cost = point.cost;
          const isBest = point.value === analysis.best;
          if (cost === null) {
            return (
              <rect
                key={point.value}
                x={index * step + step * 0.15}
                y={height - 3}
                width={step * 0.7}
                height={3}
                className="bar-empty"
              />
            );
          }
          const barH = barHeight(cost);
          return (
            <rect
              key={point.value}
              x={index * step + step * 0.15}
              y={height - barH}
              width={step * 0.7}
              height={barH}
              className={isBest ? "bar-best" : "bar"}
            />
          );
        })}
      </svg>
      <div className="stage-chart-axis">
        {points.map((point) => (
          <span
            key={point.value}
            className={point.value === analysis.best ? "is-best" : undefined}
          >
            {point.value}
          </span>
        ))}
      </div>
      <p className="stage-chart-note">
        Die Balkenhöhe zeigt, wie gut ein Wert abgeschnitten hat. Intern wird
        ein Kostenwert berechnet, bei dem <em>niedriger</em> besser ist — der
        beste Wert hat also den höchsten Balken und die niedrigsten Kosten
        ({bestCost}).{" "}
        {points.filter((p) => p.cost === null).length > 0 && (
          <>
            Werte ohne Balken lieferten zu wenig verwertbare Zyklen.{" "}
          </>
        )}
        {analysis.bestAtRangeEdge ? (
          <>
            Der beste Wert ({analysis.best} {unit}) liegt am Rand des
            gemessenen Bereichs — das Optimum kann außerhalb liegen. Erweitere
            den Bereich in diese Richtung und miss erneut.
          </>
        ) : (
          <>
            Der beste Wert ({analysis.best} {unit}) liegt innerhalb des
            gemessenen Bereichs.
          </>
        )}
      </p>
    </div>
  );
}

type StageProgress = {
  active: boolean;
  percent: number;
  secondsRemaining: number;
};

const ANALYSIS_STEPS: Record<string, string> = {
  capture: "Messung läuft noch",
  finishing_capture: "Aufnahme wird abgeschlossen",
  aligning: "Zeitausrichtung auf Klippers print_time",
  quality: "Qualitätsprüfung der Messkette",
  analyzing: "Auswertung der Messzyklen",
};

const viewport = () => ({
  width: window.innerWidth,
  height: window.innerHeight,
});

function CameraWindow({ streamUrl }: { streamUrl: string }) {
  const [box, setBox] = useState<CamBox | null>(null);
  const drag = useRef<
    | {
        mode: "move" | "resize";
        pointerId: number;
        startX: number;
        startY: number;
        origin: CamBox;
      }
    | null
  >(null);

  // Placed on the client only: the position depends on the viewport, which
  // does not exist while the page is rendered on the server.
  useEffect(() => {
    let initial: CamBox = defaultCamBox(viewport());
    try {
      const stored = window.localStorage.getItem(CAM_STORAGE_KEY);
      if (stored) initial = { ...initial, ...JSON.parse(stored) };
    } catch {
      // A corrupt entry must not keep the window off screen.
    }
    setBox(clampCamBox(initial, viewport()));
  }, []);

  useEffect(() => {
    if (!box) return;
    if (!isMeasurableViewport(viewport())) return;
    try {
      window.localStorage.setItem(CAM_STORAGE_KEY, JSON.stringify(box));
    } catch {
      // Storage may be unavailable; the window still works this session.
    }
  }, [box]);

  // A viewport that shrinks must not strand the window outside it.
  useEffect(() => {
    const onResize = () => setBox((b) => (b ? clampCamBox(b, viewport()) : b));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const onPointerDown = (mode: "move" | "resize") => (
    event: ReactPointerEvent,
  ) => {
    if (!box) return;
    event.preventDefault();
    try {
      // Capture keeps the drag alive when the pointer leaves the window. It
      // throws for a pointer the browser does not know, and an exception
      // here would abort before the drag state is set - leaving a window
      // that simply refuses to move.
      (event.target as Element).setPointerCapture?.(event.pointerId);
    } catch {
      // Dragging still works without capture as long as the pointer stays
      // over the window.
    }
    drag.current = {
      mode,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      origin: box,
    };
  };

  const onPointerMove = (event: ReactPointerEvent) => {
    const state = drag.current;
    if (!state || state.pointerId !== event.pointerId) return;
    const dx = event.clientX - state.startX;
    const dy = event.clientY - state.startY;
    setBox(
      clampCamBox(
        state.mode === "move"
          ? { ...state.origin, x: state.origin.x + dx, y: state.origin.y + dy }
          : {
              ...state.origin,
              width: state.origin.width + dx,
              height: state.origin.height + dy,
            },
        viewport(),
      ),
    );
  };

  const onPointerUp = (event: ReactPointerEvent) => {
    const state = drag.current;
    if (!state || state.pointerId !== event.pointerId) return;
    drag.current = null;
    // Snap only when the drag ends, so the window does not jump around
    // while it is still being moved.
    setBox((b) => (b ? snapCamBox(b, viewport()) : b));
  };

  if (!box) return null;

  if (box.hidden) {
    return (
      <button
        type="button"
        className="camera-reopen"
        onClick={() => setBox({ ...box, hidden: false })}
      >
        Kamera einblenden
      </button>
    );
  }

  return (
    <section
      className="camera-window"
      style={{
        left: box.x,
        top: box.y,
        width: box.width,
        height: box.height,
      }}
      aria-label="Live-Kamera"
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div className="camera-bar" onPointerDown={onPointerDown("move")}>
        <span>Live-Kamera</span>
        <button
          type="button"
          className="camera-close"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={() => setBox({ ...box, hidden: true })}
          aria-label="Kamera ausblenden"
        >
          ×
        </button>
      </div>
      {/* An MJPEG stream is a plain image element; no player is involved. */}
      <img className="camera-image" src={streamUrl} alt="" draggable={false} />
      <div
        className="camera-resize"
        onPointerDown={onPointerDown("resize")}
        aria-hidden="true"
      />
    </section>
  );
}

function StageProgressBar({
  label,
  percent,
  secondsRemaining,
  detail,
}: {
  label: string;
  percent: number;
  secondsRemaining: number;
  detail?: string | null;
}) {
  return (
    <div className="stage-progress" role="status" aria-live="polite">
      <div className="stage-progress-head">
        <span>{label}</span>
        <span className="stage-progress-value">{percent} %</span>
      </div>
      <div className="stage-progress-track">
        <div
          className="stage-progress-fill"
          style={{ width: `${Math.max(2, Math.min(100, percent))}%` }}
        />
      </div>
      <p className="stage-progress-note">
        {detail ? `${detail} · ` : ""}
        {secondsRemaining > 0
          ? `noch etwa ${secondsRemaining} s`
          : "gleich fertig"}
        {" · nicht am Drucker eingreifen"}
      </p>
    </div>
  );
}

// One control per stage, showing exactly one of four states. The start
// button used to stay visible while the sweep ran and while the analysis
// worked - merely disabled - which read as if nothing had been triggered.
function StageAction({
  applied,
  busy,
  disabled,
  startLabel,
  onStart,
  onSave,
  running,
  analyzing,
  analysisPercent,
  analysisSeconds,
  analysisStep,
  confirmingSave,
  saveSummary,
  configSnippet,
  onCopyConfig,
  copied,
  onSaveCancel,
  blockedReason,
}: {
  applied: boolean;
  busy: boolean;
  disabled: boolean;
  startLabel: string;
  onStart: () => void;
  onSave: () => void;
  running?: StageProgress | null;
  analyzing?: boolean;
  analysisPercent?: number;
  analysisSeconds?: number;
  analysisStep?: string | null;
  confirmingSave?: boolean;
  saveSummary?: string;
  configSnippet?: string;
  onCopyConfig?: () => void;
  copied?: boolean;
  onSaveCancel?: () => void;
  blockedReason?: string | null;
}) {
  if (running?.active) {
    return (
      <StageProgressBar
        label="Sweep läuft — der Drucker extrudiert"
        percent={running.percent}
        secondsRemaining={running.secondsRemaining}
        detail="Bleib am Drucker"
      />
    );
  }
  if (analyzing) {
    return (
      <StageProgressBar
        label="Daten werden ausgewertet"
        percent={analysisPercent ?? 0}
        secondsRemaining={analysisSeconds ?? 0}
        detail={ANALYSIS_STEPS[analysisStep ?? ""] ?? null}
      />
    );
  }
  if (confirmingSave) {
    // Shown where the button is, not at the foot of the card.
    return (
      <div className="confirm-box">
        <p>{saveSummary}</p>
        <pre className="config-snippet">{configSnippet}</pre>
        <div className="confirm-actions">
          <button
            type="button"
            className="primary-button"
            onClick={onCopyConfig}
          >
            {copied ? "Kopiert" : "Zeilen kopieren"}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={onSaveCancel}
          >
            Schließen
          </button>
        </div>
      </div>
    );
  }
  if (applied) {
    return (
      <div className="arming-row">
        <button
          type="button"
          className="danger-button is-emphasised"
          onClick={onSave}
        >
          Wert dauerhaft übernehmen …
        </button>
        <button
          type="button"
          className="secondary-button is-compact"
          disabled={busy || disabled}
          onClick={onStart}
        >
          Nochmal messen
        </button>
      </div>
    );
  }
  if (blockedReason) {
    return (
      <p className="stage-blocked">
        <strong>Gesperrt.</strong> {blockedReason}
      </p>
    );
  }
  return (
    <div className="arming-row">
      <button
        type="button"
        className="primary-button"
        disabled={busy || disabled}
        onClick={onStart}
      >
        {startLabel}
      </button>
    </div>
  );
}

function StageResult({
  apply,
  unit,
  analyzing,
  ranSomething,
}: {
  apply: SweepApply | null;
  unit: string;
  analyzing?: boolean;
  ranSomething?: boolean;
}) {
  // Three distinct states, because "nothing shown" used to mean all of them:
  // never run, still analyzing, and finished.
  if (analyzing) return null;
  const result = describeStageResult(apply, unit);
  if (!result) {
    if (!ranSomething) return null;
    return (
      <p className="stage-result tone-warn">
        <strong>Kein Ergebnis.</strong> Die Stufe lief, hat aber nichts
        Auswertbares geliefert.
      </p>
    );
  }
  return (
    <p className={`stage-result tone-${result.tone}`}>
      <strong>Ergebnis:</strong> {result.text}
    </p>
  );
}

function countSweepValues(from: string, to: string, step: string) {
  const span = (Number(to) - Number(from)) / Number(step);
  return Number.isFinite(span) ? Math.max(0, Math.floor(span + 1e-9) + 1) : 0;
}

const PRESSURE_DISPLAY_DEADBAND = 0.1;
const MOTION_DISPLAY_DEADBAND_MM_S2 = 200;
const DISPLAY_SMOOTHING_ALPHA = 0.42;

type SmoothedSensorValues = {
  pressure: number | null;
  motionX: number | null;
  motionY: number | null;
  motionZ: number | null;
  rmsX: number | null;
  rmsY: number | null;
  rmsZ: number | null;
};

function smoothDisplayValue(
  previous: number | null,
  next: number | null,
) {
  if (next === null || Number.isNaN(next)) return null;
  if (previous === null || Number.isNaN(previous)) return next;
  return previous + (next - previous) * DISPLAY_SMOOTHING_ALPHA;
}

function formatSignedRelative(value: number | null) {
  if (value === null || Number.isNaN(value)) return "—";
  if (Math.abs(value) < PRESSURE_DISPLAY_DEADBAND) return "≈ 0 %";
  const percent = value * 100;
  return `${percent > 0 ? "+" : "−"}${Math.abs(percent).toFixed(1)} %`;
}

function motionForDisplay(value: number | null) {
  if (value === null || Number.isNaN(value)) return null;
  return Math.abs(value) < MOTION_DISPLAY_DEADBAND_MM_S2 ? 0 : value;
}

function pressureMarkerPosition(value: number | null) {
  if (value === null || Number.isNaN(value)) return 50;
  const displayed =
    Math.abs(value) < PRESSURE_DISPLAY_DEADBAND ? 0 : value;
  return 50 + Math.tanh(displayed / 1.5) * 42;
}

function formatMotion(value: number | null) {
  if (value === null || Number.isNaN(value)) return "—";
  const converted = value / 1000;
  return `${converted > 0 ? "+" : converted < 0 ? "−" : ""}${Math.abs(converted).toFixed(2)}`;
}

const FEATURE_LABELS: Record<string, string> = {
  external_perimeter: "Außenwand",
  internal_perimeter: "Innenwand",
  infill: "Infill",
  solid_infill: "Massives Infill",
  gap_fill: "Lückenfüllung",
  bridge: "Brücke / Überhang",
  support: "Support",
  skirt_brim: "Skirt / Brim",
  ironing: "Glätten",
  unknown: "Unbekannt",
};

const CONTEXT_REASON_LABELS: Record<string, string> = {
  eligible_extrusion_feature: "PA-Messfenster aktiv",
  feature_not_validated_for_pa: "PA-Messfenster ignoriert",
  feature_unknown: "Feature unbekannt – PA bleibt unverändert",
  context_marker_pending_or_missing: "Warte auf Context-Marker",
  print_time_missing: "Klipper-Zeitbasis fehlt",
};

function LineChart({
  title,
  eyebrow,
  values,
  color,
  unit,
  value,
  isLive,
  idleLabel = "Kein Live-Stream",
}: {
  title: string;
  eyebrow: string;
  values: number[];
  color: string;
  unit: string;
  value: string;
  isLive: boolean;
  idleLabel?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(bounds.width * scale));
      canvas.height = Math.max(1, Math.round(bounds.height * scale));
      context.setTransform(scale, 0, 0, scale, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);

      context.strokeStyle = "rgba(255,255,255,.07)";
      context.lineWidth = 1;
      for (let row = 1; row < 4; row += 1) {
        const y = (bounds.height / 4) * row;
        context.beginPath();
        context.moveTo(0, y);
        context.lineTo(bounds.width, y);
        context.stroke();
      }

      const cleanValues = values.filter(Number.isFinite);
      if (cleanValues.length < 2) return;
      let min = Math.min(...cleanValues);
      let max = Math.max(...cleanValues);
      const padding = Math.max((max - min) * 0.18, Math.abs(max) * 0.03, 1);
      min -= padding;
      max += padding;

      const gradient = context.createLinearGradient(0, 0, 0, bounds.height);
      gradient.addColorStop(0, `${color}55`);
      gradient.addColorStop(1, `${color}00`);
      const xFor = (index: number) =>
        (index / Math.max(1, values.length - 1)) * bounds.width;
      const yFor = (point: number) =>
        bounds.height - ((point - min) / (max - min)) * bounds.height;

      context.beginPath();
      values.forEach((point, index) => {
        const x = xFor(index);
        const y = yFor(point);
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.lineTo(bounds.width, bounds.height);
      context.lineTo(0, bounds.height);
      context.closePath();
      context.fillStyle = gradient;
      context.fill();

      context.beginPath();
      values.forEach((point, index) => {
        const x = xFor(index);
        const y = yFor(point);
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.strokeStyle = color;
      context.lineWidth = 2;
      context.lineJoin = "round";
      context.stroke();
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [color, values]);

  return (
    <article className="chart-card">
      <div className="chart-header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h3>{title}</h3>
        </div>
        <p className="chart-value">
          {value}
          <span>{unit}</span>
        </p>
      </div>
      <canvas ref={canvasRef} aria-label={`${title} Live-Diagramm`} />
      <div className="chart-footer">
        <span>vor 60 s</span>
        <span
          className={`live-indicator ${isLive ? "is-live" : ""}`}
          aria-label={isLive ? "Live-Daten aktiv" : idleLabel}
        >
          <span aria-hidden="true" />
          {isLive ? "Live" : idleLabel}
        </span>
      </div>
    </article>
  );
}

function LiveIndicator({
  isLive,
  idleLabel,
}: {
  isLive: boolean;
  idleLabel: string;
}) {
  return (
    <span
      className={`live-indicator ${isLive ? "is-live" : ""}`}
      aria-label={isLive ? "Live-Daten aktiv" : idleLabel}
    >
      <span aria-hidden="true" />
      {isLive ? "Live" : idleLabel}
    </span>
  );
}

function PressureSignalCard({
  normalized,
  delta,
  isLive,
}: {
  normalized: number | null;
  delta: number | null;
  isLive: boolean;
}) {
  const markerPosition = pressureMarkerPosition(normalized);
  return (
    <article className="chart-card pressure-signal-card">
      <div className="chart-header">
        <div>
          <p className="eyebrow">FLY-ALPS</p>
          <h3>Düsendruck</h3>
        </div>
        <p className="chart-value pressure-signal-value">
          {formatSignedRelative(normalized)}
          <span>relatives Signal</span>
        </p>
      </div>
      <div className="pressure-signal-visual">
        <div
          className="pressure-signal-scale"
          aria-label="Düsendruck relativ zum Nullpunkt"
        >
          <span className="pressure-signal-zero" />
          <span
            className="pressure-signal-marker"
            style={{ left: `${markerPosition}%` }}
          />
        </div>
        <div className="pressure-direction-labels" aria-hidden="true">
          <span>−</span>
          <span>0</span>
          <span>+</span>
        </div>
      </div>
      <div className="signal-detail-row">
        <span>Δ {formatNumber(delta, 0)} counts</span>
        <span>− Zug · + Druck</span>
      </div>
      <div className="chart-footer">
        <span>Nullpunktbezogen</span>
        <LiveIndicator isLive={isLive} idleLabel="Kein Live-Stream" />
      </div>
    </article>
  );
}

function MotionVectorCard({
  sensorType,
  enabled,
  x,
  y,
  z,
  rmsX,
  rmsY,
  rmsZ,
  history,
  isLive,
}: {
  sensorType: string;
  enabled: boolean;
  x: number | null;
  y: number | null;
  z: number | null;
  rmsX: number | null;
  rmsY: number | null;
  rmsZ: number | null;
  history: PlotPoint[];
  isLive: boolean;
}) {
  const displayedX = motionForDisplay(x);
  const displayedY = motionForDisplay(y);
  const displayedZ = motionForDisplay(z);
  const recentMaximum = Math.max(
    0,
    ...history.flatMap((point) => [
      Math.abs(point.motionX),
      Math.abs(point.motionY),
      Math.abs(point.motionZ),
    ]),
    Math.abs(displayedX ?? 0),
    Math.abs(displayedY ?? 0),
    Math.abs(displayedZ ?? 0),
  );
  const scale = Math.max(
    5000,
    Math.ceil((recentMaximum * 1.5) / 5000) * 5000,
  );
  const xPosition =
    50 + Math.max(-1, Math.min(1, (displayedX ?? 0) / scale)) * 42;
  const yPosition =
    50 - Math.max(-1, Math.min(1, (displayedY ?? 0) / scale)) * 42;
  const zOffset =
    Math.max(-1, Math.min(1, (displayedZ ?? 0) / scale)) * 42;
  const measuredRms =
    rmsX === null || rmsY === null || rmsZ === null
      ? null
      : Math.sqrt(rmsX ** 2 + rmsY ** 2 + rmsZ ** 2);
  const rmsTotal =
    measuredRms !== null &&
    measuredRms < MOTION_DISPLAY_DEADBAND_MM_S2
      ? 0
      : measuredRms;
  const idleLabel = enabled ? "Kein Live-Stream" : "Deaktiviert";

  return (
    <article className="chart-card motion-vector-card">
      <div className="chart-header">
        <div>
          <p className="eyebrow">
            {enabled ? sensorType.toUpperCase() : "OPTIONAL"}
          </p>
          <h3>Bewegung X / Y / Z</h3>
        </div>
        <p className="chart-value motion-rms-value">
          {formatMotion(rmsTotal)}
          <span>m/s² RMS</span>
        </p>
      </div>
      <div className="motion-visual">
        <div className="xy-cross" aria-label="X-Y-Bewegungskreuz">
          <span className="xy-axis xy-axis-x" />
          <span className="xy-axis xy-axis-y" />
          <span className="axis-label axis-label-x-minus">−X</span>
          <span className="axis-label axis-label-x-plus">+X</span>
          <span className="axis-label axis-label-y-minus">−Y</span>
          <span className="axis-label axis-label-y-plus">+Y</span>
          <span
            className={`xy-motion-dot ${isLive ? "is-live" : ""}`}
            style={{ left: `${xPosition}%`, top: `${yPosition}%` }}
          />
        </div>
        <div className="z-meter-wrap">
          <span>+Z</span>
          <div className="z-meter" aria-label="Z-Bewegungsbalken">
            <span className="z-zero" />
            <span
              className={`z-fill ${zOffset < 0 ? "is-negative" : ""}`}
              style={{
                height: `${Math.abs(zOffset)}%`,
                bottom: zOffset >= 0 ? "50%" : `${50 + zOffset}%`,
              }}
            />
            <span
              className="z-marker"
              style={{ bottom: `${50 + zOffset}%` }}
            />
          </div>
          <span>−Z</span>
        </div>
      </div>
      <div className="motion-values">
        <span>X <strong>{formatMotion(displayedX)}</strong></span>
        <span>Y <strong>{formatMotion(displayedY)}</strong></span>
        <span>Z <strong>{formatMotion(displayedZ)}</strong></span>
        <small>m/s² · Offset/Schwerkraft entfernt</small>
      </div>
      <div className="chart-footer">
        <span>Skala ±{formatNumber(scale / 1000, 0)} m/s²</span>
        <LiveIndicator isLive={isLive} idleLabel={idleLabel} />
      </div>
    </article>
  );
}

function StateDot({ state }: { state: SignalState }) {
  return (
    <span className={`state-dot state-${state}`}>
      <span aria-hidden="true" />
      {STATUS_LABEL[state]}
    </span>
  );
}

export default function Home() {
  const [status, setStatus] = useState<DashboardStatus>(EMPTY_STATUS);
  const [history, setHistory] = useState<PlotPoint[]>([]);
  const smoothedSensors = useRef<SmoothedSensorValues>({
    pressure: null,
    motionX: null,
    motionY: null,
    motionZ: null,
    rmsX: null,
    rmsY: null,
    rmsZ: null,
  });
  const [profiles, setProfiles] =
    useState<MaterialProfile[]>(DEFAULT_PROFILES);
  const [selectedId, setSelectedId] = useState("pla");
  const [saved, setSaved] = useState(false);
  const [armConfirming, setArmConfirming] = useState(false);
  const [controlBusy, setControlBusy] = useState(false);
  const [controlMessage, setControlMessage] = useState("");
  const [captureBusy, setCaptureBusy] = useState(false);
  const [captureMessage, setCaptureMessage] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [sweepRStart, setSweepRStart] = useState("0.2");
  const [sweepRStop, setSweepRStop] = useState("1.4");
  const [sweepRStep, setSweepRStep] = useState("0.2");
  const [sweepCycles, setSweepCycles] = useState("5");
  const [sweepConfirming, setSweepConfirming] = useState(false);
  const [sweepBusy, setSweepBusy] = useState(false);
  const [sweepMessage, setSweepMessage] = useState("");
  // Stage 1: pressure advance. It has to settle before retraction is
  // measured, because PA decides how much pressure stands in the nozzle at
  // the moment a retraction starts.
  const [paKStart, setPaKStart] = useState("0.01");
  const [paKStop, setPaKStop] = useState("0.09");
  const [paKStep, setPaKStep] = useState("0.01");
  const [paCycles, setPaCycles] = useState("5");
  // Without a prime every stage starts from whatever the previous one
  // left in the nozzle, and a long retraction leaves it empty. The
  // generator also re-primes between candidates so the error cannot
  // compound down the sweep.
  const [primeE, setPrimeE] = useState("10");
  const [paConfirming, setPaConfirming] = useState(false);
  const [paBusy, setPaBusy] = useState(false);
  const [paMessage, setPaMessage] = useState("");
  // Stage 3: retraction speed, held at the length stage 2 settled on.
  const [speedVStart, setSpeedVStart] = useState("20");
  const [speedVStop, setSpeedVStop] = useState("60");
  const [speedVStep, setSpeedVStep] = useState("10");
  const [speedConfirming, setSpeedConfirming] = useState(false);
  const [saveConfirmStage, setSaveConfirmStage] = useState<
    string | null
  >(null);

  useEffect(() => {
    const stored =
      window.localStorage.getItem("autopa-material-profiles-v3") ??
      window.localStorage.getItem("autopa-material-profiles-v2");
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as Array<
          Partial<MaterialProfile> & Pick<MaterialProfile, "name">
        >;
        if (Array.isArray(parsed) && parsed.length) {
          const migrated = parsed.map((profile, index) => {
            const basis =
              DEFAULT_PROFILES.find(
                (candidate) => candidate.name === profile.name,
              ) ?? DEFAULT_PROFILES[0];
            return {
              ...basis,
              ...profile,
              id:
                profile.id ??
                `migrated-${index}-${profile.name.toLowerCase()}`,
              filterEnabled: Boolean(profile.filterEnabled ?? false),
              filterTag:
                profile.filterTag ??
                `[${profile.name.toUpperCase().replaceAll(" ", "_")}]`,
              filterFan: profile.filterFan ?? "chamber_filter",
              filterSpeedPercent: profile.filterSpeedPercent ?? 100,
              filterPostRunMinutes: profile.filterPostRunMinutes ?? 20,
            };
          });
          setProfiles(migrated);
          setSelectedId(migrated[0].id);
        }
      } catch {
        // Invalid local preferences fall back to the documented defaults.
      }
    }
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch("api/status", { cache: "no-store" });
        if (!response.ok) throw new Error("status unavailable");
        const next = (await response.json()) as DashboardStatus;
        try {
          const sweepResponse = await fetch("api/sweep", { cache: "no-store" });
          if (sweepResponse.ok) next.sweep = await sweepResponse.json();
        } catch {
          // Sweep status is optional; the card keeps its previous state.
        }
        try {
          const paResponse = await fetch("api/pa-sweep", {
            cache: "no-store",
          });
          if (paResponse.ok) next.paSweep = await paResponse.json();
        } catch {
          // Same as above: stage 1 keeps its previous state.
        }
        if (!active) return;
        const previous = smoothedSensors.current;
        const displayed = {
          pressure: smoothDisplayValue(
            previous.pressure,
            next.sensors.alps.normalized,
          ),
          motionX: smoothDisplayValue(
            previous.motionX,
            next.sensors.accelerometer.motionX,
          ),
          motionY: smoothDisplayValue(
            previous.motionY,
            next.sensors.accelerometer.motionY,
          ),
          motionZ: smoothDisplayValue(
            previous.motionZ,
            next.sensors.accelerometer.motionZ,
          ),
          rmsX: smoothDisplayValue(
            previous.rmsX,
            next.sensors.accelerometer.rmsX,
          ),
          rmsY: smoothDisplayValue(
            previous.rmsY,
            next.sensors.accelerometer.rmsY,
          ),
          rmsZ: smoothDisplayValue(
            previous.rmsZ,
            next.sensors.accelerometer.rmsZ,
          ),
        };
        smoothedSensors.current = displayed;
        setStatus({
          ...next,
          sensors: {
            ...next.sensors,
            alps: {
              ...next.sensors.alps,
              normalized: displayed.pressure,
            },
            accelerometer: {
              ...next.sensors.accelerometer,
              motionX: displayed.motionX,
              motionY: displayed.motionY,
              motionZ: displayed.motionZ,
              rmsX: displayed.rmsX,
              rmsY: displayed.rmsY,
              rmsZ: displayed.rmsZ,
            },
          },
        });
        setHistory((current) => [
          ...current,
          {
            pressure: next.sensors.alps.normalized ?? 0,
            motionX: next.sensors.accelerometer.motionX ?? 0,
            motionY: next.sensors.accelerometer.motionY ?? 0,
            motionZ: next.sensors.accelerometer.motionZ ?? 0,
            temperature: next.printer.temperature ?? 0,
            target: next.printer.target ?? 0,
          },
        ].slice(-60));
      } catch {
        if (!active) return;
        setStatus((current) => ({
          ...current,
          demo: false,
          printer: {
            ...current.printer,
            connected: false,
            state: "Dashboard-Backend nicht erreichbar",
          },
          quality: {
            state: "error",
            message: "Lokalen AutoPA-Dienst prüfen",
          },
        }));
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const selectedProfile =
    profiles.find((profile) => profile.id === selectedId) ?? profiles[0];

  const updateProfile = (
    field: keyof MaterialProfile,
    value: string | boolean,
  ) => {
    const parsed =
      field === "filterEnabled"
        ? Boolean(value)
        : field === "id" ||
            field === "name" ||
            field === "manufacturer" ||
            field === "filterTag" ||
            field === "filterFan"
          ? value
          : Number(value);
    setProfiles((current) =>
      current.map((profile) =>
        profile.id === selectedId
          ? { ...profile, [field]: parsed }
          : profile,
      ),
    );
    setSaved(false);
    setProfileMessage("");
  };

  const saveProfiles = async () => {
    window.localStorage.setItem(
      "autopa-material-profiles-v3",
      JSON.stringify(profiles),
    );
    setProfileMessage("");
    try {
      const response = await fetch("api/filter/config", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profiles: profiles.map((profile) => ({
            id: profile.id,
            name: profile.name,
            filter_enabled: profile.filterEnabled,
            filter_tag: profile.filterTag,
            filter_fan: profile.filterFan,
            filter_speed_percent: profile.filterSpeedPercent,
            filter_post_run_minutes: profile.filterPostRunMinutes,
          })),
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(
          result.error ?? "Filterprofil konnte nicht gespeichert werden",
        );
      }
      setStatus((current) => ({ ...current, chamberFilter: result }));
      setSaved(true);
      setProfileMessage(
        result.allowCommands
          ? "Profile und Filterregeln gespeichert."
          : "Filterregeln gespeichert; automatische Lüfterbefehle sind serverseitig gesperrt.",
      );
      window.setTimeout(() => setSaved(false), 1800);
    } catch (error) {
      setSaved(false);
      setProfileMessage(
        error instanceof Error
          ? error.message
          : "Filterprofil konnte nicht gespeichert werden",
      );
    }
  };

  const addProfile = () => {
    const existingNames = new Set(profiles.map((profile) => profile.name));
    let suffix = 1;
    let name = "Eigenes Material";
    while (existingNames.has(name)) {
      suffix += 1;
      name = `Eigenes Material ${suffix}`;
    }
    const id = `custom-${Date.now()}`;
    const basis = selectedProfile ?? DEFAULT_PROFILES[0];
    setProfiles((current) => [
      ...current,
      {
        ...basis,
        id,
        name,
        manufacturer: "Eigenes Profil",
      },
    ]);
    setSelectedId(id);
    setSaved(false);
  };

  const removeProfile = () => {
    if (!selectedProfile || profiles.length <= 1) return;
    const remaining = profiles.filter(
      (profile) => profile.id !== selectedProfile.id,
    );
    setProfiles(remaining);
    setSelectedId(remaining[0].id);
    setSaved(false);
  };

  const cameraStreamUrl = useMemo(() => {
    if (typeof window === "undefined") return "";
    const url = new URL(window.location.href);
    // Opened directly on the dashboard port, the webcam still lives on the
    // printer's normal web port, so the relative path has to be re-based.
    if (url.port === "7126") url.port = "";
    url.pathname = "/webcam/";
    url.search = "?action=stream";
    url.hash = "";
    return url.toString();
  }, []);

  const returnToMainsail = () => {
    const mainsailUrl = new URL(window.location.href);
    if (mainsailUrl.port === "7126") mainsailUrl.port = "";
    mainsailUrl.pathname = "/";
    mainsailUrl.search = "";
    mainsailUrl.hash = "";
    window.location.assign(mainsailUrl.toString());
  };

  const postControl = async (
    path: "config" | "arm" | "disarm",
    payload: Record<string, unknown> = {},
  ) => {
    setControlBusy(true);
    setControlMessage("");
    try {
      const response = await fetch(`api/control/${path}`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Änderung abgelehnt");
      setStatus((current) => ({ ...current, control: result }));
      setControlMessage(
        path === "arm"
          ? "Validierungsmodus ist für maximal 30 Minuten bewaffnet."
          : path === "disarm"
            ? "Anwenden beendet; Dry-Run bleibt verfügbar."
            : "Reglereinstellungen gespeichert.",
      );
      if (path === "arm") setArmConfirming(false);
    } catch (error) {
      setControlMessage(
        error instanceof Error ? error.message : "Änderung fehlgeschlagen",
      );
    } finally {
      setControlBusy(false);
    }
  };

  const postCapture = async (action: "start" | "stop") => {
    setCaptureBusy(true);
    setCaptureMessage("");
    try {
      const response = await fetch(`api/capture/${action}`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error ?? "Messung konnte nicht geändert werden");
      }
      setStatus((current) => ({
        ...current,
        capture: { ...current.capture, manager: result },
      }));
      setCaptureMessage(
        action === "start"
          ? result.attachedToPrint
            ? "Live-Daten sind eingeschaltet und enden automatisch mit dem Druck."
            : "Live-Daten sind eingeschaltet. Ein neuer Druck wird automatisch erkannt."
          : "Live-Daten werden sauber ausgeschaltet.",
      );
    } catch (error) {
      setCaptureMessage(
        error instanceof Error ? error.message : "Messung fehlgeschlagen",
      );
    } finally {
      setCaptureBusy(false);
    }
  };

  const [copiedConfig, setCopiedConfig] = useState(false);

  // Klipper's SAVE_CONFIG cannot store these values: only modules that call
  // configfile.set() reach the autosave block - PID, bed mesh, probe
  // offsets, input shaper - and neither extruder.py nor
  // firmware_retraction.py does. Issuing it restarted Klipper, which
  // discards the runtime value, and wrote nothing. The config lines below do
  // work, so they are what the card offers.
  const configSnippet = useMemo(() => {
    const pa = formatNumber(status.printer.pressureAdvance, 3);
    const length = formatNumber(status.printer.retractLength, 2);
    const speed = formatNumber(status.printer.retractSpeed, 0);
    return [
      "[extruder]",
      `pressure_advance: ${pa}`,
      "",
      "[firmware_retraction]",
      `retract_length: ${length}`,
      `retract_speed: ${speed}`,
      `unretract_speed: ${speed}`,
    ].join("\n");
  }, [
    status.printer.pressureAdvance,
    status.printer.retractLength,
    status.printer.retractSpeed,
  ]);

  const copyConfigSnippet = async () => {
    try {
      await navigator.clipboard.writeText(configSnippet);
      setCopiedConfig(true);
      window.setTimeout(() => setCopiedConfig(false), 2000);
    } catch {
      // Clipboard access can be denied; the lines stay selectable by hand.
      setCopiedConfig(false);
    }
  };

  const postPaSweepRun = async () => {
    setPaBusy(true);
    setPaMessage("");
    try {
      const response = await fetch("api/pa-sweep/run", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phrase: ARM_PHRASE,
          k_start: Number(paKStart),
          k_stop: Number(paKStop),
          k_step: Number(paKStep),
          cycles: Number(paCycles),
          prime_e: Number(primeE),
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Sweep abgelehnt");
      setStatus((current) => ({ ...current, paSweep: result }));
      // No success text: the progress bar below reports the run while it
      // happens, and a leftover "Läuft …" line beside a finished result was
      // the most confusing thing on the card. Errors still persist.
      setPaMessage("");
      setPaConfirming(false);
    } catch (error) {
      setPaMessage(
        error instanceof Error ? error.message : "Sweep fehlgeschlagen",
      );
    } finally {
      setPaBusy(false);
    }
  };

  const postSweepRun = async (mode: "length" | "speed" = "length") => {
    setSweepBusy(true);
    setSweepMessage("");
    try {
      const response = await fetch("api/sweep/run", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          mode === "speed"
            ? {
                phrase: ARM_PHRASE,
                mode: "speed",
                v_start: Number(speedVStart),
                v_stop: Number(speedVStop),
                v_step: Number(speedVStep),
                cycles: Number(sweepCycles),
                prime_e: Number(primeE),
                // A speed result is reported as retract_speed_mm_s, which the
                // apply pipeline does not know how to send, so it would skip
                // anyway. Saying so explicitly keeps the intent readable.
                auto_apply: false,
              }
            : {
                phrase: ARM_PHRASE,
                r_start: Number(sweepRStart),
                r_stop: Number(sweepRStop),
                r_step: Number(sweepRStep),
                cycles: Number(sweepCycles),
                prime_e: Number(primeE),
              },
        ),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Sweep abgelehnt");
      setStatus((current) => ({ ...current, sweep: result }));
      setSweepMessage("");
      setSweepConfirming(false);
      setSpeedConfirming(false);
    } catch (error) {
      setSweepMessage(
        error instanceof Error ? error.message : "Sweep fehlgeschlagen",
      );
    } finally {
      setSweepBusy(false);
    }
  };

  // The confirmation dialogs name what is about to happen instead of asking
  // for a phrase. A prompt only protects if the operator reads it, so both
  // summaries state the concrete values and the printer phase.
  const armConfirmSummary = useMemo(() => {
    const parts: string[] = [];
    if (status.control.adaptivePAEnabled) {
      parts.push(
        `Pressure Advance ${formatNumber(status.printer.pressureAdvance, 3)} → ${formatNumber(status.control.suggestedPA, 3)}`,
      );
    }
    if (status.control.autoRetractEnabled) {
      parts.push(
        `Rückzug ${formatNumber(status.printer.retractLength, 2)} → ${formatNumber(status.control.suggestedRetractMm, 2)} mm`,
      );
    }
    const what = parts.length ? parts.join(" und ") : "nichts";
    return `Begrenztes Anwenden im laufenden Druck scharfschalten: ${what}. Höchstens 30 Minuten, schrittweise, ohne SAVE_CONFIG, beim Entschärfen wird der Ausgangswert wiederhergestellt. Wirklich scharfschalten?`;
  }, [
    status.control.adaptivePAEnabled,
    status.control.autoRetractEnabled,
    status.control.suggestedPA,
    status.control.suggestedRetractMm,
    status.printer.pressureAdvance,
    status.printer.retractLength,
  ]);

  const analysisBusy = Boolean(
    status.sweep.analysis?.busy || status.paSweep.analysis?.busy,
  );
  const sweepRunning = Boolean(
    status.sweep.running?.active || status.paSweep.running?.active,
  );
  // Why an idle stage cannot be started right now. Shown instead of the
  // start button: a disabled button still looks like an invitation.
  const stageBlockedReason = analysisBusy
    ? "Eine andere Stufe wird gerade ausgewertet. Warte, bis dort das Ergebnis steht — sonst vermischen sich die Messungen."
    : sweepRunning
      ? "Ein Sweep läuft gerade. Warte, bis er fertig ist."
      : status.printer.printState !== "standby"
        ? `Der Drucker ist „${status.printer.printState || "unbekannt"}“. Die Stufen laufen nur im Standby.`
        : null;

  const saveConfirmSummary = useMemo(
    () =>
      `Klipper kann Pressure Advance und Rückzug nicht selbst speichern — SAVE_CONFIG legt nur Werte ab, die eine Kalibrierroutine dafür anmeldet (PID, Bed Mesh, Probe-Offsets, Input Shaper). Trage diese Zeilen in deine Druckerkonfiguration ein, damit sie einen Neustart überleben:`,
    [],
  );

  const paConfirmSummary = useMemo(() => {
    const values = countSweepValues(paKStart, paKStop, paKStep);
    return `Stufe 1, Pressure Advance: K ${paKStart}–${paKStop} in Schritten von ${paKStep} (${values} Werte à ${paCycles} Zyklen). Der Drucker extrudiert dabei in freier Luft. Der aktuelle Wert K ${formatNumber(status.printer.pressureAdvance, 3)} wird am Ende wiederhergestellt. Wirklich starten?`;
  }, [paKStart, paKStop, paKStep, paCycles, status.printer.pressureAdvance]);

  const speedConfirmSummary = useMemo(() => {
    const values = countSweepValues(speedVStart, speedVStop, speedVStep);
    return `Stufe 3, Rückzugsgeschwindigkeit: ${speedVStart}–${speedVStop} mm/s in Schritten von ${speedVStep} mm/s (${values} Werte à ${sweepCycles} Zyklen), Länge fest auf ${formatNumber(status.printer.retractLength, 2)} mm. Rückzugs- und Rückfahrgeschwindigkeit werden gemeinsam gesetzt und danach beide zurückgestellt. Der Sensor erkennt kein durchrutschendes Filament — Extruder beobachten. Wirklich starten?`;
  }, [
    speedVStart,
    speedVStop,
    speedVStep,
    sweepCycles,
    status.printer.retractLength,
  ]);

  const sweepConfirmSummary = useMemo(() => {
    const values = countSweepValues(sweepRStart, sweepRStop, sweepRStep);
    return `Stufe 2, Rückzugslänge: ${sweepRStart}–${sweepRStop} mm in Schritten von ${sweepRStep} mm (${values} Werte à ${sweepCycles} Zyklen). Der Drucker extrudiert dabei in freier Luft. Der aktuelle Wert ${formatNumber(status.printer.retractLength, 2)} mm wird am Ende wiederhergestellt. Wirklich starten?`;
  }, [
    sweepRStart,
    sweepRStop,
    sweepRStep,
    sweepCycles,
    status.printer.retractLength,
  ]);

  const temperatures = useMemo(() => {
    if (!selectedProfile) return [];
    const points = [];
    for (
      let value = selectedProfile.minTemperature;
      value <= selectedProfile.maxTemperature + 0.001;
      value += selectedProfile.temperatureStep
    ) {
      points.push(Math.round(value * 10) / 10);
      if (points.length > 30) break;
    }
    return points;
  }, [selectedProfile]);

  const overallState: SignalState = !status.printer.connected
    ? "error"
    : status.quality.state;

  return (
    <>
      {/* Mounted above the page content so it keeps its viewport position
          while scrolling, and is never clipped by the layout. */}
      <CameraWindow streamUrl={cameraStreamUrl} />
      <main>
      <header className="topbar">
        <div className="brand-area">
          <button
            className="back-button"
            type="button"
            onClick={returnToMainsail}
            aria-label="Zurück zu Mainsail"
          >
            <span aria-hidden="true">←</span>
            Mainsail
          </button>
          <div className="brand">
            <span className="brand-mark">A</span>
            <div>
              <strong>AutoPA</strong>
              <span>Pressure Intelligence</span>
            </div>
          </div>
        </div>
        <div className="topbar-right">
          {status.demo && <span className="demo-badge">Vorschaudaten</span>}
          <span className="clock">
            {new Date(status.timestamp).toLocaleTimeString("de-DE")}
          </span>
          <StateDot state={status.printer.connected ? "ok" : "error"} />
        </div>
      </header>

      <section className="overview">
        <div className="overview-copy">
          <p className="eyebrow">Systemzustand</p>
          <div className="status-title">
            <span className={`status-orb state-${overallState}`} />
            <h1>
              {overallState === "ok"
                ? "Alles im grünen Bereich"
                : overallState === "waiting"
                  ? "Bereit für eine Messung"
                  : overallState === "warning"
                    ? "Messung bitte prüfen"
                    : "Verbindung prüfen"}
            </h1>
          </div>
          <p>{status.quality.message}</p>
        </div>
        <div className="overview-metrics">
          <div>
            <span>Hotend</span>
            <strong>{formatNumber(status.printer.temperature)} °C</strong>
            <small>Ziel {formatNumber(status.printer.target)} °C</small>
          </div>
          <div>
            <span>Pressure Advance</span>
            <strong>{formatNumber(status.printer.pressureAdvance, 3)}</strong>
            <small>Smooth {formatNumber(status.printer.smoothTime, 3)} s</small>
          </div>
          <div>
            <span>Drucker</span>
            <strong>{status.printer.printState}</strong>
            <small>{status.printer.state}</small>
          </div>
          <div>
            <span>Düsenprofil</span>
            <strong>
              {formatNumber(status.printer.nozzleDiameter, 2)} mm
            </strong>
            <small>
              Filament {formatNumber(status.printer.filamentDiameter, 2)} mm
            </small>
          </div>
        </div>
      </section>

      <div className="dashboard-grid">
        <section className="signals">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Live-Signale</p>
              <h2>Was gerade an der Düse passiert</h2>
            </div>
            <span className="window-label">60-Sekunden-Fenster</span>
          </div>
          <div className="chart-grid">
            <PressureSignalCard
              normalized={status.sensors.alps.normalized}
              delta={status.sensors.alps.delta}
              isLive={
                status.capture.state === "ok" &&
                status.sensors.alps.state === "ok"
              }
            />
            <MotionVectorCard
              sensorType={status.sensors.accelerometer.type}
              enabled={status.sensors.accelerometer.enabled}
              x={status.sensors.accelerometer.motionX}
              y={status.sensors.accelerometer.motionY}
              z={status.sensors.accelerometer.motionZ}
              rmsX={status.sensors.accelerometer.rmsX}
              rmsY={status.sensors.accelerometer.rmsY}
              rmsZ={status.sensors.accelerometer.rmsZ}
              history={history}
              isLive={
                status.capture.state === "ok" &&
                status.sensors.accelerometer.enabled &&
                status.sensors.accelerometer.state === "ok"
              }
            />
            <LineChart
              eyebrow="HOTEND"
              title="Temperatur"
              values={history.map((point) => point.temperature)}
              color="#ffbd69"
              value={formatNumber(status.printer.temperature)}
              unit="°C"
              isLive={status.printer.connected}
            />
          </div>

          <div className="pressure-control-grid">
            <article className="context-card">
              <div className="section-heading compact">
                <div>
                  <p className="eyebrow">G-Code Context Engine</p>
                  <h2>Aktuell ausgeführter Druckkontext</h2>
                </div>
                <span
                  className={`live-indicator ${
                    status.control.gcodeContext?.active ? "is-live" : ""
                  }`}
                  aria-label={
                    status.control.gcodeContext?.active
                      ? "G-Code-Kontext live"
                      : "Kein G-Code-Kontext"
                  }
                >
                  <span />
                  {status.control.gcodeContext?.active ? "Live" : "Wartet"}
                </span>
              </div>
              <div className="context-values">
                <div>
                  <span>Layer</span>
                  <strong>
                    {status.control.gcodeContext?.layer ?? "—"}
                    {status.control.gcodeContext?.z_mm != null
                      ? ` · Z ${formatNumber(
                          status.control.gcodeContext.z_mm,
                          2,
                        )} mm`
                      : ""}
                    {status.control.gcodeContext?.source_line != null
                      ? ` · Zeile ${status.control.gcodeContext.source_line}`
                      : ""}
                  </strong>
                </div>
                <div>
                  <span>Feature</span>
                  <strong>
                    {FEATURE_LABELS[
                      status.control.gcodeContext?.feature ?? "unknown"
                    ] ?? status.control.gcodeContext?.feature ?? "Unbekannt"}
                  </strong>
                </div>
                <div>
                  <span>Objekt</span>
                  <strong>
                    {status.control.gcodeContext?.object ?? "Nicht angegeben"}
                  </strong>
                </div>
                <div>
                  <span>Druckgeschwindigkeit</span>
                  <strong>
                    {formatNumber(status.control.toolheadVelocityMmS, 1)} mm/s
                  </strong>
                </div>
                <div>
                  <span>Extruderbewegung</span>
                  <strong>
                    {formatNumber(status.control.extruderVelocityMmS, 2)} mm/s
                  </strong>
                </div>
                <div>
                  <span>Volumenstrom</span>
                  <strong>
                    {formatNumber(status.control.volumetricFlowMm3S, 2)} mm³/s
                  </strong>
                </div>
              </div>
              <p
                className={`context-window ${
                  status.control.paContextEligible ? "eligible" : ""
                }`}
              >
                {CONTEXT_REASON_LABELS[
                  status.control.gcodeContext?.eligibility_reason ?? ""
                ] ?? "Kontext fehlt – PA bleibt unverändert"}
              </p>
            </article>
            <article className="adaptive-card">
              <div className="section-heading compact">
                <div>
                  <p className="eyebrow">Kalibrierung in drei Stufen</p>
                  <h2>Druckabstimmung</h2>
                </div>
                <span className="safety-note">
                  {status.printer.printState === "standby"
                    ? "Standby – Stufen 1–3 möglich"
                    : `Drucker: ${status.printer.printState || "unbekannt"}`}
                </span>
              </div>

              <p className="card-intro">
                Der FLY-ALPS misst die Kraft an der Düse mit etwa 2.600
                Messwerten pro Sekunde. Daraus lässt sich ablesen, wie schnell
                der Druck in der Schmelzkammer auf- und abgebaut wird — genau
                das, was Pressure Advance und der Rückzug beeinflussen.
              </p>
              <p className="card-intro">
                Die drei Stufen laufen <strong>im Standby</strong>, mit der
                Düse frei in der Luft. Es wird nichts gedruckt, sondern nur
                extrudiert und gemessen. Die Reihenfolge ist nicht beliebig:
                Pressure Advance bestimmt, wie viel Druck im Moment eines
                Rückzugs überhaupt ansteht — wer den Rückzug bei falschem PA
                misst, optimiert für einen Zustand, den es später nicht gibt.
              </p>
              <p className="card-intro">
                Lege eine Auffangmöglichkeit unter die Düse. Jede Stufe stellt
                den Ausgangswert am Ende selbst wieder her.
              </p>
              <p className="card-intro">
                <strong>Vorfüllen</strong> gilt für alle Stufen: Vor dem ersten
                Messzyklus <em>und</em> zwischen je zwei Kandidatenwerten wird
                die Düse neu gefüllt. Ohne das startet jeder Wert aus dem
                Zustand, den der vorige hinterlassen hat — ein langer Rückzug
                leert die Kammer, der nächste Wert misst dann ins Leere und der
                Fehler schaukelt sich über den Sweep auf.
              </p>

              <div className="field-group two">
                <label>
                  Vorfüllen
                  <span>
                    <input
                      type="number"
                      min="0"
                      max="20"
                      step="1"
                      value={primeE}
                      onChange={(event) => setPrimeE(event.target.value)}
                    />
                    mm
                  </span>
                </label>
                <label>
                  Live-Daten
                  <span className="field-hint">
                    {status.capture.manager?.active
                      ? "laufen — werden für den Sweep kurz übernommen"
                      : "aus"}
                  </span>
                </label>
              </div>

              {analysisBusy && (
                <p className="control-note warn">
                  Eine Auswertung läuft gerade. Die Stufen sind so lange
                  gesperrt, damit sich die Messungen nicht vermischen.
                </p>
              )}

              <div className="phase-divider">
                <span>Stufe 1 · Pressure Advance</span>
              </div>

              <p className="control-note">
                Fährt jeden K-Wert mit einer langsamen und einer schnellen
                Extrusionsbewegung an. Der Sensor zeigt, bei welchem Wert der
                Düsendruck der Bewegung am saubersten folgt, ohne
                nachzulaufen oder zu überschwingen. Aktuell steht der Drucker
                auf K&nbsp;{formatNumber(status.printer.pressureAdvance, 3)}.
              </p>

              <div className="field-group two">
                <label>
                  Von
                  <span>
                    <input
                      type="number"
                      min="0"
                      max="0.2"
                      step="0.005"
                      value={paKStart}
                      onChange={(event) => setPaKStart(event.target.value)}
                    />
                    K
                  </span>
                </label>
                <label>
                  Bis
                  <span>
                    <input
                      type="number"
                      min="0"
                      max="0.2"
                      step="0.005"
                      value={paKStop}
                      onChange={(event) => setPaKStop(event.target.value)}
                    />
                    K
                  </span>
                </label>
              </div>
              <div className="field-group two">
                <label>
                  Schritt
                  <span>
                    <input
                      type="number"
                      min="0.001"
                      max="0.1"
                      step="0.001"
                      value={paKStep}
                      onChange={(event) => setPaKStep(event.target.value)}
                    />
                    K
                  </span>
                </label>
                <label>
                  Zyklen je Wert
                  <span>
                    <input
                      type="number"
                      min="3"
                      max="30"
                      step="1"
                      value={paCycles}
                      onChange={(event) => setPaCycles(event.target.value)}
                    />
                  </span>
                </label>
              </div>

              {paConfirming ? (
                <div className="confirm-box">
                  <p>{paConfirmSummary}</p>
                  <div className="confirm-actions">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={paBusy}
                      onClick={postPaSweepRun}
                    >
                      Ja, Stufe 1 starten
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setPaConfirming(false)}
                    >
                      Abbrechen
                    </button>
                  </div>
                </div>
              ) : (
                <StageAction
                  applied={Boolean(status.paSweep.lastApply?.applied)}
                  busy={paBusy}
                  disabled={
                    analysisBusy ||
                    !status.paSweep.allowPrinterCommands ||
                    status.printer.printState !== "standby"
                  }
                  startLabel="Stufe 1 starten …"
                  onStart={() => setPaConfirming(true)}
                  onSave={() => setSaveConfirmStage("pa")}
                  confirmingSave={saveConfirmStage === "pa"}
                  saveSummary={saveConfirmSummary}
                  configSnippet={configSnippet}
                  onCopyConfig={copyConfigSnippet}
                  copied={copiedConfig}
                  onSaveCancel={() => setSaveConfirmStage(null)}
                  blockedReason={stageBlockedReason}
                  running={status.paSweep.running}
                  analyzing={Boolean(
                    status.paSweep.analysis?.busy && status.paSweep.analysis?.stage === "pa"
                  )}
                  analysisPercent={status.paSweep.analysis?.percent}
                  analysisSeconds={status.paSweep.analysis?.secondsRemaining}
                  analysisStep={status.paSweep.analysis?.step}
                />
              )}
              {status.paSweep.lastRun && (
                <p className="control-message">
                  Letzter Lauf: {status.paSweep.lastRun.kValues?.length ?? "?"}{" "}
                  K-Werte à {status.paSweep.lastRun.cycles} Zyklen
                </p>
              )}
              <StageChart
                analysis={status.paSweep.lastAnalysis}
                unit="K"
              />
              <StageResult
                apply={status.paSweep.lastApply}
                unit="K"
                analyzing={
                  status.paSweep.analysis?.busy &&
                  status.paSweep.analysis?.stage === "pa"
                }
                ranSomething={!!status.paSweep.lastRun}
              />
              {paMessage && <p className="control-message">{paMessage}</p>}
              {status.paSweep.lastError && (
                <p className="control-error">{status.paSweep.lastError}</p>
              )}

              <div className="phase-divider">
                <span>Stufe 2 · Rückzugslänge</span>
              </div>

              <p className="control-note">
                Zieht das Filament um jeden Kandidatenwert zurück, wartet eine
                Sekunde und fährt wieder an. In der Wartezeit zeigt der Sensor,
                wie viel Druck in der Düse übrig bleibt — zu wenig Rückzug
                heißt Nachsickern und Fäden, zu viel heißt Lufteinschluss und
                eine Lücke beim Wiederanfahren. Aktuell steht der Drucker auf{" "}
                {formatNumber(status.printer.retractLength, 2)} mm.
              </p>

              <div className="field-group two">
                <label>
                  Von
                  <span>
                    <input
                      type="number"
                      min="0"
                      max="5"
                      step="0.1"
                      value={sweepRStart}
                      onChange={(event) => setSweepRStart(event.target.value)}
                    />
                    mm
                  </span>
                </label>
                <label>
                  Bis
                  <span>
                    <input
                      type="number"
                      min="0.05"
                      max="10"
                      step="0.1"
                      value={sweepRStop}
                      onChange={(event) => setSweepRStop(event.target.value)}
                    />
                    mm
                  </span>
                </label>
              </div>
              <div className="field-group two">
                <label>
                  Schritt
                  <span>
                    <input
                      type="number"
                      min="0.01"
                      max="2"
                      step="0.01"
                      value={sweepRStep}
                      onChange={(event) => setSweepRStep(event.target.value)}
                    />
                    mm
                  </span>
                </label>
                <label>
                  Zyklen je Wert
                  <span>
                    <input
                      type="number"
                      min="3"
                      max="30"
                      step="1"
                      value={sweepCycles}
                      onChange={(event) => setSweepCycles(event.target.value)}
                    />
                  </span>
                </label>
              </div>

              {sweepConfirming ? (
                <div className="confirm-box">
                  <p>{sweepConfirmSummary}</p>
                  <div className="confirm-actions">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={sweepBusy}
                      onClick={() => postSweepRun("length")}
                    >
                      Ja, Stufe 2 starten
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setSweepConfirming(false)}
                    >
                      Abbrechen
                    </button>
                  </div>
                </div>
              ) : (
                <StageAction
                  applied={Boolean(status.sweep.lastApplyByMode?.length?.applied)}
                  busy={sweepBusy}
                  disabled={
                    analysisBusy ||
                    !status.sweep.allowPrinterCommands ||
                    status.printer.printState !== "standby"
                  }
                  startLabel="Stufe 2 starten …"
                  onStart={() => setSweepConfirming(true)}
                  onSave={() => setSaveConfirmStage("length")}
                  confirmingSave={saveConfirmStage === "length"}
                  saveSummary={saveConfirmSummary}
                  configSnippet={configSnippet}
                  onCopyConfig={copyConfigSnippet}
                  copied={copiedConfig}
                  onSaveCancel={() => setSaveConfirmStage(null)}
                  blockedReason={stageBlockedReason}
                  running={status.sweep.running}
                  analyzing={Boolean(
                    status.sweep.analysis?.busy &&
                    status.sweep.analysis?.stage === "retract" &&
                    status.sweep.lastRun?.mode !== "speed"
                  )}
                  analysisPercent={status.sweep.analysis?.percent}
                  analysisSeconds={status.sweep.analysis?.secondsRemaining}
                  analysisStep={status.sweep.analysis?.step}
                />
              )}

              {status.printer.printState !== "standby" && (
                <p className="control-error">
                  Gesperrt: Drucker ist „{status.printer.printState || "unbekannt"}
                  “ — der Sweep läuft nur im Standby und wird während eines
                  Drucks serverseitig abgelehnt.
                </p>
              )}

              <p className="control-note">
                Erzeugt den markierten G10/G11-Sweep im Speicher und sendet ihn
                direkt an Moonraker — keine G-Code-Datei nötig. Der aktuelle
                Wert ({formatNumber(status.printer.retractLength, 2)} mm) wird
                am Ende wiederhergestellt. Nur im Standby: Düse ≥ 10 mm über
                dem Bett, Auffangbehälter, Recorder vorher starten und am
                Drucker bleiben.
              </p>
              {status.sweep.lastRun && (
                <p className="control-message">
                  Letzter Lauf ({status.sweep.lastRun.mode === "speed"
                    ? "Geschwindigkeit"
                    : "Länge"}
                  ):{" "}
                  {(status.sweep.lastRun.mode === "speed"
                    ? status.sweep.lastRun.speedValues
                    : status.sweep.lastRun.retractValues
                  )?.join(", ") ?? "—"}{" "}
                  {status.sweep.lastRun.mode === "speed" ? "mm/s" : "mm"} à{" "}
                  {status.sweep.lastRun.cycles} Zyklen
                </p>
              )}
              <StageChart
                analysis={status.sweep.lastAnalysisByMode?.length}
                unit="mm"
              />
              <StageResult
                apply={status.sweep.lastApplyByMode?.length ?? null}
                unit="mm"
                analyzing={
                  status.sweep.analysis?.busy &&
                  status.sweep.analysis?.stage === "retract" &&
                  status.sweep.lastRun?.mode !== "speed"
                }
                ranSomething={!!status.sweep.lastRunByMode?.length}
              />
              {sweepMessage && <p className="control-message">{sweepMessage}</p>}
              {status.sweep.lastError && (
                <p className="control-error">{status.sweep.lastError}</p>
              )}

              <div className="phase-divider">
                <span>Stufe 3 · Rückzugsgeschwindigkeit</span>
              </div>

              <p className="control-note">
                Hält die Länge auf dem Druckerwert (
                {formatNumber(status.printer.retractLength, 2)} mm) und
                variiert stattdessen, wie schnell gezogen wird. Wie zäh die
                Schmelze ist, hängt stark vom Material ab — dieselbe Länge
                wirkt bei PETG anders als bei PLA. Bewertet wird vor allem das
                Wiederanfahren nach <code>G11</code>: zu langsam heißt
                Unterextrusion, zu schnell heißt Druckspitze und Blob.
              </p>
              <p className="control-note warn">
                Wichtig: Der Sensor kann <strong>kein durchrutschendes oder
                angefrästes Filament erkennen</strong> — dafür fehlt ein
                Encoder. Eine zu hohe Geschwindigkeit kann druckseitig sauber
                aussehen und trotzdem den Antrieb schädigen. Beobachte den
                Extruder während des Laufs. Das Ergebnis wird deshalb auch
                <strong> nie automatisch übernommen</strong>.
              </p>

              <div className="field-group two">
                <label>
                  Von
                  <span>
                    <input
                      type="number"
                      min="5"
                      max="120"
                      step="5"
                      value={speedVStart}
                      onChange={(event) => setSpeedVStart(event.target.value)}
                    />
                    mm/s
                  </span>
                </label>
                <label>
                  Bis
                  <span>
                    <input
                      type="number"
                      min="5"
                      max="120"
                      step="5"
                      value={speedVStop}
                      onChange={(event) => setSpeedVStop(event.target.value)}
                    />
                    mm/s
                  </span>
                </label>
              </div>
              <div className="field-group two">
                <label>
                  Schritt
                  <span>
                    <input
                      type="number"
                      min="1"
                      max="40"
                      step="1"
                      value={speedVStep}
                      onChange={(event) => setSpeedVStep(event.target.value)}
                    />
                    mm/s
                  </span>
                </label>
                <label>
                  Zyklen je Wert
                  <span>
                    <input
                      type="number"
                      min="3"
                      max="30"
                      step="1"
                      value={sweepCycles}
                      onChange={(event) => setSweepCycles(event.target.value)}
                    />
                  </span>
                </label>
              </div>

              {speedConfirming ? (
                <div className="confirm-box">
                  <p>{speedConfirmSummary}</p>
                  <div className="confirm-actions">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={sweepBusy}
                      onClick={() => postSweepRun("speed")}
                    >
                      Ja, Stufe 3 starten
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setSpeedConfirming(false)}
                    >
                      Abbrechen
                    </button>
                  </div>
                </div>
              ) : (
                <StageAction
                  applied={Boolean(status.sweep.lastApplyByMode?.speed?.applied)}
                  busy={sweepBusy}
                  disabled={
                    analysisBusy ||
                    !status.sweep.allowPrinterCommands ||
                    status.printer.printState !== "standby"
                  }
                  startLabel="Stufe 3 starten …"
                  onStart={() => setSpeedConfirming(true)}
                  onSave={() => setSaveConfirmStage("speed")}
                  confirmingSave={saveConfirmStage === "speed"}
                  saveSummary={saveConfirmSummary}
                  configSnippet={configSnippet}
                  onCopyConfig={copyConfigSnippet}
                  copied={copiedConfig}
                  onSaveCancel={() => setSaveConfirmStage(null)}
                  blockedReason={stageBlockedReason}
                  running={status.sweep.running}
                  analyzing={Boolean(
                    status.sweep.analysis?.busy &&
                    status.sweep.analysis?.stage === "retract" &&
                    status.sweep.lastRun?.mode === "speed"
                  )}
                  analysisPercent={status.sweep.analysis?.percent}
                  analysisSeconds={status.sweep.analysis?.secondsRemaining}
                  analysisStep={status.sweep.analysis?.step}
                />
              )}
              <StageChart
                analysis={status.sweep.lastAnalysisByMode?.speed}
                unit="mm/s"
              />
              <StageResult
                apply={status.sweep.lastApplyByMode?.speed ?? null}
                unit="mm/s"
                analyzing={
                  status.sweep.analysis?.busy &&
                  status.sweep.analysis?.stage === "retract" &&
                  status.sweep.lastRun?.mode === "speed"
                }
                ranSomething={!!status.sweep.lastRunByMode?.speed}
              />

              <div className="phase-divider">
                <span>Zum Schluss · nur im laufenden Druck</span>
              </div>

              <div className="section-heading compact">
                <div>
                  <p className="eyebrow">Experimenteller Validierungsmodus</p>
                  <h2>Adaptive PA & Auto-Retract</h2>
                </div>
                <span className={`control-mode mode-${status.control.mode}`}>
                  {status.control.mode === "apply"
                    ? "BEWAFFNET"
                    : status.control.mode === "dry_run"
                      ? "DRY-RUN"
                      : "AUS"}
                </span>
              </div>

              <p className="control-note">
                Kein Sweep, sondern ein Nachregler: Er beobachtet die Rückzüge,
                die dein Slicer im echten Druck ohnehin auslöst, und schiebt
                den Wert schrittweise nach. Gedacht für Drift durch Material,
                Feuchte oder Temperatur — nicht für die Grundeinstellung.
              </p>
              <p className="control-note warn">
                Seine Reichweite ist bewusst winzig: Pressure Advance insgesamt
                <strong> ±0,01</strong>, Rückzug <strong>±0,30 mm</strong>.
                Steht PA auf 0,040 und das Optimum liegt bei 0,060, kommt er
                nie darüber hinaus. Ohne die Stufen 1–3 vorher läuft er also
                ins Leere — erst messen, dann nachführen.
              </p>

              <div className="control-toggles">
                <label>
                  <input
                    type="checkbox"
                    checked={status.control.adaptivePAEnabled}
                    disabled={controlBusy}
                    onChange={(event) =>
                      postControl("config", {
                        mode:
                          status.control.mode === "off"
                            ? "dry_run"
                            : status.control.mode,
                        adaptive_pa_enabled: event.target.checked,
                        auto_retract_enabled:
                          status.control.autoRetractEnabled,
                      })
                    }
                  />
                  <span>
                    <strong>Adaptive PA</strong>
                    <small>
                      {formatNumber(status.printer.pressureAdvance, 3)} →{" "}
                      {formatNumber(status.control.suggestedPA, 3)}
                    </small>
                  </span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={status.control.autoRetractEnabled}
                    disabled={
                      controlBusy ||
                      !status.printer.firmwareRetractionAvailable
                    }
                    onChange={(event) =>
                      postControl("config", {
                        mode:
                          status.control.mode === "off"
                            ? "dry_run"
                            : status.control.mode,
                        adaptive_pa_enabled:
                          status.control.adaptivePAEnabled,
                        auto_retract_enabled: event.target.checked,
                      })
                    }
                  />
                  <span>
                    <strong>Auto-Retract</strong>
                    <small>
                      {status.printer.firmwareRetractionAvailable
                        ? `${formatNumber(status.printer.retractLength, 2)} → ${formatNumber(status.control.suggestedRetractMm, 2)} mm`
                        : "Benötigt [firmware_retraction] und G10/G11"}
                    </small>
                  </span>
                </label>
              </div>

              <div className="control-evidence">
                <span>PA-Fenster <strong>{status.control.paWindows}</strong></span>
                <span>
                  Retract-Ereignisse{" "}
                  <strong>{status.control.retractEvents}</strong>
                </span>
                <span>
                  Änderungen <strong>{status.control.commandCount}</strong>
                </span>
              </div>

              <div className="control-actions">
                <button
                  type="button"
                  className="secondary-button"
                  disabled={controlBusy}
                  onClick={() =>
                    postControl("config", {
                      mode: "dry_run",
                      adaptive_pa_enabled:
                        status.control.adaptivePAEnabled,
                      auto_retract_enabled:
                        status.control.autoRetractEnabled,
                    })
                  }
                >
                  Dry-Run starten
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={controlBusy}
                  onClick={() => postControl("config", { mode: "off" })}
                >
                  Ausschalten
                </button>
              </div>

              {armConfirming ? (
                <div className="confirm-box">
                  <p>{armConfirmSummary}</p>
                  <div className="confirm-actions">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={controlBusy}
                      onClick={() =>
                        postControl("arm", { phrase: ARM_PHRASE })
                      }
                    >
                      Ja, scharfschalten
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setArmConfirming(false)}
                    >
                      Abbrechen
                    </button>
                  </div>
                </div>
              ) : (
                <div className="arming-row">
                  {status.control.armed ? (
                    <button
                      type="button"
                      className="danger-button"
                      disabled={controlBusy}
                      onClick={() => postControl("disarm")}
                    >
                      Anwenden beenden
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="primary-button"
                      disabled={
                        controlBusy || !status.control.allowPrinterCommands
                      }
                      onClick={() => setArmConfirming(true)}
                    >
                      Begrenzt anwenden …
                    </button>
                  )}
                </div>
              )}

              <p className="control-note">
                Keine Pause, kein Abbruch und kein SAVE_CONFIG. Änderungen sind
                zeitlich begrenzt, schrittweise und nur während „printing“
                erlaubt. Status: {status.control.reason ?? "—"}
              </p>
              {controlMessage && <p className="control-message">{controlMessage}</p>}
              {status.control.lastError && (
                <p className="control-error">{status.control.lastError}</p>
              )}

              <div className="phase-divider">
                <span>Werte dauerhaft machen</span>
              </div>

              <p className="control-note">
                Jede Übernahme oben gilt <strong>nur zur Laufzeit</strong>.
                Nach einem Klipper-Neustart stehen wieder die Werte aus deiner
                Konfiguration. Aktuell aktiv: PA{" "}
                {formatNumber(status.printer.pressureAdvance, 3)}, Rückzug{" "}
                {formatNumber(status.printer.retractLength, 2)} mm bei{" "}
                {formatNumber(status.printer.retractSpeed, 0)} mm/s.
              </p>
              <p className="control-note warn">
                <strong>Klipper kann diese beiden Werte nicht selbst
                speichern.</strong> `SAVE_CONFIG` schreibt nur, was eine
                Kalibrierroutine dafür anmeldet — PID, Bed Mesh,
                Probe-Offsets, Input Shaper. Pressure Advance und
                Firmware-Rückzug gehören nicht dazu. Ein `SAVE_CONFIG` würde
                Klipper neu starten und dabei genau den Laufzeitwert
                verwerfen, den du behalten wolltest. Nutze stattdessen den
                Knopf an der jeweiligen Stufe: er zeigt die Zeilen zum
                Eintragen.
              </p>
            </article>
          </div>

          <div className="health-card">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Messkette</p>
                <h2>Bereitschaft & Datenqualität</h2>
              </div>
              <span className="safety-note">
                {status.control.mode === "apply"
                  ? "Begrenzt und ausdrücklich bewaffnet"
                  : "Keine automatische Druckaktion"}
              </span>
            </div>
            <div className="health-rows">
              <div className="health-row">
                <div>
                  <strong>Klipper & Moonraker</strong>
                  <span>{status.printer.state}</span>
                </div>
                <StateDot state={status.printer.connected ? "ok" : "error"} />
              </div>
              <div className="health-row">
                <div>
                  <strong>ALPS Drucksensor</strong>
                  <span>
                    {status.sensors.alps.sampleRate
                      ? `${formatNumber(status.sensors.alps.sampleRate, 0)} Hz`
                      : "startet mit der nächsten Aufnahme"}
                  </span>
                </div>
                <StateDot state={status.sensors.alps.state} />
              </div>
              <div className="health-row">
                <div>
                  <strong>
                    {status.sensors.accelerometer.enabled
                      ? `${status.sensors.accelerometer.type.toUpperCase()} Beschleunigung`
                      : "Beschleunigungssensor (optional)"}
                  </strong>
                  <span>
                    {!status.sensors.accelerometer.enabled
                      ? "deaktiviert – Kraftanalyse bleibt verfügbar"
                      : status.sensors.accelerometer.sampleRate
                        ? `${formatNumber(
                            status.sensors.accelerometer.sampleRate,
                            0,
                          )} Hz`
                        : "startet mit der nächsten Aufnahme"}
                  </span>
                </div>
                <StateDot state={status.sensors.accelerometer.state} />
              </div>
              <div className="health-row">
                <div>
                  <strong>Synchronisierte Aufnahme</strong>
                  <span>
                    {status.capture.manager?.active
                      ? status.capture.manager.attachedToPrint
                        ? `${status.capture.dataset ?? "Datensatz"} · live bis Druckende`
                        : `${status.capture.dataset ?? "Datensatz"} · Live-Vorschau`
                      : status.capture.manager?.stopReason === "print_finished"
                        ? `${status.capture.dataset ?? "Datensatz"} · am Druckende beendet`
                        : status.capture.dataset ?? "noch kein aktiver Datensatz"}
                  </span>
                </div>
                <StateDot state={status.capture.state} />
              </div>
            </div>
            <div className="control-actions">
              {status.capture.manager?.active ? (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={captureBusy || !status.capture.manager.canStop}
                  onClick={() => postCapture("stop")}
                >
                  Live-Daten ausschalten
                </button>
              ) : (
                <button
                  type="button"
                  className="primary-button"
                  disabled={
                    captureBusy ||
                    !status.printer.connected ||
                    !status.capture.manager?.canStart
                  }
                  onClick={() => postCapture("start")}
                >
                  Live-Daten einschalten
                </button>
              )}
            </div>
            <p className="control-note">
              Schaltet die passive ALPS-/Bewegungsaufnahme direkt ein oder aus.
              Beginnt ein Druck, endet sie automatisch mit ihm. Kein PA-,
              Rückzugs-, Pause- oder Abbruchbefehl wird gesendet.
            </p>
            {captureMessage && (
              <p className="control-message">{captureMessage}</p>
            )}
            {status.capture.manager?.error && (
              <p className="control-error">{status.capture.manager.error}</p>
            )}
          </div>
        </section>

        <aside className="profile-card">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Materialprofil</p>
              <h2>Testfenster vorbereiten</h2>
            </div>
            <span className="profile-icon">
              {(selectedProfile?.name ?? "—").slice(0, 2)}
            </span>
          </div>

          <div className="profile-tabs-row">
            <div className="material-tabs" role="tablist" aria-label="Material">
              {profiles.map((profile) => (
                <button
                  key={profile.id}
                  className={profile.id === selectedId ? "active" : ""}
                  onClick={() => setSelectedId(profile.id)}
                  role="tab"
                  aria-selected={profile.id === selectedId}
                >
                  {profile.name}
                </button>
              ))}
            </div>
            <button
              className="add-profile-button"
              type="button"
              onClick={addProfile}
              aria-label="Neues Filamentprofil hinzufügen"
            >
              + Profil
            </button>
          </div>

          {selectedProfile && (
            <div className="profile-form">
              <div className="profile-source">
                <span>Profilbasis</span>
                <strong>{selectedProfile.manufacturer}</strong>
              </div>
              <div className="field-group two profile-identity">
                <label>
                  Filamentart / Name
                  <input
                    type="text"
                    value={selectedProfile.name}
                    onChange={(event) =>
                      updateProfile("name", event.target.value)
                    }
                    placeholder="z. B. PA-CF Schwarz"
                  />
                </label>
                <label>
                  Hersteller / Notiz
                  <input
                    type="text"
                    value={selectedProfile.manufacturer}
                    onChange={(event) =>
                      updateProfile("manufacturer", event.target.value)
                    }
                    placeholder="z. B. SUNLU"
                  />
                </label>
              </div>
              <div className="field-group">
                <label>
                  Temperatur von
                  <span>
                    <input
                      type="number"
                      value={selectedProfile.minTemperature}
                      onChange={(event) =>
                        updateProfile("minTemperature", event.target.value)
                      }
                    />
                    °C
                  </span>
                </label>
                <label>
                  bis
                  <span>
                    <input
                      type="number"
                      value={selectedProfile.maxTemperature}
                      onChange={(event) =>
                        updateProfile("maxTemperature", event.target.value)
                      }
                    />
                    °C
                  </span>
                </label>
                <label>
                  Schritt
                  <span>
                    <input
                      type="number"
                      min="1"
                      value={selectedProfile.temperatureStep}
                      onChange={(event) =>
                        updateProfile("temperatureStep", event.target.value)
                      }
                    />
                    °C
                  </span>
                </label>
              </div>

              <div className="temperature-strip">
                {temperatures.slice(0, 7).map((temperature) => (
                  <span key={temperature}>{temperature}°</span>
                ))}
                {temperatures.length > 7 && <span>+{temperatures.length - 7}</span>}
              </div>

              <div className="divider" />

              <div className="field-group two">
                <label>
                  Heizbett von
                  <span>
                    <input
                      type="number"
                      value={selectedProfile.minBedTemperature}
                      onChange={(event) =>
                        updateProfile("minBedTemperature", event.target.value)
                      }
                    />
                    °C
                  </span>
                </label>
                <label>
                  bis
                  <span>
                    <input
                      type="number"
                      value={selectedProfile.maxBedTemperature}
                      onChange={(event) =>
                        updateProfile("maxBedTemperature", event.target.value)
                      }
                    />
                    °C
                  </span>
                </label>
              </div>

              <div className="field-group two">
                <label>
                  Geschwindigkeit von
                  <span>
                    <input
                      type="number"
                      value={selectedProfile.minPrintSpeed}
                      onChange={(event) =>
                        updateProfile("minPrintSpeed", event.target.value)
                      }
                    />
                    mm/s
                  </span>
                </label>
                <label>
                  bis
                  <span>
                    <input
                      type="number"
                      value={selectedProfile.maxPrintSpeed}
                      onChange={(event) =>
                        updateProfile("maxPrintSpeed", event.target.value)
                      }
                    />
                    mm/s
                  </span>
                </label>
              </div>

              <div className="divider" />

              <div className="filter-settings">
                <label className="filter-toggle">
                  <input
                    type="checkbox"
                    checked={selectedProfile.filterEnabled}
                    onChange={(event) =>
                      updateProfile("filterEnabled", event.target.checked)
                    }
                  />
                  <span>
                    <strong>Chamber-Filter für dieses Material</strong>
                    <small>
                      {status.chamberFilter.allowCommands
                        ? "Automatische Lüfterbefehle freigegeben"
                        : "Serverseitig gesperrt – Konfiguration ist sicher testbar"}
                    </small>
                  </span>
                </label>

                {selectedProfile.filterEnabled && (
                  <>
                    <div className="field-group two">
                      <label>
                        Kennung im Dateinamen
                        <input
                          type="text"
                          value={selectedProfile.filterTag}
                          onChange={(event) =>
                            updateProfile("filterTag", event.target.value)
                          }
                          placeholder="[FILTER]"
                        />
                      </label>
                      <label>
                        Klipper-Lüfter
                        <select
                          value={selectedProfile.filterFan}
                          onChange={(event) =>
                            updateProfile("filterFan", event.target.value)
                          }
                        >
                          {!status.chamberFilter.availableFans.length && (
                            <option value={selectedProfile.filterFan}>
                              {selectedProfile.filterFan ||
                                "Kein fan_generic gefunden"}
                            </option>
                          )}
                          {status.chamberFilter.availableFans.map((fan) => (
                            <option value={fan} key={fan}>
                              {fan}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div className="field-group two">
                      <label>
                        Filterleistung
                        <span>
                          <input
                            type="number"
                            min="10"
                            max="100"
                            step="5"
                            value={selectedProfile.filterSpeedPercent}
                            onChange={(event) =>
                              updateProfile(
                                "filterSpeedPercent",
                                event.target.value,
                              )
                            }
                          />
                          %
                        </span>
                      </label>
                      <label>
                        Nachlauf
                        <span>
                          <input
                            type="number"
                            min="0"
                            max="120"
                            step="5"
                            value={selectedProfile.filterPostRunMinutes}
                            onChange={(event) =>
                              updateProfile(
                                "filterPostRunMinutes",
                                event.target.value,
                              )
                            }
                          />
                          min
                        </span>
                      </label>
                    </div>
                    <p className="filter-hint">
                      Beispiel: Nur eine Datei mit{" "}
                      <strong>{selectedProfile.filterTag || "[FILTER]"}</strong>{" "}
                      im Namen aktiviert diese Regel. Bei Fehlern bleibt der
                      Druck unbeeinflusst; ein bereits laufender Filter wird
                      nicht vorschnell ausgeschaltet.
                    </p>
                  </>
                )}
              </div>

              <div className="divider" />

              <div className="field-group">
                <label>
                  PA von
                  <input
                    type="number"
                    step="0.005"
                    value={selectedProfile.paStart}
                    onChange={(event) =>
                      updateProfile("paStart", event.target.value)
                    }
                  />
                </label>
                <label>
                  bis
                  <input
                    type="number"
                    step="0.005"
                    value={selectedProfile.paStop}
                    onChange={(event) =>
                      updateProfile("paStop", event.target.value)
                    }
                  />
                </label>
                <label>
                  Schritt
                  <input
                    type="number"
                    step="0.005"
                    value={selectedProfile.paStep}
                    onChange={(event) =>
                      updateProfile("paStep", event.target.value)
                    }
                  />
                </label>
              </div>

              <label className="cycle-field">
                Wiederholungen
                <input
                  type="number"
                  min="3"
                  max="20"
                  value={selectedProfile.cycles}
                  onChange={(event) =>
                    updateProfile("cycles", event.target.value)
                  }
                />
              </label>

              <div className="notice">
                <strong>Filterstatus: {status.chamberFilter.state}</strong>
                <p>
                  Das Profil heizt den Drucker nicht und übernimmt keinen
                  PA-Wert. Filterbefehle sind getrennt freigeschaltet und
                  betreffen ausschließlich den gewählten `fan_generic`.
                </p>
              </div>

              <div className="profile-actions">
                <button className="primary-button" onClick={saveProfiles}>
                  {saved
                    ? "Profile gespeichert"
                    : "Profile & Filterregeln speichern"}
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={removeProfile}
                  disabled={profiles.length <= 1}
                >
                  Profil entfernen
                </button>
              </div>
              {profileMessage && (
                <p className="control-message">{profileMessage}</p>
              )}
              {status.chamberFilter.lastError && (
                <p className="control-error">
                  {status.chamberFilter.lastError}
                </p>
              )}
            </div>
          )}
        </aside>
      </div>

      <footer>
        <span>AutoPA · experimentelle Sensorauswertung</span>
        <span>Fail-open: Druckeraktion {status.safety.printerAction}</span>
      </footer>
      </main>
    </>
  );
}
