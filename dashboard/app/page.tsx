"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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

const PRESSURE_DISPLAY_DEADBAND = 0.1;
const MOTION_DISPLAY_DEADBAND_MM_S2 = 200;

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

function PressureGauge({
  value,
  baseline,
  delta,
  normalized,
}: {
  value: number | null;
  baseline: number | null;
  delta: number | null;
  normalized: number | null;
}) {
  const percentage = pressureMarkerPosition(normalized);
  return (
    <article className="pressure-gauge-card">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">FLY-ALPS · LIVE</p>
          <h2>Druck auf der Düse</h2>
        </div>
        <strong className="pressure-main-value">
          {formatSignedRelative(normalized)} <span>relatives Signal</span>
        </strong>
      </div>
      <div className="pressure-scale" aria-label="Relativer Düsendruck">
        <span className="pressure-zero" />
        <span className="pressure-marker" style={{ left: `${percentage}%` }} />
      </div>
      <div className="pressure-scale-labels">
        <span>− Zug</span>
        <span>0</span>
        <span>+ Druck</span>
      </div>
      <div className="pressure-values">
        <div><span>Δ Counts</span><strong>{formatNumber(delta, 0)}</strong></div>
        <div><span>Rohwert</span><strong>{formatNumber(value, 0)}</strong></div>
        <div>
          <span>Nullpunkt</span>
          <strong>{formatNumber(baseline, 0)}</strong>
        </div>
      </div>
    </article>
  );
}

export default function Home() {
  const [status, setStatus] = useState<DashboardStatus>(EMPTY_STATUS);
  const [history, setHistory] = useState<PlotPoint[]>([]);
  const [profiles, setProfiles] =
    useState<MaterialProfile[]>(DEFAULT_PROFILES);
  const [selectedId, setSelectedId] = useState("pla");
  const [saved, setSaved] = useState(false);
  const [armPhrase, setArmPhrase] = useState("");
  const [controlBusy, setControlBusy] = useState(false);
  const [controlMessage, setControlMessage] = useState("");
  const [captureBusy, setCaptureBusy] = useState(false);
  const [captureMessage, setCaptureMessage] = useState("");
  const [profileMessage, setProfileMessage] = useState("");

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
        if (!active) return;
        setStatus(next);
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
      if (path === "arm") setArmPhrase("");
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
            <PressureGauge
              value={status.sensors.alps.value}
              baseline={status.sensors.alps.baseline}
              delta={status.sensors.alps.delta}
              normalized={status.sensors.alps.normalized}
            />
            <article className="adaptive-card">
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

              <div className="arming-row">
                <input
                  type="text"
                  value={armPhrase}
                  onChange={(event) => setArmPhrase(event.target.value)}
                  placeholder="AUTOPA VALIDIEREN"
                  aria-label="Bestätigung für begrenztes Anwenden"
                />
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
                      controlBusy ||
                      !status.control.allowPrinterCommands ||
                      armPhrase !== "AUTOPA VALIDIEREN"
                    }
                    onClick={() => postControl("arm", { phrase: armPhrase })}
                  >
                    Begrenzt anwenden
                  </button>
                )}
              </div>

              <p className="control-note">
                Keine Pause, kein Abbruch und kein SAVE_CONFIG. Änderungen sind
                zeitlich begrenzt, schrittweise und nur während „printing“
                erlaubt. Status: {status.control.reason ?? "—"}
              </p>
              {controlMessage && <p className="control-message">{controlMessage}</p>}
              {status.control.lastError && (
                <p className="control-error">{status.control.lastError}</p>
              )}
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
  );
}
