# Research index

Research date: 2026-10-03. Target hardware: owner's LCD Steam Deck, originally
512 GB, upgraded SSD, running Bazzite. Read-only SSH access has been provided
and the first inventory completed. Human confirmation is required for anything
potentially dangerous to hardware or software.

| Record | Contents |
| --- | --- |
| [BIOS](bios.md) | Stock/r03/r04 comparison, EC patch map, byte-order anomaly |
| [Full reconstruction](full-reconstruction.md) | Whole BIOSIMG identity and remaining signed-container work |
| [Panel initialization](panel-init.md) | Decoded packets, known meanings and explicit unknowns |
| [Brightness](brightness.md) | Recovered mailbox and panel protocol |
| [Validation](hardware-validation.md) | Work requiring the physical device |
| [Provenance](provenance.md) | Sources, tool versions, reproduction boundaries |
| [Reproduction](reproduce.md) | Download, inspection, comparison and test commands |
| [Artifact manifest](../research/artifacts.json) | Download URLs and SHA-256 digests |

Evidence levels used throughout:

- **Verified offline**: directly measured in identified binary artifacts or
  reproduced by code and compared byte-for-byte.
- **Interpretation**: meaning inferred from instructions, public register names,
  or specifications. Not proof of behavior on a running device.
- **Unresolved**: needs hardware observation or additional reverse engineering.

Do not treat a valid additive checksum, a vendor filename containing `signed`,
or successful offline reproduction as hardware validation.

## Checkpoints

- `8a04f83`: initial BIOS analysis, provenance, parsers and exact r04 EC reproduction.
- `40f9b36`: open brightness implementation, protocol tests and read-only collector.
- `3afcf54`: reproducible artifact tools, UEFI/container reports and upstream Lua profile.

## Remaining work

- Runtime testing only after explicit human approval; read-only inventory is complete.
- Determine which EC bank is active and whether the reversed table is reachable.
- Verify command meanings still marked opaque, mailbox arbitration and wake behavior.
- Analyze firmware signature verification and produce a supported build/update path.
- Locate touchscreen firmware artifacts/source and assess remaining closed dependencies.
- Explain all modifications, not just reproduce bytes, before claiming equivalence
  to the original developer's process. The owner does not want a teardown for
  panel identification; continue from public artifacts and static analysis.

The project is not ready to replace firmware on a device. Offline reconstruction
and source availability are established for the documented changes; full hardware
behavior and a completely open platform stack are not.
