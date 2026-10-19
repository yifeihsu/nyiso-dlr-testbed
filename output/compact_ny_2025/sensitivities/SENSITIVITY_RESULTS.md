# Compact NY 2025 S1 electrical assumption sensitivities

8 of 8 prespecified variants pass bounded AC reconstruction and independent fixed-input power flow. These are S1 training fits; no held-out observations or automatic parameter selection are used.

Every case uses the same 2025-07-29 18:00 public evidence, year-peak gamma 0.355758660106238, gross benchmark demand 10,902.2198 MW, and ten-channel boundary policy. MIPS start0 is tried first; unchanged-input IPOPT fallback is retained where required. All successful and failed attempts have full independent bus, generator and branch audits.

| Variant | AC qualified | Solver | MAE MW | Maximum error MW | Pmax change MW | Active branches |
|---|---:|---|---:|---:|---:|---:|
| nominal | 1 | MIPS | 2.017 | 3.207 | 0.000 | 112 |
| impedance_075 | 1 | MIPS | 1.978 | 3.207 | 0.000 | 112 |
| impedance_125 | 1 | MIPS | 2.051 | 3.203 | 0.000 | 112 |
| charging_zero | 1 | MIPS | 2.025 | 3.209 | 0.000 | 112 |
| charging_150 | 1 | MIPS | 2.009 | 3.207 | 0.000 | 112 |
| RCC_announced_paths_off | 1 | MIPS | 2.015 | 3.197 | 0.000 | 110 |
| Astoria_retirement_not_assumed | 1 | MIPS | 1.970 | 3.140 | 187.841 | 112 |
| South_Fork_zero_available | 1 | IPOPT | 2.015 | 3.206 | -46.960 | 112 |

Impedance/charging factors apply only to the infrastructure overlay fields declared by its builder; they do not modify every inherited NPCC branch. RCC-off opens the two announced cable through paths while retaining zero-injection station stubs. The Astoria case restores an assumed retired share in a generic aggregate; it does not identify an original physical machine. South Fork zero availability changes the assumed upper bound, not observed wind output.

Interface operators remain model proxies, generation dispatch is reconstructed, and inherited aggregate reactive limits remain assumptions. A low training error cannot validate the operator mapping, dispatch, physical parameter values, or thermal ratings. A failed variant is a solver/electrical outcome under that assumption, not a proof of global infeasibility. No DLR qualification follows from this campaign.
