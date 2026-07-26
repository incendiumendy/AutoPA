# Fail-open printing and fail-closed analysis

## Safety contract

AutoPA follows two different failure policies:

1. **Normal printing is fail-open.** Missing ALPS samples, LIS2DW errors,
   timestamp gaps, implausible values, recorder crashes and analysis failures
   never pause, cancel or emergency-stop a print.
2. **Data analysis is fail-closed.** A dataset with missing, delayed, clipped,
   flat or otherwise implausible signals receives no PA recommendation.

The one deliberate exception is `AUTOPA_VALIDATE`: it may reject an explicitly
started calibration file before the first calibration move. It is not inserted
into ordinary sliced print files.

## Isolation from Klipper

- The recorder is an external process connected to Klipper's read-only API
  socket and the ALPS serial port.
- Recorder exceptions stop only the recording threads and are written into
  `manifest.json`.
- The recorder sends no `PAUSE`, `CANCEL_PRINT`, `M112`,
  `SET_PRESSURE_ADVANCE` or heater/motion command.
- A disconnected recorder automatically releases the LIS2DW dump subscription.
- `AUTOPA_MARK` is fail-open. An empty or internally failed marker is logged
  and skipped without raising a G-code error.
- The existing digital ALPS probe remains independent of the USB measurement
  stream.

## Dataset gates

`autopa.quality` rejects analysis when any of these are found:

- errors recorded in `manifest.json`;
- LIS2DW error or overflow counters above zero;
- missing raw or filtered ALPS channel;
- ALPS rate below 1,000 Hz;
- LIS2DW rate below 100 Hz;
- fewer than three clock synchronization pairs;
- clock-fit maximum residual above 1 ms;
- force gaps above the larger of 10 sample periods or 5 ms;
- acceleration gaps above the larger of 10 sample periods or 30 ms;
- ALPS values within 5% of a signed 24-bit ADC rail;
- a completely flat raw or filtered force channel.

These are acquisition validity limits, not printer-control limits. They set
`analysis_eligible: false` and preserve the raw files for diagnosis.

## Analysis behavior

`autopa.analyze` requires `quality.json` with
`analysis_eligible: true`. Otherwise:

- per-cycle diagnostics may still be produced;
- `recommendation` is `null`;
- `printer_action` remains `none`;
- no PA value is applied.

Even a valid recommendation remains advisory until repeated hardware tests and
an explicit user-confirmed apply workflow exist.
