# Staggered framing blocking — 2026.10.15.2

Enable the Framing tab blocking checkbox to generate clear-bay blocks over both beam center lines and at least one intermediate row between beams. Longer bearing spans receive extra evenly spaced rows according to the maximum row spacing. Alternate bays are offset half a block thickness each way (1.5 inches between courses for nominal 2x blocking) to expose the ends for nailing. Blocks stop at joist faces and use the selected blocking section/type. Without beams, rows are distributed across the common clear joist span. Touching plies have no clear bay and receive no buried block.

The polygon planner checks block width against its inset footprint and skips overlap with existing seam backing. Preview and framing counts include the new members; native placement uses the existing BLOCK path. Blocking remains opt-in for saved layouts. Reload pyRevit and reopen the layout, enable blocking, preview, then rebuild.

199 local tests pass, including beam/midspan courses and staggering on rectangular and stepped footprints. Native Revit fit and nailing access still require inspection. No fastening schedule or structural sizing is established by this layout change.

## Edge-bay correction — 2026.10.16.1

The first implementation excluded vertical side RIM members, leaving the outer clear bays empty. Include side rims with normalized endpoint direction in the bearing zone. Short return rims outside that zone must not split a bay between full-length joists. A stepped-outline regression now verifies that all three blocking courses reach both side-rim inner faces. 200 local tests pass; native Revit verification remains required.

## Native nail name repair — 2026.10.16.2

Report 20261016_003926_282000 passes connector profile probes and post checks, then fails on the first individual connector nail. Its product label contains a pipe character and was assigned verbatim to DirectShape.Name. Sanitize generated DirectShape names before assignment, replacing reserved punctuation and control characters. The stored nail product/application metadata is unchanged. Regression covers the logged product label and the DirectShape assignment path. 202 tests pass; retry the native build to verify.

## IronPython nail extrusion repair - 2026.10.16.3

Nested report 20261016_004228_299000 confirms version .2 reached LUS210 nail 9, the first 3-inch double-shear nail. Its length is an integer, and IronPython evaluates 3/12 as zero. Inch dimensions now use explicit floating-point divisors in the native adapter. Tests exercise the nail adapter with simulated Python-2 division for integer/fractional lengths and straight, inclined and vertical directions. They check shank/head lengths and head position. 203 tests pass; native verification remains required.
