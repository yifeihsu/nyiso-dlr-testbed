# S6 scaled-interchange and zonal-net-injection PF assessment

> Historical five-interface assessment. The S6 CSVs were subsequently
> regenerated with Dysinger East and West Central added. Use
> `s7_seven_interface_perform_calibration_assessment.md` for the current
> seven-interface results and tie-line decision.

## Implemented formulation

S6 uses the S4 NY boundary-equivalent network. The external NPCC mesh is
removed for this test because a standard PF cannot independently enforce each
public external interchange schedule in an intact meshed external system.
Scaled P-32 external schedules are represented by fixed boundary generators.

For each public hour, the following quantities are applied:

```text
L_z       scaled P-58C zonal load
I_z_ext   scaled P-32 external import at boundary buses
F_m       scaled P-32 internal-interface target
```

The inferred zonal generation vector is obtained from:

```text
min_g  sum_m ((F_dc,m(g) - F_target,m) / S_m)^2
       + lambda * sum_z ((g_z - g_prior,z) / S_z)^2

subject to
       sum_z g_z = sum_z L_z - sum_z I_z_ext
       PMIN_z <= g_z <= PMAX_z
```

`F_dc(g)` is the DC response of the actual reduced NPCC topology. The weak
prior is the scaled PERFORM 2019 on-peak zonal dispatch. PERFORM GSKs allocate
each inferred zonal total to retained NPCC generator buses. Native and effective
net injections are then:

```text
N_z_native    = g_z - L_z
N_z_effective = g_z - L_z + I_z_ext
```

This constrained inverse is required because the five available P-32 internal
interfaces do not uniquely identify eleven zonal injections.

## Flow results

| Metric | Result |
|---|---:|
| Public scenarios | 6 |
| Standard AC PF convergence | 6 / 6 |
| Q-limit-enforced PF convergence | 5 / 6 |
| Maximum external schedule error | 1.14e-13 MW |
| Sum PERFORM-prior DC interface objective | 4.03984 |
| Sum inferred DC interface objective | 0.00716 |
| Sum standard AC PF interface objective | 0.27796 |
| Maximum AC interface residual | 573.1 MW |

| Interface | Mean absolute AC residual | Maximum absolute AC residual |
|---|---:|---:|
| Moses South | 24.7 MW | 45.8 MW |
| Central East | 115.9 MW | 134.9 MW |
| Total East proxy | 151.8 MW | 236.7 MW |
| UPNY-ConEd | 276.7 MW | 417.3 MW |
| Dunwoodie South | 280.7 MW | 573.1 MW |

The previous full-NPCC `PERFORM_GSK__current` PF score was 3.53394. The S6
score is much lower, but the comparison is not perfectly like-for-like because
S6 uses an exact boundary equivalent and estimates injections from the same
P-32 targets being scored.

## Remaining feasibility problems

The flow match is improved, but S6 is not fully AC-feasible:

- Branch 29, Niagara West-Huntley, is overloaded in all six standard PFs,
  with a maximum excess of 196.9 MVA.
- The shoulder-light-load case reaches 0.80565 pu at Knickerbocker and has six
  voltage-bound violations.
- The shoulder case requires CE UG reactive output of 2474.9 MVAr against a
  999 MVAr maximum; Q-limit enforcement eliminates all remaining REF/PV buses.
- The standard PF places AC losses on the Zone J reference unit. This exceeds
  the RAV A-3 unit PMAX by 17.8 MW in the high-NYC/LI case and 68.6 MW in the
  high-Total-East case.
- The inferred solution reaches Zone B and E PMAX in the shoulder case, and
  Zone E PMAX in the low-Total-East case. Zone H remains fixed at zero
  generation because the reduced case has no Zone H source.

## Interpretation

The requested public-data path is now applied: loads, external schedules, and
inferred zonal net injections all enter the PF, while PERFORM controls the
within-zone bus allocation. This materially improves the internal-interface
match.

The result is an in-sample consistency test, not independent validation. P-32
flows participate in estimating the injections and are then used to score the
AC PF. Independent validation requires held-out hours or generation observations.
The remaining blocker is AC voltage/reactive feasibility, especially in the
shoulder-light-load condition, rather than active-power interface consistency.
