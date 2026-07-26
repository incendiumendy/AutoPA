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
      },
      capture: {
        state: "ok",
        dataset: "Vorschau · ABS 250 °C",
        ageSeconds: 0.08,
      },
      sensors: {
        alps: {
          state: "ok",
          value: force,
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
    },
    {
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
