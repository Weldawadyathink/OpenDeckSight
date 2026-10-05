# ICNA3512 datasheet: relevance to variable refresh

The [ICNA3512 Preliminary Datasheet, revision 0.00](datasheets/ICNA3512_Preliminary_Datasheet_V0.00.pdf)
is useful for the VRR investigation and is retained unmodified on this branch.
It describes a candidate **panel display-driver controller**, not the ANX7580
eDP-to-DSI bridge. Matching initialization commands support investigating this
controller family; they do not establish the exact DeckSight chip or revision.
This review used local documents and existing static reports only.

The PDF and its provenance were imported from DSC commit
`800bc2b29eddb6624abd768a22e60efa4b9d29bb`, without importing that branch's device
tools or experimental changes. The 18,926,223-byte, 314-page document has SHA-256
`afa40b8f9d7dcd13b3716a8524d7316bb4869966e5494dcae623ac571858f991`.
The [source manifest](../research/icna3512-datasheet-source.json) preserves its
public origin and rights notice. Page references below use the printed page
numbers, which match PDF page positions. The key tables on pages 8, 31 and 166
were also checked visually.

## The most useful clue: the existing video-mode command

The [released first-bank initialization](../research/reports/r04-panel-init.json)
already contains `48 03`, submitted at EC offset `0x6e69`. Page 166 defines
command `48h` as display-operation-mode selection. Under that definition,
parameter `03h` means:

- `DSI_MODE[1:0] = 3`: video mode with GRAM bypass.
- `HFR_MODE[1:0] = 0`: the normal refresh-mode selection.

**Conditional inference:** if those definitions apply to DeckSight's controller
and that initialization executes successfully, it requests the path that
bypasses the controller's frame memory. This weakens the hypothesis that the
panel must always rescan a full-frame buffer independently of incoming video.
It does not establish per-frame blanking tolerance, successful live command
acceptance, or transparent timing through the upstream bridge. GRAM bypass
also does not imply that every internal timing function or buffer is bypassed.

Page 167 documents command `49h` for reading the same mode fields. It is a
potential future observation, not a read performed here. A panel read requires
an active DSI transport transaction through the bridge; it must not be treated
as a harmless cached query or attempted merely because the command is named
"read."

## Relevant sections and limits

| Pages | Finding | Use for VRR research |
| --- | --- | --- |
| 7-8 | The controller has frame memory and advertises dynamic frame rate, up to 144 Hz in command/video modes, and a separate AOD range. | A positive controller-family lead. These feature claims do not specify arbitrary per-frame timing, DeckSight limits, or a usable 1-144 Hz VRR range. |
| 31 | The video timing table gives typical values, including a 16-line front porch and 60 Hz, but leaves minimum/maximum timing columns blank. It ties sync/back-porch placement to gate timing. | It supplies no verified limit for stretching vertical blanking on DeckSight. Its 2800-line example is not the DeckSight mode. |
| 64-68 | Video-mode packet sequences carry synchronization events and real-time pixel data. | Helps reason about the DSI output that must be measured; does not document ANX7580 pass-through behavior. |
| 87-90, 165 | TE output modes and a current-scanline read command are described. | Possible synchronization observables if a reviewed access path exists. TE behavior alone is not optical proof, and no accessible DeckSight TE connection is established here. |
| 166-167 | Separate command/video paths through or around GRAM, plus mode readback. | Gives the conditional interpretation of the released `48 03` command above. |
| 193-196 | LTPO-labeled controls and readback exist. | Their presence does not identify the panel backplane or explain a complete VRR sequence. Page 7 describes the controller as LTPS; do not infer DeckSight is LTPO. |

Several less-generic byte matches strengthen the family lead. Pages 106-107
describe `9c a5 a5` and `fd 5a 5a` as disabling the user/manufacturer command
locks. Page 246 defines `9f 01` and `9f 02` as register-group selection. Page 169
also defines five brightness parameters, consistent with the unusual payload
length of `51 09 00 00 00 00`. All occur in the released first-bank stream.
These are conditional semantic matches, not a silicon identity read. In
particular, the grouped `ed` and `b4` payload effects remain unresolved.

## Effect on the next experiment

The [completed narrow A/B/A run](vrr-visual-experiment.md) remains evidence of
variable GPU event timing and no reported visual anomalies. This datasheet
does not upgrade it to measured bridge/panel VRR and does not explain the zero
DPCD control-byte readback. The ANX7580 still has to transfer the frame timing,
and the particular panel still has to accept it.

Use the document to refine the timing model and any future reviewed mode
readback. The decisive next evidence remains optical capture of visible frame
transitions against irregular submissions and a fixed-refresh control. No
timing-range expansion, panel command, LTPO setting, or firmware change follows
from this document review.
