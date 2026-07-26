# Mellow factory-firmware serial protocol

This protocol was reconstructed from the JavaScript delivered by Mellow's
public FLY-ALPS web tool. It allows pressure samples to be read without
replacing the factory firmware.

## Transport and commands

- USB CDC serial, 115200 baud, 8 data bits, no parity, one stop bit.
- Send `version\n` and parse `version:<value>`.
- `rt` reads the configured trigger threshold; it does not start samples.
- Firmware `1.0`/`1.0.0`: send `v` to start and `uv` to stop.
- Newer firmware: send `v\n` to start and `uv\n` to stop.
- If the version request times out, Mellow's own tool assumes version `1.0`.

## Measurement lines

- Firmware `1.0`/`1.0.0` sends `a=<raw>` and `b=<filtered>` on separate lines.
- Newer firmware sends `a=<raw>,b=<filtered>` on one line.
- Values are signed decimal integers.

`src/autopa/alps_serial.py` implements both formats and timestamps each sample
with Linux `CLOCK_MONOTONIC` as close to line receipt as possible.

## Safety significance

The factory firmware continues to provide the digital trigger output used by
the current EBB42 `[probe]` configuration. Therefore this is the preferred
first integration path. It avoids changing the bed-probing firmware and avoids
the raw-only Klipper backport's loss of the digital probe output.

This still requires supervised validation: start streaming while the printer
is idle, verify that `QUERY_PROBE` and a manual nozzle tap behave normally, and
stop the stream before any Z movement until coexistence is proven.
