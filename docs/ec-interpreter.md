# EC table interpreter: instruction-level evidence

The r04 table loader is now traced from the original 8051 instructions, with
all memory held in Python arrays. The trace stops **before** the bus routine at
`0xf129`; it neither performs nor assumes a successful hardware transaction.
The [report](../research/reports/r04-ec-trace.json) records both EC copies,
every table read address, prepared bus bytes, delay counters and selector cases.

Addresses below are relative to one 128 KiB EC copy. The traced routines and
tables are in its first 64 KiB. This does not determine which physical firmware
copy the device boots. Code-window banking and selection of the two firmware
copies are distinct questions.

## Display selection is forced, not just renamed

At `0xf2c3`, the code reads XRAM `0x160a`, tests bit 6 and stores its selected
display in XRAM `0x0356`. The stock branch stores 1 when the bit is clear and
2 when set. DeckSight changes `MOV A,#2` at `0xf2d1` to `MOV A,#1`, so both
paths now store 1. The electrical source of bit 6 has not been identified here.

At `0xf769`, state `0x13` selects its initialization table using that value:

- Selector 1: table at `0x6e55`, the table replaced by DeckSight.
- Other selector: table at `0x6a4a`, which DeckSight leaves unchanged.

The trace verifies both selector branches. This explains why patching one panel
table plus the display-selector instruction changes both detected-panel cases.

## Exact table-to-bus transformation

State `0x13` starts at `0xf75b`. XRAM `0x0fd3:0x0fd5` holds a big-endian,
16-bit record index. Helper `0xfa53` uses the multiply/address helper at
`0x6436` to calculate `table + 5*index` and reads code memory with `MOVC`.
Helpers at `0xfa9f` and `0xfaa5` arrange the output:

| Code memory, relative to record | XRAM | Meaning at the bus boundary |
| --- | --- | --- |
| `+0` | `0x0fd8`, `0x0fd9` | Register, also used for control-record dispatch |
| `+4` | `0x0fda` | Least-significant byte of the stored big-endian value |
| `+3` | `0x0fdb` | Next value byte |
| `+2` | `0x0fdc` | Next value byte |
| `+1` | `0x0fdd` | Most-significant value byte |

For ordinary records the code reaches `0xf129` with `R7=1`, `R5=0xc0`,
`R2:R3=5`, and XRAM `0x06b2:0x06b4` containing pointer `0x0fd9`.
The five bytes are therefore the register followed by the little-endian value.
For example, the first two r04 records prepare:

| EC copy | First bus buffer | Second bus buffer |
| --- | --- | --- |
| First, base `0` | `70 9c a5 a5 00` | `6c 39 03 00 00` |
| Second, base `0x40000` | `70 00 a5 a5 9c` | `6c 00 00 03 39` |

The interpreter does not compensate for the second copy's byte order. The
reference protocol decoder's first-copy ordering is now supported by the code
that prepares the transaction, rather than inferred solely from plausible DCS
commands. Peripheral acceptance and effects remain outside this trace.

## Delay correction: low byte, then one decrement per invocation

Both register `0xaa` and `0xab` take the delay path at `0xf7f3..0xf80b`.
Helper `0xfab6` reads **only XRAM `0x0fda`**, zeros the high counter byte at
`0x0fd5`, and stores that one byte at `0x0fd6`. It then advances the record
index through the 16-bit add helper at `0x61d7` and returns to the caller.
In pseudocode:

```c
delay_counter = record_value & 0xff;
record_index += 1;
return;
```

At the next entry to `0xf207`, a nonzero counter jumps to `0xf6c4`, subtracts
one and returns without dispatching the next state. An entry with zero proceeds
to the dispatcher at `0xf214`. Probe cases 0, 1, 60, 256 and 65535 confirm the
zero case and decrement/borrow behavior. Thus a counter of 60 delays dispatch
for 60 further invocations. The caller's wall-clock period is not yet proven;
the earlier millisecond label was an inference and has been removed from reports.

This corrects the earlier table-only interpretation of the second copy:

- First copy's stored bytes `00 00 00 3c` give counter 60.
- Second copy's stored bytes `3c 00 00 00` give counter **0**, not 1,006,632,960.

Both copies reach their terminator at record 25 (`0x6ed2`) and set state
`0x14`. The original table's remaining tail is consequently not read by this
path. This is a conditional result for a selected code window, not evidence
that the device ever activates the second copy.

## Reproduction and limits

```sh
python3 tools/trace_ec.py artifacts/extracted/r04/chunks/BIOSIMG.bin
python3 tools/trace_ec.py artifacts/extracted/stock/chunks/BIOSIMG.bin
python3 -m unittest discover -s tests -v
```

The command rejects unknown BIOSIMG hashes. Its small instruction model uses
the [Arm/Keil 8051 instruction specification](https://www.keil.com/support/man/docs/is51/is51_instructions.asp)
for arithmetic, memory and branch semantics. It rejects unsupported opcodes and
caps the step count. Unit tests exercise carry, multiplication/address carry,
separate code/XRAM access, calls and backward branches. Optional artifact tests
compare the actual loader's bus buffers with the independently specified r04
semantic table and check the alternate selector and delay paths.

Each record starts independently with explicit state/index inputs. Register
bank zero and an abstract call stack are modeled; interrupts, non-carry flags,
peripherals, whole-program scheduling and physical bank activation are not.
This tool is an auditable local analysis of the recovered routine, not a full
EC emulator or a claim of hardware validation. Vendor-specific panel opcodes
still need evidence about the controller's internal behavior.
