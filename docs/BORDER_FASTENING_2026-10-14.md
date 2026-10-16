# Border fastening choices — 2026.10.14.4

**Historical baseline:** see [2026.10.14.5 detail repairs](DETAIL_REPAIRS_2026-10-15.md) for current mounting, screw and nail behavior. Earlier rotation/count instructions below are superseded where noted.


The user confirmed missing fasteners in both field gaps and picture-frame borders, and requested either fastening method in the tool. This build adds those choices to **5. Preview & clips**, while preserving the material/schedule, beam and hardware work in .3.

## Use in Revit

1. Reload pyRevit and confirm **2026.10.14.4** in the designer title. If the title remains old, save/restart Revit. Open the existing managed deck in Deck Designer.
2. Open **5. Preview & clips → Picture-frame / breaker fastening**.
3. Choose **Grooved/routed long edges + clips** or **Square-edge + schematic face screws**. **Manual / not modeled** preserves the earlier behavior and does not add border fasteners. Existing layouts default to that manual setting until you choose.
4. Review supplementary station spacing and end/face-edge setback. Defaults are 16 inches and 1 inch. Enable **Add missing cross-blocking in clear framing bays** if desired. These are schematic layout inputs, not approved product fastening specifications.
5. Preview: **teal = clips, purple = face screws, magenta = unsupported requested border stations**. Missing stations are omitted from counts. Large previews sample graphics; totals count all planned pieces. Rebuild and inspect actual geometry before relying on it.

## What each method does

**Grooved/routed mode** creates schematic grooves on inner border long edges and compatible adjacent field rip edges. Exposed outer perimeter faces stay square. Inner courses can have grooves on both long edges. Clip placement requires two opposing parallel long-edge grooves, the actual side gap and modeled framing support. It handles supported parallel border-to-field interfaces and gaps between double-border courses. Each border clip rotates to that border's length direction, in either schematic geometry or a user-verified loaded clip family. Loaded instances use absolute alignment to account for insertion rotation.

This mode explicitly assumes you have selected decking and routing details approved for the chosen clip. Routed border stock is reported as a separate purchasing group requiring review. Grooves are schematic, not manufacturer tooling dimensions. No clip is invented at a miter, exposed perimeter or end-grain joint. A diagonal field meeting a single border can have **zero eligible border clips** because these edges are not parallel grooved interfaces; the tool warns and directs you to face screws or a separately reviewed starter/termination detail.

**Face-screw mode** leaves borders square and creates individual **schematic face-fastener DirectShapes** at supported points on two inset screw rows per border or breaker piece. The setback is checked against the actual clipped/mitered outline. These are editable/countable generic placeholders, not downloaded screw/plug families or a procurement specification. Face screws have a separate count, role and material/pricing line; they are never counted as hidden clips. Field clips continue at grooved field gaps. Additional field-end pinning or termination fasteners remain a separate product-specific detail.

**Optional backing** adds native Structural Framing cross-blocks between planned member faces where a clear bay can carry a requested fastening point. It checks against the other planned framing rectangles and does not overlap them. The selected blocking type/section is used and receives the existing native geometry checks. It does not perform clash detection against unregistered/manual model geometry; unrelated geometry is preserved. Unresolved points remain magenta, with a warning and no fastener count. Review skewed corners, unusual sections, block spacing, fastening and load paths in Revit.

The supplementary spacing fills positions over continuous parallel support or requests additional support. Clips at actual crossing members are retained. A fixed 3/8-inch screw-center clearance within schematic framing is used to avoid counting points directly at member ends or ply seams; verify actual manufacturer clearances separately.

## Rebuild, quantities and logging

New screws and backing are registered as owned generated elements. Changing methods or turning off **Generate clips / border fasteners** removes only the previous registered fasteners/backing when rebuilt. Copied, manually placed and unrelated elements remain protected by the existing ownership/deletion checks. Native schedules and the single materials/pricing CSV include the new face-fastener role. Run Material List refresh after manual edits/copies. Layout reports retain unsupported station coordinates and each clip/screw's source board/support keys.

## Exact small tests

Use a 12 x 10 ft three-point rectangle, boards along A, 5.5-inch width/.94-inch thickness, .1875-inch side gap/.125-inch butt gap, 20-foot board stock, 1.5 x 9.25-inch joists at 16 inches, rims on, blocking off, angle 0 and no hardware/support beams. Enable boards/framing/fasteners. Use matching verified loaded joist/blocking types.

| Border setup / method | Field + border clips | Included border clips | Separate face screws | Framing pieces |
| --- | ---: | ---: | ---: | ---: |
| One course, manual | 190 | 0 | 0 | 16 |
| One course, grooved | 210 | 20 | 0 | 16 |
| Two courses, grooved, backing on | 222 | 52 | 0 | 30 |
| Two courses, grooved, backing off | 206 | 36 | 0 | 14 |
| One course, face screws | 190 | 0 | 74 | 16 |
| Two courses, face screws, backing on | 170 | 0 | 144 | 35 |

The backing-off double-border case must show **16 unsupported requested stations**. Rebuild twice, switch grooved → face → manual, and turn fasteners off/on. Confirm no duplicates, old registered screws/backing are replaced, and an unrelated manually placed member survives. Repeat with 30/45-degree decking and the stepped Floor; confirm no hidden clips across end grain and sensible missing-support warnings. Verify native board grooves/miter trims, loaded clip rotation, screw elevations, schedule counts and CSV counts in both Revit 2025 and 2027.

## Validation and limits

148 local tests pass, including default-layout preservation, actual support/board-edge checks, backing non-overlap, double-border clip orientation, field/diagonal/stepped layouts, no end-grain clips, native placement argument/geometry fixtures, face-fastener ownership and replacement/removal. Python/YAML/packaging checks pass; ten WPF screens were rendered offscreen, including actual pure-planner samples for both modes and unsupported points. The agent has **not run these new features inside Revit**. Counts in this document are local planner results, not a completed installation design or host acceptance test.

No new stair geometry was developed. The requested future drop-header attachment remains recorded in USER_PREFERENCES.md. ROBMEPTOOLS and other extensions are outside these changes.

## Manufacturer references

[CAMO's current installation guide](https://www.camofasteners.com/wp-content/uploads/24586-CMO-2024-Edge_Wedge-Instructions-Insert-v16-3.pdf) distinguishes grooved clip installation, starter clips, sister-joist butt-joint support and product-dependent additional fastening. [CAMO starter clips](https://www.camofasteners.com/products/clips/starter-clips/) are a separate perimeter detail, not the generic gap clip used here. [Trex picture-frame guidance](https://www.trex.com/academy/how-to-guides/all-guides/picture-framing-deck/) describes square-edge borders with face screws or plugs and additional framing. These references support offering distinct methods; they do not approve the tool's schematic geometry or arbitrary groove routing.
