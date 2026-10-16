# Compact AC model anchored to the 148-bus system

The public entry point is `run_nygrid_2025_compact_acpf`. It solves the complex
AC admittance equivalent on the 148 retained buses, then recovers voltages,
terminal powers and physical branch currents in the detailed network. No OPF
or full-network Newton solve is used inside this entry point.
The example assumes MATLAB and MATPOWER 8.1 are installed and on the MATLAB
path; the project wrapper adds its own helpers but does not install MATPOWER.

```matlab
cd('C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems');
addpath('System Matpower Format');
[compact_result, audit, recovered] = run_nygrid_2025_compact_acpf(8508);
assert(compact_result.success && audit.reduction_and_equation_gate ...
    && audit.P_profile_preservation_gate);
size(compact_result.bus, 1)                 % 148
Iseries_A = compact_result.recovered_line_current_A(:,3);
```

`audit.reduction_and_equation_gate` establishes the AC equation and algebraic
recovery checks. Operating-limit qualification remains a separate audit
field, `audit.VQ_and_generator_assumption_gate`. Profile preservation is
checked by `audit.P_profile_preservation_gate`. The default PF preserves
demand, non-slack active generation and all six transfer active-power targets;
the original slack adjusts to supply AC losses. Neither profile preservation
nor operating-limit qualification is implied by the reduction/equation gate.
A converged solution can violate voltage, generator capability or
converter assumptions inherited from the detailed model.

The model is a matrix network. Use its dedicated solver rather than passing
it to MATPOWER `runpf`: the entries of `Yred` are equivalent couplings, not
physical lines with conductor ratings. The third returned value is a usual
detailed MATPOWER result with algebraically recovered bus and branch arrays.

## Retention and exact recovery

Let `k` be the 148 anchor buses and any additional required injection/control
ports, and let `e` contain the passive, zero-injection interior buses. With
the original complex admittance matrix partitioned in that order,

```text
K = -Yee \ Yek
Ve = K Vk
Yred = Ykk + Yke K
Vfull = L Vk
Ifull_from = Yf L Vk
Ifull_to   = Yt L Vk
```

Resistance, charging, fixed shunts, off-nominal taps and phase shifts are
included before elimination. The implementation retains complex,
potentially non-symmetric admittances and does not prune small entries.
Eliminated connected components must touch a retained bus and `Yee` must
pass the conditioning and elimination-identity checks.

Additional nonzero loads, generators, DC terminals or PV/reference controls
outside the 148 anchors are retained automatically. Fixed admittance shunts
do not require additional voltage states. The current input model requires
no additional retained buses. This preserves the requested 148-bus interface;
it is not a claim that 148 is the global minimum for every use case.

The result's current columns are `from_terminal_A`, `to_terminal_A` and
`series_A`. Terminal currents include charging and use their own terminal
voltage base. Series current excludes charging and uses the receiving-side
base for transformer rows. For overhead conductors at equal terminal kV,
series current is the relevant Joule-heating current. Do not assign physical
ratings to reduced matrix couplings, and do not treat cable or mixed-device
equivalent currents as validated overhead DLR assets.
Current row `j` corresponds to `recovered.branch(j,:)` and its full branch key
when available; it does not correspond to a row or column of `Yred`.

Currents are amperes on the unchanged 100-MVA-base synthetic model with its
existing scaled inputs. They must never be divided by `gamma`; that scale is
used only for comparing aggregate MW with the public observations. Recovered
model currents are not observed NYISO ampere telemetry.

## Changing a physical parameter or operating input

Build a fresh compact model after changing a physical branch resistance,
tap, status, shunt, load or control. For example, an electrothermal iteration
must update physical `R(T)` before rebuilding the operators:

```matlab
m = npcc_nygrid_2025_ac(8508);
% Apply a justified physical parameter change to m here.
[r, audit, full] = run_nygrid_2025_compact_acpf(m);
```

The cached source and operator fingerprints reject accidental edits to a
previously built model. Do not edit `Yred` or recovered-current operators in
place. Hourly constructor calls obtain the dated topology and profiles from
the same detailed source used for validation.

## Controls and available artifacts

The solver uses MATPOWER's polar power-mismatch Newton kernel, generator
reactive-power allocation and DC-line conversion. Its reactive-limit modes
0, 1 and 2 follow the installed MATPOWER legacy policy; all controller
terminals remain in the retained set. The default comparison uses mode 0,
matching the frozen detailed annual baseline. Mode 1 is tested separately.
This wrapper does not implement AC OPF or alternative Cartesian/current
Newton formulations.

`export_models` saves fixed-hour matrix examples for all four dated topology
states and hour 8508. These files carry the detailed source and conductor
metadata needed for reconstruction; the nonlinear solve still has only the
retained bus states. The root report `NYGRID_2025_COMPACT_AC.md` describes the
validation results and links the reproducible evidence. The baseline detailed
model, input profiles and prior sealed audit remain unchanged.
