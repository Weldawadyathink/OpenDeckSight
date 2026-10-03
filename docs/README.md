# Research index

Research date: 2026-10-03. Target hardware: owner's LCD Steam Deck, originally
512 GB, upgraded SSD, running Bazzite. SSH is possible but has not been provided.

| Record | Contents |
| --- | --- |
| [BIOS](bios.md) | Stock/r03/r04 comparison, EC patch map, byte-order anomaly |
| [Brightness](brightness.md) | Recovered mailbox and panel protocol |
| [Validation](hardware-validation.md) | Work requiring the physical device |
| [Provenance](provenance.md) | Sources, tool versions, reproduction boundaries |
| [Artifact manifest](../research/artifacts.json) | Download URLs and SHA-256 digests |

Evidence levels used throughout:

- **Verified offline**: directly measured in identified binary artifacts or
  reproduced by code and compared byte-for-byte.
- **Interpretation**: meaning inferred from instructions, public register names,
  or specifications. Not proof of behavior on a running device.
- **Unresolved**: needs hardware observation or additional reverse engineering.

Do not treat a valid additive checksum, a vendor filename containing `signed`,
or successful offline reproduction as hardware validation.
