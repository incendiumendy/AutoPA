# FLY-ALPS through the EBB42 Gen2 USB passthrough

## Deutsch

### Verifizierter Anschlussweg

AutoPA kann den USB-CDC-Datenstrom eines Mellow FLY-ALPS über den
USB-Passthrough-Anschluss eines **BIGTREETECH EBB42 Gen2 V1.0** lesen. Diese
Variante wurde am 27. Juli 2026 mit RatOS und Klipper praktisch geprüft:

```text
Raspberry Pi / Klipper-Host
`- stabiler USB-Uplink
   `- EBB USB Adapter -> EBB42 Gen2 im USB-Modus
      |- EBB42-Klipper-MCU und LIS2DW
      `- USB-Passthrough -> Mellow FLY-ALPS USB-C
         `- Werksfirmware / USB-CDC-Messdaten
```

Der offizielle EBB42-Gen2-Aufbau unterstützt laut
[BIGTREETECH-Dokumentation](https://global.bttwiki.com/EBB42_GEN2.html) einen
Passthrough-Port, der sich mit der gewählten Kommunikationsart umschaltet. Im
USB-Modus steht er deshalb als USB-Erweiterungsweg zur Verfügung. Das ist eine
Eigenschaft des **EBB42 Gen2** und darf nicht ungeprüft auf ältere EBB42-, EBB36-
oder andere Toolboards übertragen werden.

### Voraussetzungen und Sicherheit

1. Das EBB42 Gen2 muss im USB-Modus betrieben werden: nach
   BIGTREETECH-Vorgabe **kein CAN/USB-Auswahl-Jumper**.
2. Der offizielle EBB USB Adapter und der dafür vorgesehene geschirmte
   Adapter-zu-Toolboard-Kabelweg bleiben erforderlich.
3. Das EBB42 benötigt weiterhin seine separate 24-V-Versorgung. USB-C versorgt
   das Toolboard laut Hersteller nicht mit Betriebsleistung.
4. CAN und USB dürfen am EBB42 Gen2 nicht gleichzeitig als Hostverbindung
   angeschlossen werden.
5. Für den ALPS-Passthrough ist ein korrekt belegtes, kurzes und geschirmtes
   USB-Datenkabel erforderlich. Niemals Adern nur anhand ihrer Farbe crimpen;
   Steckerbelegung und Schirmung müssen elektrisch geprüft werden.
6. Der USB-Messweg ersetzt den digitalen ALPS-Probeausgang nicht. Der
   vorhandene Probe-/Homing-Pfad bleibt unabhängig bestehen.
7. Vor einem unbeaufsichtigten Druck zuerst im Leerlauf auf Disconnects,
   Unterspannung und stabile ALPS-Abtastrate prüfen.

### Erkennung unter RatOS oder Linux

Nach dem Anstecken müssen EBB42 und ALPS als zwei getrennte USB-Geräte
erscheinen:

```sh
lsusb
lsusb -t
ls -l /dev/serial/by-id/
```

Typische stabile Namen sind:

```text
/dev/serial/by-id/usb-Klipper_stm32g0b1xx_EBB42_GEN-if00
/dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_SERIAL-if00
```

`/dev/ttyACM*` darf nicht dauerhaft konfiguriert werden, weil sich die Nummer
nach einem Neustart oder Neuverbinden ändern kann. AutoPA soll immer den
`/dev/serial/by-id`-Pfad des ALPS verwenden.

Mit `udevadm` lässt sich kontrollieren, ob beide Geräte am erwarteten
USB-Zweig liegen:

```sh
udevadm info --query=property \
  --name=/dev/serial/by-id/usb-Klipper_stm32g0b1xx_EBB42_GEN-if00 \
  | grep '^ID_PATH='

udevadm info --query=property \
  --name=/dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_SERIAL-if00 \
  | grep '^ID_PATH='
```

Anschließend:

```sh
curl -fsS http://127.0.0.1:7125/printer/info
curl -fsS http://127.0.0.1:7126/api/status
journalctl -k --since '-10 min' --no-pager \
  | grep -Ei 'usb|disconnect|reset|descriptor|over-current'
```

Akzeptanzkriterien:

- Klipper meldet `ready`;
- EBB42- und ALPS-`by-id`-Pfad bleiben vorhanden;
- AutoPA meldet ALPS `state: ok` und frische Daten;
- die Abtastrate bleibt oberhalb der AutoPA-Mindestgrenze von `1000 Hz`;
- im Prüfzeitraum erscheinen keine neuen USB-Disconnects, Resets oder
  Descriptor-Fehler.

### Ergebnis des ersten verifizierten Tests

Nach dem Einstecken wurde das ALPS als `STMicroelectronics PressureLeveling`
erkannt. EBB42 und ALPS erschienen als getrennte CDC-Geräte am selben
USB-Zweig. Direkt beim Einstecken traten mehrere Neuverbindungen und einmal
`device descriptor read/64, error -32` auf. Danach lief eine zehnminütige
Überwachung mit elf Kontrollpunkten fehlerfrei:

- beide stabilen Gerätepfade blieben vorhanden;
- Klipper blieb durchgehend `ready`;
- AutoPA zeichnete ohne Monitorfehler weiter auf;
- es gab keine weiteren Disconnects, Resets oder Descriptor-Fehler;
- die abschließend gemessene ALPS-Rate lag bei etwa `1447 Hz`.

Das Ergebnis bestätigt diese Anschlussmöglichkeit für die geprüfte
Hardwarekombination. Es beweist nicht, dass jede Stromversorgung, jeder
Kabelaufbau oder jede EBB-Hardwareversion stabil funktioniert.

### Fehlersuche und Rückfallweg

Bei wiederholten Disconnects:

1. keinen Druck starten und keine Firmware flashen;
2. Kabel, Crimpung, Schirmung und Zugentlastung prüfen;
3. `vcgencmd get_throttled`, Kernel-Log und USB-Topologie sichern;
4. ALPS testweise wieder an einen guten, möglichst extern versorgten USB-Hub
   oder direkt an einen separaten stabilen Host-Port anschließen;
5. erst nach mindestens zehn Minuten fehlerfreier Leerlaufaufnahme weiter
   testen.

## English

### Validated connection path

AutoPA can read the Mellow FLY-ALPS factory USB CDC stream through the USB
passthrough port of a **BIGTREETECH EBB42 Gen2 V1.0**. This path was validated
on 27 July 2026 with RatOS and Klipper:

```text
Raspberry Pi / Klipper host
`- stable USB uplink
   `- EBB USB Adapter -> EBB42 Gen2 in USB mode
      |- EBB42 Klipper MCU and LIS2DW
      `- USB passthrough -> Mellow FLY-ALPS USB-C
         `- factory firmware / USB CDC measurements
```

The [official BIGTREETECH documentation](https://global.bttwiki.com/EBB42_GEN2.html)
states that the Gen2 passthrough port follows the selected communication mode.
It therefore provides a USB expansion path while the board is in USB mode.
This is an **EBB42 Gen2** feature and must not be assumed for older EBB42,
EBB36 or unrelated toolboards.

### Requirements and safety

1. Operate the EBB42 Gen2 in USB mode: BIGTREETECH specifies **no CAN/USB
   selection jumper** for this mode.
2. Keep the official EBB USB Adapter and the intended shielded
   adapter-to-toolboard harness in the path.
3. The EBB42 still requires its separate 24 V supply. The manufacturer states
   that USB-C does not power the toolboard.
4. Never attach USB and CAN host connections to the EBB42 Gen2 at the same
   time.
5. Use a correctly pinned, short, shielded USB data cable for the ALPS
   passthrough. Never infer a crimp pinout from wire colours; verify pinout and
   shielding electrically.
6. USB measurement does not replace the digital ALPS probe output. The
   existing probing and homing path remains independent.
7. Before unattended printing, verify disconnect-free idle operation, adequate
   power and a stable ALPS sample rate.

### Detection on RatOS or Linux

The EBB42 and ALPS must appear as separate USB devices:

```sh
lsusb
lsusb -t
ls -l /dev/serial/by-id/
```

Typical stable device names are:

```text
/dev/serial/by-id/usb-Klipper_stm32g0b1xx_EBB42_GEN-if00
/dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_SERIAL-if00
```

Do not configure `/dev/ttyACM*`, because its number can change after reconnect
or reboot. AutoPA should always use the ALPS `/dev/serial/by-id` path. Use the
`udevadm`, Moonraker, AutoPA and kernel-log checks from the German section
above to verify topology and health.

Acceptance criteria:

- Klipper reports `ready`;
- both stable device paths remain present;
- AutoPA reports ALPS `state: ok` with fresh data;
- the sample rate stays above AutoPA's `1000 Hz` minimum;
- no new USB disconnect, reset or descriptor error appears during the test.

### First validated result

The ALPS enumerated as `STMicroelectronics PressureLeveling`, separately from
the EBB42 on the same USB branch. Initial plug-in caused several reconnects and
one `device descriptor read/64, error -32`. The connection then passed an
eleven-sample, ten-minute observation:

- both stable device paths remained present;
- Klipper stayed `ready`;
- AutoPA capture continued without monitor errors;
- no further disconnect, reset or descriptor error occurred;
- the final observed ALPS rate was approximately `1447 Hz`.

This validates the connection option for the tested hardware combination. It
does not guarantee every power supply, cable assembly or EBB hardware revision.

If disconnects recur, stop before printing or flashing, inspect cable pinout,
shielding, strain relief and power integrity, save the kernel log and USB
topology, then move ALPS back to a known-good powered hub or separate stable
host port for comparison.
