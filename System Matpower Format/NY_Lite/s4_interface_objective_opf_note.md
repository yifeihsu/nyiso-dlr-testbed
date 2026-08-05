# S4 Interface Objective Implementation Note

The current S4 calibration sweep treats NYISO P-32 interface flows as soft
post-OPF scoring targets. This is intentional for the first cost/participation
calibration pass.

MATPOWER generalized quadratic costs through `N`, `H`, and `Cw` are best suited
to linear functions of OPF variables. The NY-lite AC interface flows are sums of
branch active-power flows, and those flows are nonlinear functions of voltage
angle and magnitude in ACOPF. Therefore an exact in-OPF AC interface-flow
penalty should be implemented as a nonlinear OPF cost callback, not as a simple
linear generalized cost.

The appropriate next implementation route is:

1. Use a MATPOWER formulation userfcn.
2. Add an `om.add_nln_cost` block.
3. Compute interface active flows from `Va` and `Vm` using `makeYbus` and
   `dSbr_dV`.
4. Provide gradients, and preferably Hessians, using MATPOWER branch-flow
   derivative helpers such as `dSbr_dV` and `d2Sbr_dV2`.
5. Validate the nonlinear cost derivative numerically before using it for
   calibration.

Until that derivative path is validated, the safer workflow is:

```text
run ACOPF with candidate equivalent costs and caps
compute P-32 scaled interface residuals after solve
select candidates by balanced public-interface objective and dispatch plausibility
```

The balanced objective used in this stage is:

```text
sum_m ((F_lite_m - F_target_m) / max(500, target_limit_m))^2
```

where `target_limit_m` is the scaled aggregate P-32 interface limit. This keeps
low-flow scenarios from dominating only because their target flow is small.
