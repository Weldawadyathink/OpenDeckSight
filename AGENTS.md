# OpenDeckSight working constraints

The project target is a program that applies understood DeckSight modifications
to a Valve-provided BIOS artifact and reproduces the released image byte-for-byte.
A binary delta, copying changed regions, or matching hashes alone is not enough.
Document each transformation's meaning and evidence; label opaque vendor
commands and unresolved signing/rebuild details honestly. Keep organized research
notes and make sensible Git commits at completed checkpoints.

Limit authorized device diagnostics to **read-only** operations.
Anything potentially dangerous to hardware or software MUST be confirmed by a
human first. Do not stop/start services, install/copy files on the Deck, change
settings, access MMIO, run a flasher, or reboot without explicit human approval
for the concrete action. Stream read-only collectors through SSH with Python
bytecode writes disabled. Local source edits, analysis outputs, tests and Git
checkpoints remain authorized. Keep raw device reports in ignored `artifacts/`.
Publish only anonymous compatibility findings; omit ownership details, access
arrangements, account/host identifiers and transient device settings. Prefer
public artifacts and static analysis for panel identification.

Preserve input provenance and hashes. Keep downloaded firmware and complete
extracted payloads in ignored `artifacts/`, and local analysis executables in
ignored `.tools/`. Never execute a vendor installer or flasher for analysis.
