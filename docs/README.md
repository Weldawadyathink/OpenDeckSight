# Research index

Target hardware: LCD Steam Deck with a DeckSight display. Anonymous read-only
compatibility findings are recorded in the validation notes. Human confirmation
is required for anything potentially dangerous to hardware or software.

| Record | Contents |
| --- | --- |
| [BIOS](bios.md) | Stock/r03/r04 comparison, EC patch map, byte-order anomaly |
| [Full reconstruction](full-reconstruction.md) | Whole `.fd` identity and remaining semantic/signing requirements |
| [Container reconstruction](container-reconstruction.md) | IFLASH/PE metadata and explicit historical signature reuse |
| [Signing and installation](signing.md) | How signatures work, signer identity and whether a new signing step is needed |
| [Other custom BIOS projects](custom-bios-research.md) | Public signing/bypass research, conflicting reports and the QA certificate in stock firmware |
| [Panel initialization](panel-init.md) | Decoded packets, known meanings and explicit unknowns |
| [EC interpreter](ec-interpreter.md) | Instruction traces for table selection, bus buffers and delay counters |
| [Brightness](brightness.md) | Recovered mailbox and panel protocol |
| [Validation](hardware-validation.md) | Work requiring the physical device |
| [Variable refresh feasibility](vrr-feasibility.md) | Read-only VRR finding, bridge/panel uncertainties and next evidence |
| [Bridge VRR experiment plan](vrr-bridge-test-plan.md) | Native AUX result, active-test prerequisites and decision points |
| [Offline VRR kernel tests](vrr-kernel-research.md) | Candidate OGC source, independent range gates, late-frame fallback and quantization |
| [Optical VRR measurement](vrr-optical-measurement.md) | Camera versus photodiode, microcontroller capture design and end-to-end evidence |
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
- `e9d94c9`: complete r04 BIOSIMG reproduction, packet decoding and cryptographic verification.
- `d9a999d`: original EC instruction traces, forced selector and corrected delay-counter behavior.

## Remaining work

- Runtime testing only after explicit human approval; read-only compatibility
  observations are available.
- Determine which EC bank is active and whether the reversed table is reachable.
- Verify command meanings still marked opaque, mailbox arbitration and wake behavior.
- Analyze firmware signature verification and produce a supported build/update path.
- Locate touchscreen firmware artifacts/source and assess remaining closed dependencies.
- Explain all modifications, not just reproduce bytes, before claiming equivalence
  to the original developer's process. Continue panel identification from public
  artifacts and static analysis.

The project is not ready to replace firmware on a device. Offline reconstruction
and source availability are established for the documented changes; full hardware
behavior and a completely open platform stack are not.
