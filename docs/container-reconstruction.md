# Signed-container reconstruction

The complete 17,778,952-byte r04 `.fd` now reproduces byte-for-byte from the
Valve F7A0133 `.fd`, generated BIOSIMG modifications, the identified PNG and
three existing r04 signature resources. `build-fd` does not read the reference
release's firmware or executable regions. Its output is checked against:

`4c0b33f4d48b9557337d690d20014941855acd39a1cfb7e3e46d04b1d12403ea`

The [end-to-end report](../research/reports/full-fd-reconstruction.json) records
the build and [signature checks](../research/reports/rebuilt-fd-signatures.json)
verify all three layers on the output. Byte identity does not resolve the
remaining vendor-specific panel semantics or establish updater trust policy.

## IFLASH sizes: two conventions, one aligned record structure

The meaningful IFLASH header starts at the ASCII `$_IFLASH` marker. It contains
an eight-byte signature, eight-byte tag, a 32-bit little-endian total size and
a 32-bit little-endian payload size: **24 bytes** in total. The original scanner
also matches the eight zero bytes preceding that marker; those are alignment
padding, not part of this header.

Every marker in these files is 32-byte aligned. Let `n` be the payload length:

```text
slot_size = round_up(24 + n, 32)
padding   = slot_size - 24 - n
Valve total-size field     = slot_size
DeckSight total-size field = slot_size - 24
```

The formula accounts for every record in both inputs:

| Record | Stock payload length | r04 payload length | Stock total field | r04 total field |
| --- | --- | --- | --- | --- |
| DRV_IMG | `0x10ded68` | `0x10ded88` | `0x10ded80` | `0x10ded88` |
| BIOSIMG | `0x1000000` | same | `0x1000020` | `0x1000008` |
| INI_IMG | `0xb05a` | same | `0xb080` | `0xb068` |
| BIOSCER | `0x100` | same | `0x120` | `0x108` |
| BIOSCR2 | zero | same | `0x20` | `0x08` |

Thus r04 counts from the end of the header, while the stock field includes the
header. Neither interpretation changes the recorded payload length. Padding is
generated as zeros; no target padding fragments are copied. The public
[BIOSUtilities header definition](https://github.com/platomav/BIOSUtilities/blob/main/biosutilities/insyde_ifd_extract.py)
also describes the r04 convention. This is evidence about the format, not
identification of the private tool/version used to produce DeckSight's file.

## The shipped updater confirms the payload-length interpretation

Valve's package contains an unstripped x86-64 `h2offt`, SHA-256
`7295a98ec04fe3a73d4778d2add15ccef0ef685e34322fca725af6913d222447`.
It was extracted locally **as data only** and disassembled, never executed.
In `GetBiosImageFromSecureImage`:

- `0x43d58f..0x43d5b4` searches for the 16-byte ASCII `$_IFLASH_BIOSIMG`.
- `0x43d60f` reads the 32-bit payload length at marker + `0x14`.
- `0x43d6c4..0x43d6de` copies that many bytes from marker + `0x18`.

That extraction path does not use the total-size field at +`0x10` to find the
next record. This explains why changing the total-size convention does not
change what this routine extracts. It is not a whole-updater acceptance test.
Reproduce the relevant disassembly without running the updater:

```sh
python3 tools/fetch_artifacts.py
objdump -d --x86-asm-syntax=intel --start-address=0x43d525 --stop-address=0x43d7f7 artifacts/extracted/stock/usr/share/jupiter_bios_updater/h2offt
```

## Rebuilding the nested PE wrappers

The original wrapper code comes from Valve, whose executable sections already
match r04. The builder preserves the original headers and prefix through the
first IFLASH marker, then rebuilds records in order. It handles the inner
driver first, then embeds that complete signed driver in the outer wrapper.

The final `.reloc` section contains the appended firmware records. Both wrappers
use equal file offsets and RVAs with file/section alignment 32. The builder
checks that layout and recalculates the final section's raw and virtual sizes,
`SizeOfImage`, certificate-table offset/size and PE checksum from the resulting
bytes. Original executable/linker fields that do not describe these appended
extents remain unchanged. The PE field layout follows
[Microsoft's PE specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).

Each PKCS#7 DER resource is wrapped in a generated `WIN_CERTIFICATE`, revision
`0x0200`, type 2, with zero padding to eight bytes. The release's certificate
length convention includes that padding. The signatures use the same QA
certificate but are different signatures over different content.

The inner certificate changes from 1,352 to 1,384 bytes. Its preceding section
length is unchanged. Embedding the 32-byte-larger signed inner image grows the
outer resource section and `SizeOfImage` by 32; the outer certificate also
grows by 32. The final file therefore grows by exactly **64 bytes**. Both PE
checksums are calculated anew, not taken from a target header.

## Explicit signature reuse, not a recovered signing process

Only these three cryptographic resources are extracted from r04:

| Resource | Bytes | Purpose |
| --- | --- | --- |
| `bioscer.sig` | 256 | RSA PKCS#1 v1.5 signature over the complete BIOSIMG SHA-256 |
| `driver.p7b` | 1,371 | Existing inner Authenticode SignedData, including its certificate |
| `outer.p7b` | 1,371 | Existing outer Authenticode SignedData, including its certificate |

The files total 2,998 bytes. Their hashes are pinned separately in the manifest
and builder. The eight-byte certificate headers and five-byte alignment tails
are generated rather than extracted. The required CLI flag
`--reuse-release-signatures` makes this dependency explicit. No private key is
present, and altered payloads are rejected rather than given stale signatures.

The existing signatures verify because their signed bytes have been reproduced.
This establishes exact historical reconstruction. It does **not** establish how
to sign a different BIOS version, repair the second-bank anomaly in a signed
update, or reproduce the original developer's private signing environment.
Those remain separate requirements, alongside understanding the opaque panel
commands. No update or flash operation has been attempted.
