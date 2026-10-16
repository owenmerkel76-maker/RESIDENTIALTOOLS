# Material workflow and placement repairs — 2026.10.14.3

**Historical baseline:** see [2026.10.14.5 detail repairs](DETAIL_REPAIRS_2026-10-15.md) for current mounting, screw and nail behavior. Earlier rotation/count instructions below are superseded where noted.


**Later .4 update:** [border fastening choices and supported placement](BORDER_FASTENING_2026-10-14.md) supersedes this version's border/face-fastener limitations. The material, pricing and beam instructions below remain applicable.

This field-test build changes the live extension and the authorized Desktop test copy. It has not been executed by the agent inside Revit. Reload pyRevit and confirm **2026.10.14.3** in the designer title; save/restart Revit if cached modules persist.

## Material List: use this first

1. Build or rebuild a managed deck. Open **Material List**.
2. Choose **Revit schedules (recommended)** and All managed decks or one deck. Choose **Create selected output**. Other pricing/stock inputs are irrelevant to this action.
3. A schedule opens, with other generated category schedules under **Schedules/Quantities** in the Project Browser. Framing, generic models, connectors and available accessory categories are separate native schedules. Columns include deck, component, family/product, actual section, cut length, summed length, material and piece count. Every physical beam ply/segment counts separately.
4. Run Material List again after manual edits, family-type changes, copies or deletions. Generated rebuilds populate new elements after these parameters have been enabled. Length metadata is a refreshed snapshot, not an automatic edit-event monitor. Unknown current type dimensions stay blank with a warning.
5. The tool updates only schedules bearing its ownership stamp. It preserves their view IDs, so placed schedule views remain referenced, but refresh resets those managed views' field/group/filter configuration. User-created schedules are untouched. Duplicate managed schedule copies stop with an error. Shared parameter names/GUIDs are checked; a conflicting unrelated parameter is never replaced.

Dedicated RTD_* instance parameters provide scope and quantities. Refresh clears only RTD_Scope on unregistered copied pieces in relevant categories, excluding them from these managed schedules without deleting geometry or changing Mark/Comments. Worksharing permissions can prevent a refresh; the transaction then rolls back. The user's shared-parameter file preference is restored after temporary definition creation.

## One CSV and optional retail pricing

- **Materials + pricing CSV** creates one `materials_and_pricing.csv`. Blank/unverified prices stay blank and are excluded from subtotals. LF means installed linear feet, EA means modeled pieces/assemblies, STOCK means estimated composite stock boards including allowance. Taxes, delivery, unmodeled fasteners, wood-stock waste, footings and post hardware are not inferred.
- **Supplier pricing template CSV** creates `supplier_prices.csv` with stable item keys. Enter unit_price, unit, supplier, currency, source_url and price_date; choose it with **Browse** on the next priced export. Do not change item keys. Choose LF, EA or STOCK deliberately.
- **Lowe's / Home Depot pricing worksheet** opens a local browser worksheet with product-search links for ZIP **19464**. Review the exact product, grade/treatment, section, length, package quantity, store and price. Enter pricing units per retail board/pack (for example, 16 LF per 16-foot board). Mark a quote verified only after checking it, then download supplier_prices.csv and import it for the priced export.
- Existing exact retailer product URLs in that optional CSV receive a bounded public-page lookup. Only a single explicit USD product offer is accepted; no guessed search-result prices, login or access-control bypass is used. Both real public-page smoke checks returned **HTTP 403** on October 14. Browser review/manual entry is the working fallback; automatic local-store pricing is **not verified**. Fixture prices in automated tests are not quotes.
- The previous detailed four-CSV/JSON reports remain under **Detailed legacy reports**, rather than being the default workflow.

## Built-up beams

In **4. Supports**, select the framing type for **one ply**, verify its actual width/depth, then choose **2 or 3 touching plies**. Posts and hurricane-tie crossings remain coordinated with two logical beam assemblies. Each physical ply is a separately registered native Structural Framing member. Rebuild replaces the old registered beam pieces and preserves unrelated manually placed members.

Set maximum beam piece length. Runs exceeding stock are split at modeled post centers; every ply receives countable stock-limited pieces. A 35-foot run with 20-foot maximum stock creates four pieces per two-ply assembly, or six per three-ply assembly. Review splice bearing and fastening. This is geometry/purchasing coordination, not automatic built-up beam or connection capacity design.

## Hardware

- Single/double hanger, hurricane tie and corner-angle pickers exclude recognized products from other roles. Unknown custom families remain explicitly user-verified. Touching double joists use one double hanger at each eligible end; spaced joists use singles. Ties remain at modeled beam crossings.
- Hanger requests carry the actual inward member direction. The family rotation defaults to **180 degrees**, reversing the previously reported facing. Choose 0/90/180/270 for a custom family's axes. Point instances align to an absolute target, accounting for insertion rotation; work-plane families use the host reference direction. Test both ends and rotated footprints before accepting the fit.
- The previous A35 CAD download is no longer automatically offered as a corner bracket: its bend/origin was not calibrated for this workflow. Use a reviewed loaded L70/L90 or custom angle, or open official Drawing Finder. No verified direct L70/L90 RFA URL was found, so none is invented. Existing vendor families are not overwritten or deleted.
- Corner angles use inside rim faces at convex 90-degree corners, initially at joist bottom with adjustable height/rotation. Return/skew corners are skipped and warned; their hangers are retained. Only modeled corner brackets suppress nearby end hangers. Actual vendor-family seat, bend, mounting face, coating and fasteners still require native review.
- Per-hardware requested position/direction/rotation/type are logged, alongside the saved build request. Neither model count nor nominal product match establishes a connection design.

## Clip repair and exact test

The previous angled-field routine could omit crossing blocking, rim or border-backing supports because it checked only selected joist roles. One shared gap-crossing planner now tests all finite top-framing crossings, verifies grooved long edges on both adjacent field boards and deduplicates coincident intersections. Requests retain the support key/role for diagnosis.

Rebuild the pictured deck and inspect long field-board gaps next to picture-frame backing, diagonal blocking and butt-joint supports. Compare the preview count with native clip instances; rebuild twice and verify no duplicate clips and no change to unrelated model elements. The old project report was unavailable, so the exact screenshot has not been reproduced in Revit.

Square-edge picture-frame/breaker boards deliberately receive no hidden clips at ungrooved edges or end grain. Starter/face fasteners and a separate grooved-border fastening workflow remain incomplete. Do not count those as supplied by this repair.

## Validation and remaining work

134 local tests pass. Python syntax/Python-2 grammar, YAML, XAML names/events, ribbon completeness, icons, preserved original files and installed 2027 API members are checked. Eight WPF sample screens were rendered offscreen; the retail worksheet's JavaScript export was executed with a DOM fixture. These checks do not replace native Revit 2025/2027 execution, family flex or hardware fit tests.

The accessory collector was corrected to filter instances and types before extracting IDs, addressing the recorded Revit 2027 railing error. Stair geometry was not redesigned. The user's future **drop-header stair attachment** preference is recorded in USER_PREFERENCES.md for the later stair phase.

## Primary references

- [Autodesk shared parameters](https://help.autodesk.com/cloudhelp/2024/ENU/Revit-API/files/Revit_API_Developers_Guide/Basic_Interaction_with_Revit_Elements/Parameters/Revit_API_Revit_API_Developers_Guide_Basic_Interaction_with_Revit_Elements_Parameters_Shared_Parameters_html.html), [native schedule fields, grouping and filters](https://help.autodesk.com/cloudhelp/2024/ENU/Revit-API/files/Revit_API_Developers_Guide/Basic_Interaction_with_Revit_Elements/Views/View_Types/TableView/ViewSchedule/Revit_API_Revit_API_Developers_Guide_Basic_Interaction_with_Revit_Elements_Views_View_Types_TableView_ViewSchedule_Working_with_ViewSchedule_html.html). Installed Revit 2027 XML separately confirms the used members; 2025 execution remains a host test.
- [Simpson A35 bend and installation guidance](https://www.strongtie.com/resources/product-installers-guide/a35-installation), [US angles/product submittals](https://www.strongtie.com/resources/product-submittal-generator?v=%3Aname-asc%3Acategory%3AFramingAnglesandPlates_AnglesandPlates), [Drawing Finder](https://www.strongtie.com/search).
- [Home Depot local-price terms](https://www.homedepot.com/c/Terms_of_Use), [Home Depot example product](https://www.homedepot.com/p/315376336), [Lowe's example product](https://www.lowes.com/pd/2-in-x-10-in-x-20-ft-2-Pressure-Treated-Lumber/1000698168). These links are review examples, not automatic catalog matches or verified quotes.
