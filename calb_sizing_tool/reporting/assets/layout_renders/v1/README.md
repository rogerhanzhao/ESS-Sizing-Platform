# Typical arrangement render library

This library contains the owner-approved gravel/close-view revision (2026-11-10.v2).
Each template has TOP, SW, SE, NE and NW PNGs, all 2400 x 1600.
The source equipment geometry is unchanged. All views retain complete equipment
and foundations; perimeter kerbs are illustrative scene dressing, not site constraints.

| ID | Cabinet and placement |
| --- | --- |
| T1 | 40 ft AC with 8 DC containers, central bilateral 4+4 |
| T2 | 20 ft AC with 4 DC containers, linear paired layout |
| T3 | 20 ft AC with 2 DC containers, DC equipment ends towards AC |
| T4 | 40 ft AC with 4 DC containers, linear paired layout |

The manifest records source hashes, equipment placement signatures, spacing
profile and per-image hashes. MW/MWh values do not select images. Existing AC
sizing and arrangement resolution remain authoritative; the image selector never
changes them. A 40 ft linear arrangement with 8 DC containers does not match T1.

Mixed reports, neutral branding, uncovered layouts and incompatible product
bindings retain the existing engineering drawing. All five image hashes must
pass before TOP and a random oblique are selected. Set a template's `released`
flag to false to disable it without changing report calculations or saved data.

Images are representative installation concepts, not product electrical
schedules or construction drawings. Report figures retain concept watermarks.
