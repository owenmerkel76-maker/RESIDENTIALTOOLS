# RESIDENTIALTOOLS implementation report

**Current .5 detail repairs:** [hardware mounting, hurricane ties, individual nails, full-board edges and screw stations](DETAIL_REPAIRS_2026-10-15.md). Native Material List testing is on hold.

**Earlier .4 border-fastening choices:** [grooved clips, face screws, backing and exact tests](BORDER_FASTENING_2026-10-14.md). See also the [schedule, pricing, beam and hardware workflow](MATERIALS_AND_REPAIRS_2026-10-14.md). These supersede older limitations below.

Updated October 15, 2026. Version **2026.10.15.1**, field-test build. Source: this repository. See [H2.5A probe repair](H25A_PROBE_REPAIR_2026-10-15.md) for the failed .5 tab assumption and current retry steps.

The agent has not executed this build inside Revit. User screenshots show native LUS210 instances in Revit 2027; seating, revised origins and all new workflows still require host tests in both supported versions. Generated Lumber Library RFAs are not certified by local checks.

## Implemented features

| Area | Current behavior |
| --- | --- |
| Shared designer | Decking, Framing, Hardware, Supports, Preview & clips tabs; saved settings, editable drafts, plan preview, friendly counts, relevant dependent controls and explicit rebuild. Joist Builder uses the same engine. |
| Footprints | Three-point rectangles or one planar straight-edge Floor loop, including concave stepped returns. Reads actual boundary and preserves the source Floor. Floor extents are locked until re-picked. |
| Decking | Individual Generic Model DirectShapes, schematic grooves, adjustable default 3/16-inch gaps, edge rips, 12/16/20-foot stock, staggered supported seams and independently adjustable angle. |
| Borders and breakers | Optional grooved/routed border clips or square-edge schematic face screws, clear-bay backing and visible unsupported positions. One/two mitered perimeter courses and stock-limited pieces. Clipped cross-deck breaker bands with automatic/manual centers, central joist and touching paired edge supports; long pieces split to stock. Fixed framing keeps breakers along joists while diagonal fields meet them. Clips avoid square-edge bands. |
| Joists/blocking | Loaded native Structural Framing, actual section checks, 12/16/24-inch O.C., rims and solid blocking. Explicit persistent “blocking follows joist,” or separately selected blocking family/section. Searchable loaded joist types. |
| Supports | Two/three separately countable touching plies per drop-beam assembly, stock-limited splices at posts; native two-level Structural Column posts, adjustable sections/setbacks/height/end offsets/maximum spacing. |
| Hardware | Single hangers, one double hanger per touching two-ply assembly end, selected corner brackets suppressing corner-end hangers, ties only at modeled beam crossings. Eligible native work-plane families use owned reference planes. |
| Simpson library | Six directly offered RFA candidates: LUS24/26/28/210, LUS210-2, H2.5A. A35 historical CAD entry is excluded from corner auto-selection; reviewed loaded corner types use a manual workflow. Terms acknowledgement, cache hashes, type selection and provenance. Hardware browsing is independent of unfinished unrelated fields. |
| Deck Stairs | One native straight-run assembly; labeled loaded-type/level/dimension form, input summary, previous settings restored and picked plan direction. Separately managed replacement. |
| Deck Railings | Native perimeter paths; labeled type/edge/opening form, edge lengths/local endpoints, previous selections restored and connected-path preview summary. Separately managed replacement. |
| Deck Manager | Saved/live count distinction, current registered pieces/work planes/accessories, missing/stale warnings, selection, report export and guarded removal. |
| Material List | Native managed category schedules, one materials/pricing CSV, reviewed retail worksheet for ZIP 19464, supplier template and optional legacy details. Border face screws have separate quantities. |
| Pennsylvania | Official UCC/2021 IRC links, entered municipality, centerline support/span/cantilever/post-spacing review, basic PA stair-input checks. No automatic allowable-span sizing. |
| Roof option | One sloped planar Floor may provide a projected outline for a LEVEL deck above its peak with entered clearance. Automatic supports are blocked in this mode. |

Boards can be individually moved/marked/counted/deleted; dimensions change through settings/rebuild, not per-board RFA parameters. Native framing/beam/post actual geometry is checked during building; incompatible geometry aborts and rolls back.

## Ownership and updates

DataStorage records plus element Extensible Storage stamps identify owner/layout/generation. Rebuild checks new geometry before deleting the selected registry's old elements. Unsafe dependent deletion, pinned/grouped elements or changed ownership stops replacement. Missing registered elements are reported. Unregistered copied/manual elements, other layouts, source Floors and family definitions remain preserved.

Generated pieces edited manually within a registry are replaced on rebuild. A changed source Floor must be re-picked. Rebuilding a deck preserves its separately registered stairs/railings; rerun those commands after parent footprint/elevation changes. Material List and Manager warn about stale accessory generations. There is no model-change monitoring.

Hidden clip counts cover eligible modeled grooved field-board connections. Square-edge border/breaker face fasteners, starter clips, nails and screws are excluded. Double hangers are included in total hangers. Owned hardware reference planes are excluded from piece counts.

## Incomplete features

- Verified allowable-span/member sizing needs site loads, species/grade, wet-service/incising, beam ply construction and applicable table footnotes. Measurements are centerline distances, not capacity approval. House/ledger connections remain deferred by request.
- No footings, roof stanchions, post caps/bases, lateral bracing or generated built-up beam plies. One selected family instance represents each beam.
- No Floor holes/curves/multiple loops, multi-facet roofs, pitched decking/framing or automatic multi-zone support design. Some concave footprints require separate support layouts. Skewed and return-corner backing/details require review.
- Stairs are one native straight run, not complete wood-stringer fabrication; complex stairs/landings and full stair/guard design remain future work. Native types control component details. Railing opening is manually selected, not inferred from the stair.
- Lumber Library remains the preserved untreated 2x10, treated 2x10 and I-joist prototype. Full LVL/LSL/PSL/C-joist catalogs, specialized rims and X-bridging remain future work.
- Hardware fit/origin/orientation/coating/capacity/fasteners need verification. Adaptive and face/wall/floor-hosted hardware is unsupported; no vendor RFAs are bundled.
- Stock estimates pack lengths within compatible groups; no optimized nesting/ripped-width recovery. Rotated/width-changed boards are excluded from stock estimates with warnings. Native stair/railing subcomponent materials require schedules. Unmodeled items are not inferred.
- Rebuild replaces ElementIds; annotations may need reassociation. Worksharing/design options are not host-tested.

## Inspection, files and checks

All nine commands/shared backends were reviewed. Historical source paths/hashes remain in `SOURCE_INVENTORY.json`; recorded FRAMETOOLS/DECKTOOLS files are currently unavailable. Earlier selective geometry reuse is documented, but no new migration or complete legacy parity is claimed. No RVT was opened/mined for families.

Both Hello Worlds and Lumber Library retain 13 original-file hashes. No ROBMEPTOOLS or other extension was edited; no nested `.extension` folder was created.

New in this sweep: `lib/rt_presentation.py`, `lib/rt_forms.py`, `resources/ToolOptions.xaml`, `release.json`, four tab/panel `bundle.yaml` manifests, `tests/test_review_quality.py`, this release review and `docs/UI_RENDER_REVIEW.json`. Existing shared modules, designer XAML and documentation were edited in place. The delivery manifest lists every packaged file and SHA-256.

**Current local results:** see TEST_RESULTS.json and LOCAL_VALIDATION.json for exact counts. The .5 report above supersedes earlier mounting/fastening limitations; native Revit execution remains unverified.

See `REVIEW_2026-10-14.md` for per-tool changes/comparisons and `REVIT_TEST_CHECKLIST.md` for host verification. Publishing a ZIP makes the field-test build downloadable; it does not establish native family or structural correctness.

## 2026.10.14.2 — post alignment correction

The reported build stopped at `POST_1_1`: expected 5.5 inches, measured 6.63 inches. The previous placement added the planned deck angle to any existing column insertion rotation. A rotated square can produce exactly this enlarged projected width even when the actual section is correct. Local regression geometry reproduces the reported values; the actual user's family has not been inspected in a Revit API session.

New columns are aligned to the absolute planned beam/post axes using `Instance.GetTransform()` before section checks. An offset insertion origin is compensated horizontally so the measured solid centers under the planned beam point. Width, depth, height and base/top checks remain strict; real section differences still abort/roll back. Standard loaded 4x4/6x6 types use their actual entered/type-parameter dimensions; no nominal size is guessed and no existing family is edited.

Failure logs now identify the selected post family/type, initial/target/correction angles, measured/expected values in inches and any centering shift. `build_request.json` retains attempted settings/anchor/counts before a native build, including failed builds. This file stays in the local Reports folder.

Six added regressions cover the reported rotated 6x6 projection, loaded 4x4 dimensions with combined deck/post angle, rectangular sections, offset origins, incompatible section and failed rotation. Total: 109 passing local tests, zero packaging errors and 48 installed Revit 2027 XML members checked. Native Revit confirmation of the user's selected post family remains required.
