export const dynamic = "force-dynamic";

export async function GET() {
  const now = Date.now();
  const phase = now / 1000;
  const force = 10420 + Math.sin(phase * 1.7) * 260 + Math.sin(phase * 0.31) * 90;
  const acceleration =
    9630 + Math.sin(phase * 2.1) * 110 + Math.cos(phase * 0.42) * 55;
  const temperature = 210 + Math.sin(phase * 0.18) * 0.35;

  return Response.json(
    {
      timestamp: new Date(now).toISOString(),
      demo: true,
      printer: {
        connected: true,
        state: "Klipper bereit",
        printState: "standby",
        temperature,
        target: 210,
        pressureAdvance: 0.03,
        smoothTime: 0.02,
        nozzleDiameter: 0.6,
        filamentDiameter: 1.75,
        maxExtrudeCrossSection: 1.44,
        firmwareRetractionAvailable: true,
        retractLength: 0.5,
        retractSpeed: 120,
      },
      capture: {
        state: "ok",
        dataset: "Vorschau · ABS 250 °C",
        ageSeconds: 0.08,
        manager: {
          state: "idle",
          active: false,
          canStart: true,
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
          state: "ok",
          value: force,
          baseline: 10420,
          delta: force - 10420,
          normalized: (force - 10420) / 350,
          sampleRate: 2597,
        },
        lis2dw: {
          state: "ok",
          magnitude: acceleration,
          sampleRate: 386,
        },
      },
      quality: {
        state: "ok",
        message:
          "Alle Datenströme sind frisch und die Messkette ist synchron.",
      },
      safety: {
        printerAction: "none",
      },
      control: {
        mode: "dry_run",
        allowPrinterCommands: false,
        armed: false,
        armedSecondsRemaining: 0,
        adaptivePAEnabled: true,
        autoRetractEnabled: false,
        suggestedPA: 0.032,
        suggestedRetractMm: 0.55,
        paConfidence: "learning",
        retractConfidence: "learning",
        paWindows: 3,
        retractEvents: 2,
        reason: "preview",
        gcodeContext: {
          active: true,
          layer: 12,
          z_mm: 2.6,
          feature: "external_perimeter",
          object: "calibration_cube",
          source_line: 18342,
          pa_eligible: true,
          eligibility_reason: "eligible_extrusion_feature",
          print_time: 142.5,
        },
        paContextEligible: true,
        extruderVelocityMmS: 3.91,
        toolheadVelocityMmS: 86,
        volumetricFlowMm3S: 9.4,
        contextPrintTime: 142.7,
        commandCount: 0,
        lastCommand: null,
        lastError: null,
      },
    },
    {
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
