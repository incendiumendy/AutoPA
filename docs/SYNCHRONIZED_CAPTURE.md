# Synchronized ALPS + optional accelerometer capture

## Goal

Record nozzle force and real toolhead acceleration during a controlled PA test
or an ordinary print. Both streams are retained as raw data and aligned on
Klipper's `print_time` clock before analysis.

## Existing hardware

- FLY-ALPS: ADS131M02 load-cell ADC, connected to the Raspberry Pi through the
  stable USB hub.
- EBB42 Gen2: onboard LIS2DW, already configured as `lis2dw toolboard_t0` over
  software SPI and connected to Klipper by USB.
- Live validation returned plausible X/Y/Z acceleration values. No additional
  accelerometer wiring is needed.

## Preferred data paths

| Stream | Klipper source | Nominal fields |
| --- | --- | --- |
| Force | Mellow factory USB serial protocol | host monotonic time, raw, filtered |
| Motion | selected Klipper accelerometer endpoint, optional | time, X, Y, Z acceleration |
| Planned motion | Klipper toolhead and extruder trap queues | executed path speed and filament speed |
| Print context | Klipper status / G-code markers | position, velocity, extrusion, PA candidate |
| Material state | Klipper object subscription | nozzle temperature, target, PA, Smooth Time, print state |

Klipper converts accelerometer MCU time to `print_time`. ALPS factory firmware does
not provide a timestamp, so the recorder stamps each received line with Linux
monotonic time. The read-only `autopa/clock` endpoint records monotonic /
`print_time` pairs once per second for an affine time conversion. Arrival time
remains visible so latency and jitter can be evaluated.

Factory firmware has no per-sample counter or timestamp, while the ADC stream
itself is periodic. Alignment therefore fits sample index to Linux arrival
time and uses that regularized force timebase for interpolation. Raw arrival
timestamps remain untouched in `force.csv`. A raw arrival gap above 6 ms or a
fitted RMS arrival residual above 1 ms rejects the run. The raw-gap check
catches discrete USB stalls; RMS catches sustained timing distortion without
rejecting an otherwise continuous stream for one harmless fit outlier.

## Recorder design

The preferred recorder is a host process plus the small read-only
`autopa_clock` Klipper module. A capture session has one ID and writes:

- `manifest.json`: versions, configuration, sample rates, calibration and test
  parameters;
- `force.csv`: original load-cell batches and error/overflow counters;
- `acceleration.csv`: original optional accelerometer samples and counters;
- `events.csv`: synchronized markers such as line start, corner, extrusion
  transition, PA change and capture stop;
- `toolhead_motion.csv` and `extruder_motion.csv`: Klipper's scheduled motion
  segments used to reconstruct the values at an exact `print_time`;
- `combined.parquet` or `combined.csv`: resampled analysis view generated after
  capture, never a replacement for raw data.

The factory ALPS serial reader runs in its own process. This prevents Python
thread scheduling from delaying force timestamps while Klippy acceleration
and motion batches are decoded. Only a decimated in-memory copy feeds the
10 Hz dashboard publisher; the complete force stream is written exclusively
by the ALPS process.

The streams have different sample rates. Analysis uses a common time window
and explicit resampling/filtering; it must not pair samples merely by row
number.

LIS2DW, LIS3DH, ADXL345 and MPU9250 endpoints are selectable. With
`--accelerometer-type none`, `acceleration.csv` remains header-only and
alignment uses the regularized ALPS timebase directly. Force, temperature,
markers and commanded extrusion remain available. See
[optional accelerometers](ACCELEROMETERS.md).

## What the additional signal enables

- Separate commanded pressure changes from frame/toolhead vibration.
- Reject force peaks caused by acceleration, impacts or cable motion.
- Compare force lag and overshoot against actual movement at corners and speed
  transitions.
- Detect bad runs through sensor overflow, dropped batches, unexpected RMS
  acceleration or poor signal-to-noise ratio.
- Retain normal Klipper input shaping while measuring real shaped motion during
  a print. Dedicated resonance sweeps remain a separate calibration workflow.

## Operational limits

- Start with short, supervised test patterns before full-print capture.
- Streaming both sensors increases MCU/USB/Pi load. Every run records overflow
  and retransmit counters and is invalid if thresholds are exceeded.
- Do not run `TEST_RESONANCES` during an ordinary print. Passive LIS2DW capture
  is sufficient for this project.
- Dataset recording never changes pressure advance automatically. Analysis
  proposes a value; applying it is a separate, bounded action.
- While Mellow firmware is installed, the existing digital `[probe]` remains
  responsible for bed probing. After an ALPS Klipper flash it is unavailable;
  flashing is blocked until `load_cell_probe` is validated or an independent
  Z probe is installed.

## Validation sequence

1. Validate the selected accelerometer at rest and during a short controlled
   move, or explicitly select force-only mode.
2. Install the factory-firmware host recorder and `autopa_clock` module.
3. Capture both sensors for 10 seconds at rest and verify timestamps, gravity,
   force baseline, error counts and overflows.
4. Generate and inspect a short marked smoke sweep.
5. Capture that supervised PA pattern with extrusion in free air.
6. Compare the experimental recommendation with plots and a conventional
   Klipper PA calibration.
7. Only after repeated agreement consider an explicitly confirmed apply step.
