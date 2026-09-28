# Preserved initial solver experiment

The first partial-SPC experiment qualified 14 of 15 registered electrical cases. The nominal V4 night case failed: MIPS encountered poor numerical conditioning, and the default IPOPT termination left a maximum reactive power-balance mismatch of 0.0011332787 Mvar, above the unchanged audit threshold. No voltage, generator-capability or branch-rating violation was reported for that IPOPT iterate. This is a numerical failure, not a proof of physical infeasibility.

The initial campaign, all 17 attempt matrices, audit rows and original code files are retained here. `saved_code/` contains the exact source files referenced by this experiment's code manifest. The subsequent campaign tightens numerical solver tolerances in a separate fitter while preserving topology, loads, boundary injections, generation priors and capability bounds. Its results and qualification are recorded separately in `../partial_spc/`.

This archive is historical failed-attempt evidence. The current loader does not use it as a qualified operating case. To reproduce its original driver, use the archived source versions in an isolated copy of the repository; the live driver has a newer, explicitly registered numerical solver policy.
