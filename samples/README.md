# Test Samples

IFC test files for the FSB Door Check pipeline.

| File | Schema | Doors | Spaces | web-ifc | Notes |
|---|---|---|---|---|---|
| `Clinic_Architectural_IFC2x3.ifc` | IFC2x3 | 254 | 269 | ✓ | Primary test model. Has IfcRelSpaceBoundary → PASS/FAIL/non_passage mixed results. |
| `SampleHouse_IFC4.ifc` | IFC4 | 3 | 4 | ✓ | IFC4 schema path validation. |

Additional samples available in the workspace root `samples/` directory:
- `Duplex_xeokit.ifc` — 14 doors, no space boundaries → all non_passage
- `Duplex_Apartment_IFC2x3.ifc` — 14 doors, web-ifc incompatible (old Revit export)
- `Revit_SnowdonTower_ARC_FireRating_IFC4.ifc` — no IfcSpace entities
