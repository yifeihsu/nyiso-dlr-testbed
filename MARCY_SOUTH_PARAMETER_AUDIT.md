# How the paper sets the Marcy South parameters

Verified on **2026-10-09** against the supplied final IEEE paper and the pinned
NYgrid source, commit `47698b6c7823ae7b1bc6935e5601d5b64b8f918e`.

**Finding:** the two reactances are approximately reproducible from the paper's
length-times-tabulated-reactance calculation. The available evidence does not
establish a complete physical line model: the resistance, charging, conductor
installation, circuit/bundle geometry, and thermal rating are not derived by
that calculation. The original NYPA document cited for the lengths and conductor
identification remains unavailable in this audit. No model parameters were changed.

## 1. What is explicitly in the paper and code

The supplied final paper, PDF page 7 / journal page 3299, equation (10), uses

\[
X_{\mathrm{pu}}=\frac{L X_L}{Z_{\mathrm{base}}},\qquad
Z_{\mathrm{base}}=\frac{V_{\mathrm{base}}^2}{S_{\mathrm{base}}}.
\]

It gives 137 miles for buses 43-38, 47 miles for 38-77, and a tabular value
`X_L = 0.371`. The paragraph does not print a unit beside 0.371. Interpreting
it as ohms/mile is consistent with the stated mile lengths and released code.
The case has a 100 MVA base and the three buses have 345 kV nominal voltage:

\[
Z_{\mathrm{base}}=345^2/100=1190.25\ \Omega.
\]

| Quantity | 43-38 | 38-77 |
|---|---:|---:|
| Downloaded bus names | EDIC-GILBOA | GILBOA-BUCHANAN |
| Source bus zones | E-E | E-G |
| Paper-assigned length, miles | 137 | 47 |
| `L * 0.371`, ohms | 50.827 | 17.437 |
| Calculated X, pu | 0.04270279353 | 0.01464986347 |
| Released X, pu | **0.0427** | **0.0147** |
| Code difference from literal calculation | -0.00654% | +0.34223% |
| Released R, pu | **0.0200** | **0.0200** |
| Implied R, ohms | 23.805 | 23.805 |
| Implied R per paper-assigned mile, ohms/mile | 0.173759 | 0.506489 |
| Released branch charging B, pu | 0 | 0 |
| RATE_A / RATE_B / RATE_C | 0 / 0 / 0 | 0 / 0 / 0 |

The longer segment matches ordinary four-decimal rounding. Strict rounding
of the shorter segment's literal calculation gives 0.0146, not 0.0147. This
is a small precision inconsistency, not proof of a major numerical error.
An unrounded underlying coefficient can explain it, but the authors' exact
intermediate calculation was not recovered.

The exact rows in [the pinned source](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/modifyMPC.m#L73)
are:

```matlab
newlineEG  = [38 77 0.02 0.0147 0 0 0 0 0 0 1 -360 360];
newlineEG2 = [43 38 0.02 0.0427 0 0 0 0 0 0 1 -360 360];
```

Both records are active, with unity-tap convention (`tap=0`), no phase shift,
and +/-360-degree angle bounds. Neither endpoint pair exists in either
orientation in the raw downloaded NPCC case. The added rows are preserved
identically in the stored full pre-device, full final-device, and reduced
final cases. Their row numbers differ, so the audit matches endpoints rather
than copying indices. [Recalculation CSV](output/marcy_south_parameter_audit/parameter_recalculation.csv)
and [machine-readable findings](output/marcy_south_parameter_audit/audit_summary.json).

## 2. What 0.371 does and does not establish

The paper cites Stevenson and Grainger, *Power System Analysis* (1994), for
an ACSR conductor table. The exact publisher table page was not independently
recovered. A primary manufacturer cross-check is available:

- [Prysmian/General Cable TransPowr ACSR sheet, PDF page 5](https://na.prysmian.com/sites/na.prysmian.com/files/media/documents/TransPowr%C2%AE%20ACSR%20Bare%20Overhead%20Conductor%20%28US%29.pdf#page=5)
  lists Bobolink 1431-kcmil, 45/7 ACSR with inductive reactance 0.0703 ohm/kft.
  Multiplication by 5.28 gives **0.371184 ohm/mile**. The table footnote states
  a **one-foot reference radius**. Using this converted catalog value produces
  0.04272397 and 0.01465713 pu, which round to the two released values.
- This is a **numerical match**, not proof that Bobolink was installed on the
  represented routes or that the authors used this exact manufacturer value.
- [PowerWorld's official line-parameter manual, printed pages 6 and 13-14](https://www.powerworld.com/files/TransLineCalcHelp2.pdf#page=8)
  distinguishes the conductor-table value at one-foot spacing from the line
  calculation using phase spacing and conductor/bundle geometric mean radius.

For the standard transposed, single-conductor, three-phase 60-Hz approximation,

\[
x_1=0.12134168\ln(D_{\mathrm{GMD}}/\mathrm{GMR})\quad\Omega/\mathrm{mile}.
\]

Bundled conductors require the composite bundle GMR. Parallel circuits and
series capacitors affect the equivalent impedance as well. The published
`L * 0.371` expression does not document these physical inputs. Therefore the
audit does **not** conclude that the released values must be increased, or
replace them with an arbitrary alternative; it concludes that their physical
derivation is incomplete.

## 3. Lengths, route identity, and historical equipment

Reference [43] is NYPA, *Communication Backbone OPGW Expansion Project*,
Design, Engineering and Construction Schedule, September 18, 2018. The exact
document was not located through the searches and public library sources
checked. Its phase-conductor and bundle details remain unverified. OPGW is
ground/shield wire; the title alone cannot prove that the missing document
did, or did not, also describe phase conductors.

Independent primary evidence helps constrain interpretation:

- A [NYSEG/RGE utility exhibit, January 2010, PDF page 3](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BED6519E1-E297-41CE-87AF-8EA2E4B4F92C%7D)
  lists **line 33, Fraser-Coopers Corners, as 47 miles**. This supports a real
  47-mile circuit, but not its one-to-one identity with the model's Gilboa-
  Buchanan proxy. The paper's 137-mile value was not independently corroborated.
- A [NYPA/NYSEG filing dated May 20, 2013, PDF pages 3, 10-11](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BC26585B8-A63F-4E27-A206-67419899B082%7D&DocTitle=Marcy+South+Series+Compensation+Project+Submittal+of+Comparable+Information+-+Redacted)
  identifies three circuits: Marcy-Coopers Corners (UCC2-41), Edic-Fraser
  (EF24-40), and Fraser-Coopers Corners (FCC-33). It proposes 40%, 25%, and 25%
  series compensation, respectively. FCC-33's then-existing conductor is
  described as 2156 ACSR; two replacement products were under consideration
  for a 21.8-mile section. Those proposed choices are **not verified 2019
  installed specifications**.
- [NYISO's 2019 Interim Area Transmission Review, Table 4, printed page 9](https://www.nysrc.org/wp-content/uploads/2023/04/2019_NYISO_Interim_ATR_Draft_vNYSRC_v2.pdf#page=13)
  records series compensation on all three circuits as in service. The paper's
  two positive-X rows and length formula do not document how those devices,
  their switching states, or the three-circuit topology are represented.

The downloaded proxy coordinates give straight-line distances of about
42.68 miles for 43-38 and 77.96 miles for 38-77. The latter exceeds the
paper-assigned 47 miles. These coordinates are not surveyed routes, so this
does not invalidate a physical utility length. It does show why the coarse
bus attachment cannot be treated as a verified literal route for weather or
conductor modeling.

## 4. Other parameters and the DLR consequence

| Parameter | What is established | What remains unverified |
|---|---|---|
| Voltage and case base | 345 kV / 100 MVA in paper/source | Exact circuit-to-proxy mapping |
| Reactance | Approximately matches the stated arithmetic | Conductor selection, phase/bundle geometry, circuit aggregation and capacitor treatment |
| Resistance | Both rows are hard-coded to 0.02 pu | Physical derivation, conductor temperature, bundle/circuit count |
| Charging | Both added rows have B=0 before reduction | Physical capacitance/charging |
| Thermal rating | All three rating fields are zero | Installed ampacity, equipment ceiling, temperature/sag limits |

Zero ratings mean no supplied MATPOWER thermal limit; they are not measured
zero ampacity. The reduction later moves existing branch-charging contributions
into bus shunts, which does not reconstruct missing charging for these added
rows. DC power flow does not validate their R/B or conductor heating merely
by matching MW flows; those quantities do not determine its lossless branch
flow equations. [MATPOWER DC formulation](https://matpower.app/manual/matpower/DCModeling.html).

A bounded source-history check found the 38-77 X progression 0.020 -> 0.015
-> 0.0147 pu. The [December 2021 change](https://github.com/AndersonEnergyLab-Cornell/NYgrid/commit/23c181329e4484426983b95bffa934b7ce1f0e3d)
retains R=0.02; the [May 2022 revision](https://github.com/AndersonEnergyLab-Cornell/NYgrid/commit/cc473fdfe19bbd21a4240611fd77141404b84256)
identifies the two-segment Marcy representation. Neither inspected message
establishes a resistance derivation or a documented calibration procedure.

The current first DLR screen already excludes both added aggregate rows.
That exclusion remains appropriate until physical circuits, route sections,
installed conductors/bundles, and 2019 compensation are reconciled. The
source-faithful DC benchmark remains unchanged.

## Reproduce the numerical audit

From this repository root:

```powershell
python scripts/nygrid_2019_full/audit_marcy_parameters.py
```

Use `--paper <absolute-path>` if the supplied PDF is not in the user's Downloads
folder. The script verifies pinned input fingerprints, recomputes the two
rows, and checks their preservation in the saved cases. It does not perform
network fitting, rerun the annual model, or assign physical DLR eligibility.
[Reference receipts](output/marcy_south_parameter_audit/source_receipts.json)
record the inspected source URLs, pages, hashes, and unresolved provenance.
