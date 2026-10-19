# Matched NYgrid / compact 2019 experiment

Read `NYGRID_COMPACT_2019_COMPARISON.md` at the repository root for the result and scope. This package is separate from the preferred 71-bus 2025 AC/DLR model.

Prerequisites are the completed pinned `scripts/nygrid_2019` reproduction, the compact source reconstruction, MATLAB/MATPOWER (and the existing IPOPT setup for the recorded AC fallback), and Python with NumPy, pandas and SciPy. No new source targets or tools are downloaded by the comparison.

1. In MATLAB, add `scripts/nygrid_compact_2019` to the path and run `export_reference_snapshot`. It reads the isolated cached NYgrid code and exports six development-hour components without changing the release.
2. Run `python scripts/nygrid_compact_2019/export_reference.py` to create and independently verify the annual NY-only reference arrays.
3. In MATLAB run `export_compact_network` and `test_export_compact_network`. The exported 51-bus gross construction and five current-source inputs preserve unallocated/clipped-prior evidence separately. `EXPORT_NOTES.md` documents the schema.
4. Run `python scripts/nygrid_compact_2019/run_comparison.py`. The experiment solves fixed-injection DC systems before scoring targets. It exports all annual predictions/rankings, network/input and policy comparisons, the regional balance ledger, and six selected/development numerical cases.
5. Run `python -m unittest discover -s scripts/nygrid_compact_2019 -p test_dc_model.py -v` for the analytic and failure guards. The separate crosswalk reproduction script is `output/nygrid_compact_2019/crosswalk_build.py`.
6. In MATLAB run `run_restored_fleet_ac_checkpoint`, followed by `replay_restored_fleet_ac_checkpoint` and `test_restored_fleet_ac_checkpoint`. This validates three existing-current-source 2019 inputs on the unchanged compact51 network with a restored H-generation role. It does not qualify the Marcy DC candidates.
7. From the repository root in MATLAB, run `addpath('output/nygrid_compact_2019/verification'); replay_selected_candidates(pwd)`, then `python output/nygrid_compact_2019/verification/independent_validation.py`. The independent verifier reconstructs the annual, matrix, ablation and ranking results independently.
8. In MATLAB run `verify_ac_scoring_dc`, then run `python scripts/nygrid_compact_2019/score_ac_checkpoint.py` and `python -m unittest discover -s scripts/nygrid_compact_2019 -p test_score_ac_checkpoint.py -v` for the separate AC score increment. This uses reference42 rather than the matrix's reference74 and does not qualify Marcy's added DC parameters.
9. Run `python scripts/nygrid_compact_2019/write_report.py` after all results exist, then `python scripts/nygrid_compact_2019/finalize_package.py` to verify the prior frozen artifacts and fingerprint the new package.

The preexisting 2019 and 2025 evidence is read-only. New generated files live only under `output/nygrid_compact_2019/`; their manifests retain exact bytes. Source tables under `tmp/` remain pinned caches and can be restored with the earlier reproduction's fetch scripts.

`selected_dc_candidates.mat` contains six structs in `candidates`. Each separates native input/solved bus generation, the source slack adjustment, renewable-adjusted demand, boundary injections, branch parameters and DC coefficients. Its added Marcy rows have only DC reactance provenance; zero R/B/RATE_A entries are not verified AC or thermal parameters. A fixed-bus injection solver should use `native_solved_pg_bus_mw - net_pd_mw + boundary_p_mw`. For a pre-slack replay, use the input generation and retain the explicit bus74 balancing result.

All rankings are retrospective. Paper-role and current-role operators are explicitly separate. B-arm current generation at added9003 uses an exact compact-derived common-port injection map, not measured relocation. Power scale is fixed at gamma0.358662225381536, and percentages use absolute observed flow without a denominator floor.
