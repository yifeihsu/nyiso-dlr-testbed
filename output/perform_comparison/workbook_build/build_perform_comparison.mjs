import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const buildDir = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(buildDir, "..");
const workbookPath = path.join(outputDir, "PERFORM_NPCC_NY_calibration_comparison.xlsx");

const colors = {
  navy: "#17324D",
  blue: "#2E6F95",
  teal: "#2A7F78",
  lightBlue: "#E8F1F7",
  lightTeal: "#E5F2F0",
  amber: "#D99B2B",
  lightAmber: "#FFF4D6",
  red: "#B94A48",
  lightRed: "#FBE9E7",
  green: "#2F7D4A",
  lightGreen: "#E8F5EC",
  gray: "#667085",
  lightGray: "#F2F4F7",
  border: "#CFD8E3",
  white: "#FFFFFF",
};

async function csvMatrix(fileName) {
  const text = await fs.readFile(path.join(outputDir, fileName), "utf8");
  const temp = await Workbook.fromCSV(text, { sheetName: "Data" });
  const values = temp.worksheets.getItem("Data").getUsedRange().values;
  return values.map((row) => row.map((v) => {
    if (typeof v === "number" && !Number.isFinite(v)) return null;
    if (v === "NaN") return null;
    return v;
  }));
}

const [pfAudit, zonal, fuel, crossZone, zonePairs, corridorBranches,
  corridorEq, loadCompare, genCompare, retarget] = await Promise.all([
  csvMatrix("perform_pf_summary.csv"),
  csvMatrix("perform_zonal_snapshot.csv"),
  csvMatrix("perform_zonal_generation_by_fuel.csv"),
  csvMatrix("perform_cross_zone_branches.csv"),
  csvMatrix("perform_zone_pair_summary.csv"),
  csvMatrix("perform_candidate_corridor_branches.csv"),
  csvMatrix("perform_candidate_corridor_equivalents.csv"),
  csvMatrix("perform_vs_nyiso_load.csv"),
  csvMatrix("perform_vs_goldbook_generation.csv"),
  csvMatrix("perform_retarget_pf_scenarios.csv"),
]);

const wb = Workbook.create();

function setTitle(sheet, title, subtitle, lastCol) {
  sheet.showGridLines = false;
  sheet.mergeCells(`A1:${lastCol}1`);
  sheet.getRange("A1").values = [[title]];
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 18 },
    verticalAlignment: "center",
  };
  sheet.getRange("A1").format.rowHeight = 30;
  sheet.mergeCells(`A2:${lastCol}2`);
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange(`A2:${lastCol}2`).format = {
    fill: colors.lightBlue,
    font: { color: colors.gray, italic: true, size: 10 },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange("A2").format.rowHeight = 32;
}

function styleHeader(range) {
  range.format = {
    fill: colors.blue,
    font: { bold: true, color: colors.white, size: 10 },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "inside", style: "thin", color: colors.border },
  };
  range.format.rowHeight = 34;
}

function writeDataSheet(name, title, subtitle, matrix, options = {}) {
  const sheet = wb.worksheets.add(name);
  const cols = matrix[0].length;
  const lastCol = colLetter(Math.max(cols, options.visualLastCol || cols));
  setTitle(sheet, title, subtitle, lastCol);
  const target = sheet.getRangeByIndexes(2, 0, matrix.length, cols);
  target.values = matrix;
  styleHeader(sheet.getRangeByIndexes(2, 0, 1, cols));
  if (matrix.length > 1) {
    sheet.getRangeByIndexes(3, 0, matrix.length - 1, cols).format = {
      font: { size: 9, color: "#263238" },
      borders: { insideHorizontal: { style: "thin", color: "#E6EAF0" } },
      verticalAlignment: "center",
    };
  }
  sheet.freezePanes.freezeRows(3);
  applyNumberFormats(sheet, matrix);
  applyWidths(sheet, matrix[0], options.widthOverrides || {});
  return sheet;
}

function colLetter(n) {
  let out = "";
  while (n > 0) {
    n -= 1;
    out = String.fromCharCode(65 + (n % 26)) + out;
    n = Math.floor(n / 26);
  }
  return out;
}

function applyNumberFormats(sheet, headers) {
  const rowCount = sheet.getUsedRange().values.length;
  headers.forEach((header, i) => {
    const h = String(header).toLowerCase();
    const col = colLetter(i + 1);
    const range = sheet.getRange(`${col}4:${col}${rowCount}`);
    if (h.includes("share") && !h.includes("mva")) range.format.numberFormat = "0.0%";
    else if (h.includes("ratio") && !h.includes("tap")) range.format.numberFormat = "0.00x";
    else if (h.includes("voltage") || h.endsWith("_pu")) range.format.numberFormat = "0.0000";
    else if (h.includes("pct")) range.format.numberFormat = "0.0";
    else if (h.includes("mw") || h.includes("mvar") || h.includes("mva")) range.format.numberFormat = "#,##0.0";
    else if (h.includes("count") || h.includes("index")) range.format.numberFormat = "0";
    else if (h === "r_pu" || h === "x_pu" || h === "b_pu" || h.includes("eq_pu")) range.format.numberFormat = "0.00000";
  });
}

function applyWidths(sheet, headers, overrides = {}) {
  headers.forEach((header, i) => {
    const h = String(header);
    const col = colLetter(i + 1);
    let width = 14;
    if (/scenario|case_name|corridor|generator_types/i.test(h)) width = 28;
    else if (/timestamp/i.test(h)) width = 18;
    else if (/name|status|source|note/i.test(h)) width = 22;
    else if (/zone$|zone_/i.test(h)) width = 11;
    if (overrides[h] != null) width = overrides[h];
    sheet.getRange(`${col}:${col}`).format.columnWidth = width;
  });
}

function findRow(matrix, predicate) {
  const headers = matrix[0];
  const rows = matrix.slice(1).map((r) => Object.fromEntries(headers.map((h, i) => [h, r[i]])));
  return rows.find(predicate);
}

function rowsAsObjects(matrix) {
  const headers = matrix[0];
  return matrix.slice(1).map((r) => Object.fromEntries(headers.map((h, i) => [h, r[i]])));
}

function isTrue(value) {
  return value === true || Number(value) === 1 || String(value).toLowerCase() === "true";
}

const pfRow = rowsAsObjects(pfAudit)[0];
const summerRows = rowsAsObjects(loadCompare).filter((r) => r.scenario_id === "S1_2025_SUMMER_PEAK_PUBLIC");
const summerTotal = summerRows.reduce((a, r) => a + Number(r.nyiso_actual_load_mw || 0), 0);
const summerTv = 0.5 * summerRows.reduce((a, r) => a + Math.abs(Number(r.share_difference || 0)), 0);
const genRows = rowsAsObjects(genCompare);
const goldTotal = genRows.reduce((a, r) => a + Number(r.goldbook_2025_summer_capability_mw || 0), 0);
const nativeOnlinePmax = genRows.reduce((a, r) => a + Number(r.perform_native_online_pmax_mw || 0), 0);
const nativeAllPmax = genRows.reduce((a, r) => a + Number(r.perform_native_all_pmax_mw || 0), 0);
const summerPf = findRow(retarget, (r) => r.scenario_id === "S1_2025_SUMMER_PEAK_PUBLIC");
const shoulderPf = findRow(retarget, (r) => r.scenario_id === "S3_2025_SHOULDER_LIGHT_LOAD_PUBLIC");

const summary = wb.worksheets.add("Summary");
setTitle(summary, "PERFORM Reference Assessment for NPCC-NY Calibration",
  "2019 PERFORM on-peak topology and dispatch compared with 2025 NYISO P-58C loads and Gold Book zonal capability.", "N");
summary.showGridLines = false;
summary.getRange("A4:B4").values = [["Assessment", "Result"]];
styleHeader(summary.getRange("A4:B4"));
const assessmentRows = [
  ["Use PERFORM generator locations as zonal/bus allocation priors", "YES - strong reference"],
  ["Copy exact physical branch parameters where endpoints match", "YES - after base/topology checks"],
  ["Copy parameters for aggregate NY-lite equivalents directly", "NO - use reduction/PTDF calibration"],
  ["Use the embedded 2019 dispatch as a 2025 operating point", "NO - retarget and redispatch"],
  ["Use PERFORM as a detailed validation network", "YES - with 2025 load, interchange, and commitment updates"],
];
summary.getRange("A5:B9").values = assessmentRows;
summary.getRange("A5:A9").format.font = { bold: true, color: colors.navy };
summary.getRange("A5:B9").format.wrapText = true;
summary.getRange("A5:B9").format.rowHeight = 34;
summary.getRange("A4:B9").format.borders = { preset: "inside", style: "thin", color: colors.border };

summary.getRange("D4:E4").values = [["Native PERFORM PF", "Value"]];
styleHeader(summary.getRange("D4:E4"));
summary.getRange("D5:E11").values = [
  ["PF converged", isTrue(pfRow.pf_success) ? "Yes" : "No"],
  ["Load (MW)", Number(pfRow.embedded_load_mw)],
  ["Losses (MW)", Number(pfRow.pf_losses_mw)],
  ["Minimum voltage (pu)", Number(pfRow.pf_min_voltage_pu)],
  ["Maximum voltage (pu)", Number(pfRow.pf_max_voltage_pu)],
  ["Reference generator", `${pfRow.reference_bus_name}: ${Number(pfRow.reference_gen_pg_mw).toFixed(1)} MW / ${Number(pfRow.reference_gen_pmax_mw).toFixed(1)} MW PMAX`],
  ["Q limits enforced", isTrue(pfRow.pf_q_limits_enforced) ? "Yes" : "No"],
];

summary.getRange("G4:H4").values = [["2025 Comparison", "Value"]];
styleHeader(summary.getRange("G4:H4"));
summary.getRange("G5:H11").values = [
  ["2025 summer peak load (MW)", summerTotal],
  ["PERFORM vs summer total", Number(pfRow.embedded_load_mw) / summerTotal - 1],
  ["Summer zonal-share distance", summerTv],
  ["PERFORM native online PMAX (MW)", nativeOnlinePmax],
  ["PERFORM raw native PMAX inventory (MW)", nativeAllPmax],
  ["Gold Book 2025 capability (MW)", goldTotal],
  ["Raw inventory vs Gold Book", nativeAllPmax / goldTotal - 1],
];

summary.getRange("J4:K4").values = [["Retargeted PF", "Result"]];
styleHeader(summary.getRange("J4:K4"));
summary.getRange("J5:K11").values = [
  ["Summer PF success", isTrue(summerPf.pf_success) ? "Yes" : "No"],
  ["Summer minimum voltage (pu)", Number(summerPf.min_voltage_pu)],
  ["Summer branch overloads", Number(summerPf.branch_overload_count)],
  ["Summer max overload (MVA)", Number(summerPf.max_branch_overload_mva)],
  ["Shoulder dispatch allocatable", isTrue(shoulderPf.dispatch_allocatable) ? "Yes" : "No"],
  ["Shoulder status", shoulderPf.status],
  ["Interpretation", "High-load patterns require voltage/thermal correction; light load requires recommitment."],
];

summary.getRange("A13:K13").merge();
summary.getRange("A13").values = [["Calibration guidance"]];
summary.getRange("A13:K13").format = { fill: colors.teal, font: { bold: true, color: colors.white, size: 12 } };
summary.getRange("A14:K19").merge(true);
summary.getRange("A14:K19").values = [
  ["1. Normalize PERFORM zonal PG or PMAX into generation shift keys; do not copy raw 2019 PG as a 2025 dispatch."],
  ["2. Preserve PERFORM bus-level plant locations and fuel mix where a reliable NPCC proxy mapping exists."],
  ["3. Copy R/X/B/rating only for exact physical analogs such as Gilboa-Leeds; aggregate corridors require network reduction."],
  ["4. For Pleasant Valley-Wood Street and Wood Street-Millwood, use the parallel equivalents as priors but reintroduce B cautiously because NY-lite has an overvoltage history."],
  ["5. Validate against held-out P-32 interfaces after applying matched P-58C loads, external interchange, and generation commitment."],
  ["6. Treat the MARCY reference generator violation as a balancing artifact; replace it with distributed slack before dispatch validation."],
];
summary.getRange("A14:K19").format = { wrapText: true, verticalAlignment: "center", font: { size: 10, color: "#263238" } };
summary.getRange("A14:K19").format.rowHeight = 28;

summary.getRange("A:A").format.columnWidth = 40;
summary.getRange("B:B").format.columnWidth = 34;
summary.getRange("D:D").format.columnWidth = 24;
summary.getRange("E:E").format.columnWidth = 24;
summary.getRange("G:G").format.columnWidth = 28;
summary.getRange("H:H").format.columnWidth = 16;
summary.getRange("J:J").format.columnWidth = 27;
summary.getRange("K:K").format.columnWidth = 34;
summary.getRange("E6:E7").format.numberFormat = "#,##0.0";
summary.getRange("E8:E9").format.numberFormat = "0.0000";
summary.getRange("H5:H5").format.numberFormat = "#,##0.0";
summary.getRange("H6:H7").format.numberFormat = "0.0%";
summary.getRange("H8:H10").format.numberFormat = "#,##0.0";
summary.getRange("H11:H11").format.numberFormat = "0.0%";
summary.getRange("K6:K6").format.numberFormat = "0.0000";
summary.getRange("K8:K8").format.numberFormat = "#,##0.0";
summary.freezePanes.freezeRows(2);

const loadSheet = writeDataSheet("Load Comparison", "PERFORM vs NYISO Actual Zonal Load",
  "PERFORM is a 2019 on-peak snapshot. NYISO columns are P-58C actual loads for six 2025 public scenarios; share comparison is independent of system scaling.",
  loadCompare, { visualLastCol: 21 });
loadSheet.getRange("M22:O33").values = [["Zone", "PERFORM share", "NYISO 2025 summer share"], ...summerRows.map((r) => [r.zone, Number(r.perform_load_share), Number(r.nyiso_actual_load_share)])];
styleHeader(loadSheet.getRange("M22:O22"));
loadSheet.getRange("N23:O33").format.numberFormat = "0.0%";
const loadChart = loadSheet.charts.add("bar", loadSheet.getRange("M22:O33"));
loadChart.setPosition("M3", "U19");
loadChart.title = "Zonal load shares: PERFORM vs 2025 summer peak";
loadChart.titleTextStyle.fontSize = 12;
loadChart.hasLegend = true;
loadChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
loadChart.yAxis = { numberFormatCode: "0%", min: 0, max: 0.4 };

const genSheet = writeDataSheet("Generation Comparison", "PERFORM Generation vs 2025 Gold Book",
  "PERFORM dispatch is an operating snapshot; online PMAX is committed capability; all-unit PMAX is a raw inventory upper bound. Gold Book values are summer capability, not hourly dispatch.",
  genCompare, { visualLastCol: 22 });
genSheet.getRange("N22:Q33").values = [["Zone", "PERFORM online PMAX", "PERFORM all PMAX", "Gold Book capability"], ...genRows.map((r) => [r.zone, Number(r.perform_native_online_pmax_mw), Number(r.perform_native_all_pmax_mw), Number(r.goldbook_2025_summer_capability_mw)])];
styleHeader(genSheet.getRange("N22:Q22"));
genSheet.getRange("O23:Q33").format.numberFormat = "#,##0";
const genChart = genSheet.charts.add("bar", genSheet.getRange("N22:Q33"));
genChart.setPosition("N3", "V19");
genChart.title = "Native capability by zone (MW)";
genChart.titleTextStyle.fontSize = 12;
genChart.hasLegend = true;
genChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
genChart.yAxis = { numberFormatCode: "#,##0" };

const retargetSheet = writeDataSheet("Retarget PF", "PERFORM Retargeted to 2025 P-58C Load Patterns",
  "Loads are applied at full NYISO scale. Embedded online native generators are projected within PMIN/PMAX; import proxies are held fixed; Q limits are enforced. This is a physics screen, not a 2025 dispatch reconstruction.",
  retarget);
const rtRows = rowsAsObjects(retarget);
rtRows.forEach((r, i) => {
  const row = 4 + i;
  const ok = isTrue(r.pf_success);
  retargetSheet.getRange(`J${row}:K${row}`).format.fill = ok ? colors.lightGreen : colors.lightRed;
  if (Number(r.min_voltage_pu) < 0.9) retargetSheet.getRange(`L${row}`).format = { fill: colors.lightRed, font: { bold: true, color: colors.red } };
  if (Number(r.branch_overload_count) > 0) retargetSheet.getRange(`Q${row}:R${row}`).format = { fill: colors.lightAmber, font: { bold: true, color: "#8A5A00" } };
});

const currentTieRows = [
  ["GILBOA_LEEDS", "Total East physical proxy", 0.00131, 0.01997, 0.51614, 1216],
  ["PLEASANT_VALLEY_WOOD_STREET", "Lower Hudson delivery", 0.00150, 0.02500, 0, 5000],
  ["WOOD_STREET_MILLWOOD", "UPNY-ConEd delivery", 0.00120, 0.02000, 0, 5000],
  ["MILLWOOD_CE_UG_DELIVERY", "Millwood/Dunwoodie equivalent", 0.00090, 0.01500, 0, 5000],
  ["BUCHANAN_CE_UG_DELIVERY", "Alternate H-I equivalent", 0.00120, 0.02000, 0, 5000],
  ["CE_UG_GOETHALS_DELIVERY", "NYC proxy mesh", 0.00072, 0.01200, 0, 5000],
  ["CE_UG_RAV_A3_DELIVERY", "NYC proxy mesh", 0.00060, 0.01000, 0, 5000],
  ["CE_UG_AK3_DELIVERY", "NYC proxy mesh", 0.00060, 0.01000, 0, 5000],
  ["CE_UG_EAST_GARDEN_CITY", "ConEd-LIPA delivery", 0.00120, 0.02000, 0, 5000],
  ["EAST_GARDEN_CITY_NORTHPORT", "Long Island delivery", 0.00120, 0.02000, 0, 5000],
  ["GOETHALS_NORTHPORT_DELIVERY", "J-K support equivalent", 0.00180, 0.03000, 0, 5000],
  ["LEEDS_KNICKERBOCKER", "Segment B equivalent", 0.00210, 0.03500, 0, 5000],
  ["KNICKERBOCKER_PLEASANT_VLY", "Segment B equivalent", 0.00150, 0.02500, 0, 5000],
];
const eqByName = Object.fromEntries(rowsAsObjects(corridorEq).map((r) => [r.corridor_name, r]));
const tieHeaders = ["corridor_name", "ny_lite_role", "current_r_pu", "current_x_pu", "current_b_pu", "current_rate_a_mva", "perform_direct_match", "perform_circuit_count", "perform_r_eq_pu", "perform_x_eq_pu", "perform_b_sum_pu", "perform_rate_a_sum_mva", "current_x_over_perform_x", "transfer_guidance"];
const tieRows = currentTieRows.map((r) => {
  const eq = eqByName[r[0]];
  const direct = Boolean(eq && isTrue(eq.direct_match));
  let guidance = "No direct branch match: derive an equivalent with Kron reduction/PTDF matching.";
  if (r[0] === "GILBOA_LEEDS" && direct) guidance = "Exact physical analog: current R/X/B and ratings already match PERFORM.";
  else if (direct) guidance = "Direct parallel corridor: use PERFORM equivalent as a prior; validate charging B and aggregate rating in NY-lite.";
  return [r[0], r[1], r[2], r[3], r[4], r[5], direct, direct ? Number(eq.circuit_count) : 0,
    direct ? Number(eq.parallel_r_eq_pu) : null, direct ? Number(eq.parallel_x_eq_pu) : null,
    direct ? Number(eq.sum_b_pu) : null, direct ? Number(eq.sum_rate_a_mva) : null,
    direct ? r[3] / Number(eq.parallel_x_eq_pu) : null, guidance];
});
const tieSheet = writeDataSheet("Tie Calibration", "NY-lite Tie Parameters vs PERFORM",
  "Direct matches can anchor physical parameters. Rows without direct matches are reduced equivalents and must be calibrated from PERFORM transfer behavior rather than copied from an unrelated circuit.",
  [tieHeaders, ...tieRows]);
tieSheet.getRange("C4:E16").format.numberFormat = "0.00000";
tieSheet.getRange("F4:F16").format.numberFormat = "#,##0";
tieSheet.getRange("I4:K16").format.numberFormat = "0.00000";
tieSheet.getRange("L4:L16").format.numberFormat = "#,##0";
tieSheet.getRange("M4:M16").format.numberFormat = "0.00x";
tieSheet.getRange("N:N").format.columnWidth = 55;
tieSheet.getRange("N4:N16").format.wrapText = true;

writeDataSheet("Corridor Branches", "Direct PERFORM Corridor Matches",
  "Individual branch rows used to calculate the parallel-circuit equivalents in Tie Calibration.", corridorBranches);
writeDataSheet("Zone Pair Summary", "PERFORM Cross-Zone Branch Summary",
  "Zone-pair totals are diagnostic only. NYISO P-32 interfaces are specific monitored cutsets and must not be replaced by simple zone-pair RATE_A sums.", zonePairs);
writeDataSheet("Zonal Snapshot", "PERFORM 2019 On-Peak Zonal Snapshot",
  "Native generation excludes import and reference proxy records. Import dispatch can be negative where the modeled interface exports from New York.", zonal);
writeDataSheet("Fuel by Zone", "PERFORM Generation by Zone and Fuel",
  "Use these rows as plant-location and fuel-mix priors; unit commitment and availability remain scenario-specific.", fuel);
writeDataSheet("Cross-Zone Branches", "PERFORM Cross-Zone Branch Inventory",
  "Solved AC flows use the Q-limit-enforced PF. Parameters are on the PERFORM 100 MVA base.", crossZone);
writeDataSheet("PF Audit", "Native PERFORM Power-Flow Audit",
  "The case converges with Q-limit enforcement and normal voltage, but the dummy MARCY reference generator exceeds its 1 MW PMAX while balancing losses.", pfAudit);

const sources = wb.worksheets.add("Sources & Notes");
setTitle(sources, "Sources, Scope, and Interpretation", "All comparisons are reproducible from the listed local files.", "H");
sources.getRange("A4:D4").values = [["Source", "Role", "Location / URL", "Interpretation"]];
styleHeader(sources.getRange("A4:D4"));
sources.getRange("A5:D11").values = [
  ["PERFORM v23 MATPOWER case", "Detailed network and solved 2019 on-peak snapshot", "PERFORM/On Peak 2019 v23_Perform_NY/On Peak 2019 v23/nyiso_On_Peak_v23_shunts_as_z_load.m", "1,576 buses, 615 generators, 2,371 branches; 100 MVA base."],
  ["PERFORM bus-zone map", "A-K bus mapping", "PERFORM/Auxilliary_Perform_NY/internal_NYISO_MOD2MAP.xlsx", "Used for all zonal aggregation."],
  ["NYISO P-58C", "Actual zonal load", "https://mis.nyiso.com/public/P-58Clist.htm", "Six 2025 timestamps already cached in NY_Lite."],
  ["NYISO 2025 Gold Book", "Existing summer capability by zone", "https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf", "Capability is not hourly generation dispatch."],
  ["Local public scenario table", "Selected P-58C/P-32 timestamps", "System Matpower Format/NY_Lite/nyiso_public_scenarios.csv", "Defines the six comparison scenarios."],
  ["Local capability target table", "Gold Book A-K values", "System Matpower Format/NY_Lite/nyiso_generator_capability_targets.csv", "User-provided 2025 Gold Book extraction."],
  ["Reproducible extractor", "MATLAB aggregation and PF audit", "System Matpower Format/NY_Lite/analyze_perform_reference.m", "Regenerates every CSV used by this workbook."],
];
sources.getRange("A5:D11").format = { wrapText: true, verticalAlignment: "top", borders: { insideHorizontal: { style: "thin", color: colors.border } } };
sources.getRange("A:A").format.columnWidth = 26;
sources.getRange("B:B").format.columnWidth = 28;
sources.getRange("C:C").format.columnWidth = 70;
sources.getRange("D:D").format.columnWidth = 48;
sources.getRange("A5:D11").format.rowHeight = 42;
sources.getRange("A13:D13").merge();
sources.getRange("A13").values = [["Critical limitations"]];
sources.getRange("A13:D13").format = { fill: colors.amber, font: { bold: true, color: "#4F3A00" } };
sources.getRange("A14:D18").merge(true);
sources.getRange("A14:D18").values = [
  ["The PERFORM case is labeled 2019 on-peak; the package does not identify the exact public operating timestamp used for its snapshot."],
  ["Gold Book capability cannot validate PERFORM hourly PG. A true dispatch comparison requires timestamp-matched zonal generation or plant-level output."],
  ["The retarget PF keeps the 2019 import schedule and online commitment. Its voltage/overload failures diagnose incompatibility with those assumptions, not an inability of the real 2025 NYISO system to serve the load."],
  ["Line charging from detailed PERFORM circuits should not be copied wholesale into NY-lite because the reduced model previously exhibited systemic overvoltage."],
  ["P-32 interface definitions are monitored branch sets. Zone-pair flow sums and individual RATE_A values are not substitutes for official interface limits."],
];
sources.getRange("A14:D18").format = { wrapText: true, verticalAlignment: "center", font: { size: 10 } };
sources.getRange("A14:D18").format.rowHeight = 34;

for (const sheet of wb.worksheets.items) {
  const used = sheet.getUsedRange();
  if (used) used.format.verticalAlignment = "center";
}

const inspect = await wb.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
console.log(inspect.ndjson);
const summaryCheck = await wb.inspect({ kind: "table", range: "Summary!A1:K19", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 12 });
console.log(summaryCheck.ndjson);
const errorScan = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errorScan.ndjson);

const previewDir = path.join(outputDir, "previews");
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of wb.worksheets.items.map((sheet) => sheet.name)) {
  const dense = ["Fuel by Zone", "Cross-Zone Branches", "Load Comparison"].includes(sheetName);
  const blob = await wb.render({ sheetName, autoCrop: "all", scale: dense ? 0.8 : 1.25, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName.replace(/[^A-Za-z0-9]+/g, "_")}.png`), new Uint8Array(await blob.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(workbookPath);
console.log(`WORKBOOK=${workbookPath}`);
