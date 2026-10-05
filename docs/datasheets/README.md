# Controller datasheets

[ICNA3512 Preliminary Datasheet, revision 0.00](ICNA3512_Preliminary_Datasheet_V0.00.pdf)
is the complete, unmodified 314-page Chipone document dated September 2021.
It is retained here at the user’s explicit request. Its source URL, exact byte
length and SHA-256 are recorded in
[the provenance manifest](../../research/icna3512-datasheet-source.json).

The document was publicly attached to
[a hardware project’s journal](https://github.com/Studented0/universal-ai-terminal/blob/f647e5f3e615e85d3fb7d6849655ec857b07f67f/journal.md).
Original copyright and confidentiality markings remain intact. No new license
is asserted for the document, and the repository’s code license does not apply
to it.

Several commands match DeckSight’s initialization stream. This makes ICNA3512
a useful controller-family lead; it does not yet establish the exact chip in
the DeckSight panel or validate a DSC setup for the ANX7580 bridge.

The [VRR relevance notes](../vrr-icna3512.md) identify the conditional
`48 03` video-mode/GRAM-bypass interpretation, useful timing and readback
sections, and the limits of applying this controller-family document.
