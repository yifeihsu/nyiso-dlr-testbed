# NYISO 2019 interface source audit

The released NYgrid hourly interface input is **reproduced within tolerance**. This is an independent reconstruction of input preparation from official NYISO archives, not a model validation.

- Official monthly ZIPs: 12; daily CSVs: 365; raw rows: 1,897,236.
- Channels: 18 (7 internal and 11 scheduled external).
- Hourly keys matched: 157,680; rows outside the 1e-08 numeric tolerance or missing: 0.
- Maximum absolute numeric difference: 6.36646291241e-12 in the published numeric units.
- Duplicate timestamp/interface groups: 5,094; groups containing conflicting numeric values: 2,732.
- Interpolated flow channel-hours: 36. See the imputed-hours CSV for exact dates and values.

The interpolated local hours are **2019-03-10 02:00** (spring DST) and **2019-12-12 12:00** (an actual source gap from 11:30 to 13:10). Each channel has 181 nonempty hourly bins with fewer than 12 samples and 444 with more than 12. The autumn 01:00 hour is combined, not preserved as two observations. There are no missing raw numeric values or timestamps outside their filename dates. West Central retains +9999/-9999 limits in all 8,760 hours; a normalized error using that denominator should not be presented as error relative to a verified physical rating.

The separately exported MAT data used by the model is also reproduced within tolerance. The MAT comparison tables preserve its direct comparison against the same raw reconstruction.

The reconstruction follows the pinned `Utility/writeInterflow.m`: timezone-naive hourly arithmetic means of every raw row, followed by linear interpolation of missing values. It retains the original MWH column labels and performs no energy integration. It preserves all schedule identities separately and does not sum overlapping HQ channels.

The quality and duplicate tables retain sample counts, raw-source member/line provenance, imputation flags, DST flags, gaps longer than ten local minutes, and +/-9999 limit counts. The annual 8,760 local-hour grid cannot distinguish the repeated autumn hour. Matching prepared inputs does not validate generation, electrical topology, or simulated interface flows.

Sources: [NYISO P-32 archive index](https://mis.nyiso.com/public/P-32list.htm); pinned NYgrid source and released data are hashed in the dependencies table; the upstream Git commit is recorded in `upstream_manifest.json`. Archive and daily-member hashes preserve the raw bytes. Reused historical caches were checked against their pinned manifests before copying; their original retrieval dates are not asserted.

Run `python scripts/nygrid_2019/audit_nyiso_interfaces.py --offline` to reproduce the audit from acquired archives. Omit `--offline` to acquire any missing monthly official archives.
