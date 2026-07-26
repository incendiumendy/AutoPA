# Raspberry Pi and USB stability

## Observations

1. The Raspberry Pi was previously unstable when FLY-ALPS was connected
   directly. Moving ALPS to a USB hub restored normal operation.
2. During an isolated two-job firmware compile on the Raspberry Pi, Klipper
   lost communication with `toolboard_t0` (the USB-connected EBB42 Gen2).
3. At the same time, port 22 remained open but the SSH server reset new
   handshakes. Moonraker remained reachable.
4. After the event, Moonraker reported no undervoltage/throttling flags,
   normal temperature and low CPU load. That does not rule out a transient
   USB, power or I/O event.

No firmware was flashed and the temporary build did not intentionally modify
the active `/home/pi/klipper` worktree.

## Consequences for this project

- Never build firmware during a print.
- Use `make -j1` for the next Raspberry build and monitor all MCU links.
- Keep ALPS on the stable hub path.
- Check whether the hub is externally powered and whether its 5 V path can
  back-power the Pi. Do not connect conflicting power sources.
- Prefer short, shielded data cables with strain relief.
- Before any flash, capture `dmesg`, USB topology, `vcgencmd get_throttled`,
  MCU retransmit counters and the exact disconnect time.
- A combined ALPS + LIS2DW recording is accepted only with zero sensor
  overflows and no increasing MCU retransmit count.

## Recovery after a communication loss

Do not issue `FIRMWARE_RESTART` until the EBB42 is visible again at its stable
`/dev/serial/by-id` or `/dev/RatOS` path. If it is visible and the printer is
idle, a firmware restart can restore Klipper. If it disappears repeatedly,
stop and correct USB/power integrity first.
