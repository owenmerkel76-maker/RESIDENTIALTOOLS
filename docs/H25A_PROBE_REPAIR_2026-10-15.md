# H2.5A probe repair — 2026.10.15.1

The .5 build rolled back with `Could not distinguish upper/lower H2.5A mounting tabs`. The user's native single/double hanger probes passed before this error. The tie check incorrectly required one tab to be longer. H2.5A has approximately equal flanges and overlapping tapered tails; a midpoint between tab extents also gives the wrong beam datum.

## Change

The actual loaded family name must identify H2.5A before the code uses its published US datum. [Simpson's current C-C-2026 catalog, printed page 299](https://ssttoolbox.widen.net/content/orplhjaqw1/original/C-C-2026.pdf?download=true), gives a 6-inch overall height, with the plate line 2-3/16 inches from the lower end and 3-13/16 inches from the upper end. The user's logged native bounds match these dimensions. The [official deck tie detail](https://strongtie.com.au/sites/default/files/H2.5ASS_Detail_Decking%20Joist%20Tie%20Down.pdf) shows the lower plate line aligned with the beam top.

The probe measures perpendicular mounting faces, uses surface-area centroids to determine the tab regions, checks the 6-inch envelope/flange widths and requires the tabs to straddle that plate line. Either symmetric flange can become upper. The outer sheet surfaces meet the member faces. The tab-height ratio and individual-triangle width assumptions are removed. Coplanar faces connect through shared mesh edges, so a thin end face touching only at a vertex does not extend a mounting tab's bounds.

Unknown/custom ties cannot borrow the H2.5A datum. Ambiguous contact geometry and incompatible dimensions still stop the build. Temporary probes always roll back; final native orientation/contact verification and atomic layout replacement remain active. Previous board, corner, hanger, nail, screw and framing improvements are retained. Material List host testing remains on hold.

The corrected datum also exposed a schematic nail outside the tapered flange in the regression fixture. Tie fallback nails now use a vertical rail intersected with the measured outer mounting face. The rail follows metal coverage and skips voids; positions are inset within the usable intervals. These remain schematic mounting positions, not claimed manufacturer hole centers. Native complete hole groups still take precedence, and the ten-nail H2.5A quantity is unchanged.

## Retry in Revit

1. Save the project and reload pyRevit. If the old modules remain cached, close and reopen Revit. Confirm **2026.10.15.1** in the Deck Designer title.
2. Reopen the same managed deck, keeping the loaded H2.5A, LUS210, LUS210-2 and corner-angle selections. Leave ties enabled. Preview and build once.
3. In section/3D, inspect both beam lines and touching joist pairs: upper tie tab against the joist side, lower tab against the beam face, and the correct plate line at beam top. Inspect individual schematic nails separately; a successful probe does not verify the connector's structural capacity or all fastening details.
4. Rebuild again and check stable counts. Confirm unrelated/manual model elements survive. Continue the existing corner, full-board and screw-location checks after the tie build succeeds.
5. If the probe still fails, retain the new report folder. In addition to `run.log` and `build_request.json`, it now saves `connector_probe_*.json` with the failed temporary instance's triangles in feet, family identity and section inputs. These local diagnostics are for exact geometry replay; no vendor RFA or project mesh is bundled or published.

## Evidence and limits

See [local test results](TEST_RESULTS.json) and [packaging/API checks](LOCAL_VALIDATION.json). Added tests use a closed synthetic shape with the published gross dimensions, equal flanges and overlapping tails. They cover arbitrary transforms, triangle order/winding, narrow/refined meshes, selective triangulation density, plate-line mapping at near/far/paired sides, incorrect dimensions and custom-model rejection. Adapter checks cover family-name identification, diagnostic replay files and rollback on success/failure.

Nail regressions check schematic centers against actual synthetic face triangles, disjoint metal intervals and invalid rails. Complete measured hole groups take precedence over fallback rails. An empty optional rail does not prevent fitting a connector when schematic nails are not requested. These checks validate center positions; schematic heads/shanks do not establish manufacturer detailing.

The user's complete native triangle mesh was not available during this repair. Logged planes/bounds and the official drawing informed the correction; the synthetic fixture is not a captured Simpson RFA. This build has not been run by the agent in Revit. Native confirmation remains required in Revit 2025 and 2027. The menus were unchanged, so the existing 13-screen offscreen review still applies.
