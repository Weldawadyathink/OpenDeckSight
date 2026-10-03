# Provenance and reproduction

## Inputs

- Supplied [DeckSight-Public](https://github.com/ShadeTechnik/DeckSight-Public)
  checkout at `2baab5bb4366e419bfad68beda5910a8fd2e8e32`.
- [DeckSight release r04](https://github.com/ShadeTechnik/DeckSight-Public/releases/tag/r04),
  published 2026-05-18; [r03](https://github.com/ShadeTechnik/DeckSight-Public/releases/tag/r03),
  published 2025-09-01. GitHub's release-asset digests were checked against downloads.
- Valve stock F7A0133 from
  [jupiter-hw-support-20260930.1-1-any.pkg.tar.zst](https://steamdeck-packages.steamos.cloud/archlinux-mirror/jupiter-main/os/x86_64/jupiter-hw-support-20260930.1-1-any.pkg.tar.zst).
  Downloaded directly from Valve's HTTPS package server; its package signature
  has not been independently verified against a SteamOS keyring.
- [UEFIExtract A75](https://github.com/LongSoft/UEFITool/releases/tag/A75), universal
  macOS binary. Only this analysis tool was executed, not a vendor installer or flasher.
- [jbit/uninsyde](https://github.com/jbit/uninsyde) provides the public IFLASH
  container layout. OpenDeckSight implements bounds-checked parsing independently.
- [DeckHD/BiosMaker](https://github.com/DeckHD/BiosMaker), particularly its public
  `chicago_registers.h`, supplies register names and useful context for the EC
  display tables. It is a different panel; its initialization values were not
  substituted for DeckSight values.
- [Linux DRM MIPI definitions](https://github.com/torvalds/linux/blob/master/include/video/mipi_display.h)
  are the primary source for DCS command and packet-type names.

## Method

1. Record release/package SHA-256 and extract archives without executing them.
2. Read bounded IFLASH chunks; compare the 16 MiB BIOSIMG payloads.
3. Inspect both 128 KiB EC banks, generate the observed display tables/EDID,
   recalculate checksums, and compare every byte of each bank.
4. Decompress stock and r04 with UEFIExtract; compare parsed module records and
   extracted leaf bodies to separate compressed-data changes from code changes.
5. Disassemble the released x86-64 brightness daemon using `objdump -d
   --x86-asm-syntax=intel`; inspect `.rodata`; recover protocol and arithmetic.

Sources have been inspected by the same implementer. This is transparent
reverse engineering, **not a claim of a legally isolated clean-room process**.
The provided upstream repository has a GPLv2 license. No upstream Lua, shell,
ICC profile or full firmware image is copied into the tracked implementation.
Original tooling retains this repository's existing MIT license; that does not
relicense upstream artifacts or generated firmware containing their code.

Large downloaded/extracted files and complete disassemblies stay in ignored
`artifacts/`; analysis tools stay in ignored `.tools/`. The manifest and selected
factual reports are tracked. SHA-256 identifies inputs and outputs; it does not
establish firmware authenticity beyond the stated retrieval provenance.
