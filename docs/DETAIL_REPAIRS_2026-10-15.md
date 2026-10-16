# Deck detail repairs — 2026.10.14.5

**Historical .5 baseline:** the user's Revit build exposed an incorrect H2.5A tab-height assumption. Its transition-center datum and .5 retry instructions below are superseded by the [2026.10.15.1 H2.5A repair](H25A_PROBE_REPAIR_2026-10-15.md). The other detail improvements remain in the current build.

Prepared October 15, 2026. Live source and authorized Desktop test copy only. This update supersedes the earlier fixed-rotation and border-screw instructions. Material List host testing remains on hold.

## Implemented

- **Field boards:** full board at start (default), full board at end, or balanced edge rips. START/END labels appear in plan preview. Gaps stay as entered. A final rip under 1/2 inch rejects that choice; a rip too narrow for the chosen face setback explicitly reports an omitted face row. Angled outline intersections still trim the strips.
- **Square framing corners:** through horizontal rims and butted vertical rims replace the inset-centerline corner gap/overlap. Collinear joist coverage is subtracted from rim runs. Rectangular and stepped orthogonal outlines have local footprint coverage/non-overlap regressions. Non-orthogonal native end cuts/joins remain a reviewed detail.
- **Hangers:** a temporary native instance is measured, then rolled back. Seat top, rear mounting face and channel center determine placement. A single/double hanger is fitted to the actual member direction and bottom elevation. The old 0/90/180/270 family-rotation and origin choices are removed from the UI; saved legacy values are ignored by the new mounting workflow.
- **L corner angles:** the two measured contact faces fit the inside rim faces. The long axis mounts vertically, centered on joist depth. Angles taller than the joist and ambiguous/non-simple geometry stop the build. Convex square corners are supported; return/skew corner details remain deferred.
- **Hurricane ties:** measured H2.5A-style upper/lower perpendicular tabs replace center-of-beam insertion. The upper tab fits a joist side; the lower tab fits the outer face of the built-up beam. Their transition centers on beam top. Near/far ties use compatible diagonal sides. Touching pairs use exposed outer joist faces with compatible opposing beam faces; interior plies of a larger touching group receive no buried tie. This requires a native fit test; other tie geometries are not silently assigned H2.5A axes.
- **Face screws:** mandatory end/miter setbacks plus shared rail stations replace independent per-rail grids. Touching joist groups supply one regular station toward the board middle. Flat first/last field edges receive a face row when enabled. Clear-bay backing is added or shared without moving the requested screw positions. Unsupported points remain marked/excluded.
- **Hardware nails:** individual countable Generic Model DirectShapes, each with a schematic shank/head, connector key/model, application, diameter, length, finish and source. Separate hanger header-face and 45-degree double-shear joist groups; separate tie joist/beam tabs and corner legs. Native CAD holes are preferred only when a complete matching group is measurable. Otherwise the group uses an explicitly reported schematic mounting-face pattern. These fallback coordinates are not manufacturer hole-location data.

All new model elements retain exact registry ownership and atomic replacement. Probes roll back. New geometry is checked before old layout deletion. Pinned/grouped elements and unsafe cascading deletion still stop replacement. Manually placed unrelated elements and other extensions, including ROBMEPTOOLS, are preserved.

## Nail schedule scope

| Recognized connector | Published quantity groups | Common nail option |
| --- | --- | --- |
| LUS24 | 4 header + 2 double-shear joist | 0.148 x 3 in |
| LUS26 | 4 + 4 | 0.148 x 3 in |
| LUS28 | 6 + 4 | 0.148 x 3 in |
| LUS210 | 8 + 4 | 0.148 x 3 in |
| LUS210-2 | 8 + 6 | 0.162 x 3.5 in |
| H2.5A | 5 joist + 5 beam | 0.131 x 2.5 in; selectable published 1.5-in alternative |
| L70 / L90 | 8 / 10 total, divided between legs | 0.148 x 1.5 in |

The **Single 2x header — reduced-load option** uses 0.148 x 1.5-in header nails and 0.148 x 3-in double-shear nails. It is distinct from full-length common nails; capacity is not calculated. A 1.5-in hanger nail is never substituted for the angled double-shear joist nail. The H2.5A 1.5-in alternative also has different published loads. Exact model, support thickness, material/finish, treatment, penetration and installation conditions need project review. Unknown/custom models receive no invented nail schedule.

The current defaults leave nail finish **Unspecified — review**. Pick the project finish deliberately. SS/HDG compatibility and supplier SKU are not inferred from a CAD filename. Three-dimensional nails are schematic, even when their CAD hole centers are measured.

The material collector counts registered nails as **EA**, grouped by product/size/finish/application. Native schedules label the application; pricing uses the same installed pieces. Connector rows and nail rows are separate physical items. Missing manually deleted nails are reported/excluded, and unregistered copied nails are excluded. This is wired and locally tested; native Material List testing is still paused at the user's request.

## Reproduce the user's last successful deck

Use 19.5 x 11 ft, two picture-frame courses, 5.5 x .94-in boards, .1875-in side gap, .125-in butt gap, 20-ft stock, 1.5 x 9.25-in joists at 16 in O.C., touching double border joists and solid blocking. Choose square-edge + schematic face screws; 1-in border setback, .5-in field-face setback and missing backing enabled. The .5-in field setting follows the user's schematic request; it is not a universal product-approved setback.

Local planner result: 20 field boards, 8 borders, 61 framing pieces, 285 clips, **234 face screws including 30 field-edge screws**, and no unsupported requested screw positions. With full board at start, the first strip is 5.5 in and the opposite rip is 1.1875 in. Swapping to full at end reverses those widths.

With the user's 30 hangers (4 double), 34 H2.5A ties and 4 L90 angles, recognized schedules produce **748 individual hardware nails**: 312 at 26 single hangers, 56 at 4 double hangers, 340 at ties and 40 at corners. These are planner/specification results, not a verified Revit build or a connection design. Actual placed counts are saved after native creation.

## Test in Revit next

1. Save the project. Reload pyRevit. If modules remain cached, close/reopen Revit; confirm **2026.10.14.5** in the Deck Designer title. Open the existing managed deck rather than creating a duplicate.
2. In Decking, choose full board at start, preview, then full at end. Check START/END and the rip at the opposite side. Restore the desired edge.
3. In Hardware, keep the actual LUS210, LUS210-2, H2.5A and L90 types. The manual rotation controls should be gone. Leave seat/corner adjustments at zero initially. Enable individual connector nails, choose header condition, tie nail option and finish.
4. Build once. Inspect both hanger ends in section and 3D: seats at joist bottom, mounting flanges on support faces and double hangers centered around touching plies. Inspect L90 vertically against both inside faces. Inspect both beam lines: tie upper tab on joist side, lower tab on beam face, transition at beam top.
5. Inspect rim corners without decking obscuring them. Horizontal rims should run through; perpendicular rims should butt to their inner faces. Review skew/return joints separately.
6. Inspect the red-dot screw locations at each miter; confirm the old nearby duplicate regular positions are absent. Inspect first/last flat field edges and backing. Confirm no screw is counted where the preview marks missing support.
7. Select nails: each should be an individual schematic model element. Inspect face nails versus angled joist nails, lengths/finish identifiers and native-hole/fallback warnings. Check for clashes, protrusion and incorrect hole alignment. A schematic fallback is not a passed native-hole fit test.
8. Rebuild twice: counts should remain stable. Disable connector nails and rebuild: owned nails should disappear while connectors remain. Restore nails. A manually placed unrelated item must survive. Do not resume Material List testing yet.
9. If a family is rejected, retain the new run.log and build_request.json. Logs include measured frames, native mounting diagnostics and failed nail identifiers. The previous managed layout should remain after rollback.

## Validation and limits

**175 local tests pass; zero validation errors.** Checks cover 53 Python files, 36 runtime Python-2 grammar files, 13 YAML files, nine bundles/icons, 13 preserved hashes and 85 installed Revit 2027 DB API members plus one UI member. Thirteen offscreen WPF screens were rendered/reviewed. Local results are recorded in TEST_RESULTS.json, LOCAL_VALIDATION.json and UI_RENDER_REVIEW.json. Checks cover Python syntax and runtime Python-2 grammar, YAML schema, XAML names/events, icons, packaging, preserved hashes, installed Revit 2027 API XML, pure geometry and stubbed native placement/ownership.

The agent has not run this update in Revit 2025 or 2027. The user's earlier .4 build succeeded in Revit 2027, but that does not establish the .5 connector/nail mounting. Arbitrary native CAD models, skewed rim cuts, automatic PA structural sizing, footings/caps/bases and house connections are not completed by this update. Stairs still retain the saved future drop-header preference.

## Primary references checked

- [Simpson LUS installation](https://www.strongtie.com/resources/product-installers-guide/lus-installation): full-length common/double-shear nail distinction.
- [Simpson connector fastener group counts](https://www.strongtie.com/products/fastening-systems/technical-notes/sd-connector-screw-approved-connectors): identified single/double connector groups; screw alternatives are not interchanged with nail specifications here.
- [Simpson double-shear header-condition instructions](https://www.strongtie.com/facemounthangers_engineeredwoodconnectors/hgus_hanger/p/hgus): short-header nail option and different load conditions.
- [Simpson H2.5A installation](https://www.strongtie.com/resources/product-installers-guide/h25a-installation) and [Roof/Wall Selector](https://app.strongtie.com/rws): listed common/short nail alternatives.
- [IAPMO UES ER-112, September 2026 revision](https://forms.iapmo.org/ues_reports/reports/er_0112.pdf), Table 7: L70/L90 fastener counts and installation conditions.
- [Autodesk reference-based family placement](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/be4b822c-829a-7e7b-8c03-a3a324bfb75b.htm): eligible work-plane placement. Installed API XML verifies the exact members used.

Plugin Management catalog searches for Revit / Autodesk BIM returned no matching plugins during this turn. GitHub remains connected. No new plugin was installed.
