# K210 physical experiment execution card

## Before power-on

- Confirm `/flash/main.py` has been backed up.
- Confirm the SD package hash and KModel hash on the PC.
- Confirm the selected SD card is blank or backed up and formatted FAT32.
- Confirm the laptop is not asleep and MaixPy IDE is at `115200 8N1`.

## Ten-minute sequence

1. Insert SD, connect USB, and wait for COM3/COM4.
2. Run the 30-second port-stability probe.
3. Connect the REPL port and capture firmware, reset-cause, memory and mount data.
4. Copy the package into place without overwriting `/flash/main.py`.
5. Run `SMOKE`; stop immediately on model or camera failure.
6. Install the short boot launcher only after `SMOKE` passes.
7. Capture `BENCHMARK`, then stop and allow the board to cool.
8. Capture one cold-start `STABILITY` run.
9. Capture `HOLDOUT`; the no-retune rule is mandatory.
10. Copy logs and holdout images back to the PC, hash them and evaluate.

## Cooling rule

Do not leave the board powered while arranging scenes or modifying files. Power
on only for the active run, then power off and allow cooling. A thermal reset
during any experiment is recorded as a failure and is not retried indefinitely.
