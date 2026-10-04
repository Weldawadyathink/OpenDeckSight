# Panel initialization: decoded behavior and remaining unknowns

The user's acceptance criterion is an explained reconstruction, not just a byte
match. This record deliberately distinguishes packet decoding from understanding
what proprietary panel commands do.

The first EC bank contains 26 records starting at `0x6e55`. Each record is one
bridge-register byte plus a big-endian 32-bit value. Payload register `0x70`
feeds four little-endian bytes into the DSI payload FIFO. Header register `0x6c`
submits a packet. DCS long writes use packet type `0x39` and a 16-bit byte count;
the last FIFO word is padded. The original and reconstructed streams decode to:

| Submitted bytes / action | Interpretation | Still unresolved |
| --- | --- | --- |
| `9c a5 a5` | Three-byte DCS long write | Vendor command; do not assert it is an unlock without a datasheet |
| `11` | Standard sleep-out | Panel-specific minimum delay requirement |
| Delay value 60 | Table delay; milliseconds inferred from the known initializer conventions | Interpreter timing calibration |
| `48 03` | DCS short write with one parameter | Vendor command |
| `53 69` | Write control display; standard brightness-control and dimming bits set, standard backlight bit clear | Meaning of remaining set bits `0x41` |
| `51 09 00 00 00 00` | Brightness command, six-byte long write | Extra parameters beyond the ordinary two-byte brightness value |
| `34` | Standard tear-off | Why disabled before the next commands |
| `44 00 10` | Standard tear scanline, value 16 | Panel timing rationale |
| `35` | Standard tear-on command in a zero-parameter short packet | Normally a mode parameter is supplied; panel acceptance unverified |
| Compression packet `01 00` then `00 00` | Standard packet type `0x07`, enable bit set then cleared | Why this immediate toggle is required |
| `fd 5a 5a` | Three-byte DCS long write | Vendor command |
| `9f 02` | DCS short write | Vendor command |
| `ed 00 30` | Three-byte DCS long write | Vendor command |
| `9f 01` | DCS short write | Vendor command |
| `b4 10 00 00 03 10` | Six-byte DCS long write | Vendor command |
| `29` | Standard display-on | Whether initialization/resume sequencing is robust |

The protocol decoder checks that each long-write word count matches its queued
FIFO words. Reports are in [first bank](../research/reports/r04-panel-init.json)
and [second bank](../research/reports/r04-panel-init-bank1.json).

## The second-bank anomaly has a plausible source-level mechanism

The public [DeckHD patcher](https://github.com/DeckHD/BiosMaker/blob/master/patcher.cpp)
stores `inits` globally, byte-swaps each value **in place** inside `patchEC`, and
calls that routine for the two EC images. Swapping the same array a second time
restores the original byte order. That mechanism would produce exactly the
alternating ordering observed in DeckSight's new initialization records.

This is a concrete reproducible explanation for the pattern, not proof that
DeckSight's private source uses that code. Both r03 and r04 show the pattern.
Applying the stock/first-bank interpretation to the second bank produces packet
type zero throughout and a delay value of 1,006,632,960 instead of 60. The actual
EC-bank boot-selection path and delay arithmetic still need analysis. No live
test of this anomaly is authorized or has occurred.

## What would close the remaining semantic gap

A panel/controller part number and programming specification, or original
initialization documentation, would be stronger evidence than generic opcode
searches. Without that, code can reproduce these writes exactly, but cannot
honestly explain all their internal effects. The program labels that distinction
and the project does not claim the user's full acceptance criterion is met yet.
