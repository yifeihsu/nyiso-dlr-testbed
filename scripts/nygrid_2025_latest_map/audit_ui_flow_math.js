/* Run the actual map's pure helpers and arrow expressions without a browser. */
'use strict';
const fs = require('fs'), path = require('path'), crypto = require('crypto'), vm = require('vm');
const root = path.resolve(__dirname, '../..'), out = path.join(root, 'output/nygrid_2025_latest_map');
const scriptPath = path.join(__dirname, 'map.js'), source = fs.readFileSync(scriptPath, 'utf8');
const annualPath = path.join(out, 'annual_data.json'), defsPath = path.join(out, 'interface_definitions.json');
const annual = JSON.parse(fs.readFileSync(annualPath, 'utf8')), defs = JSON.parse(fs.readFileSync(defsPath, 'utf8'));
const dataProofPath = path.join(out, 'independent_annual_data_review.json');
const dataProof = JSON.parse(fs.readFileSync(dataProofPath, 'utf8'));
const fixture = dataProof.browser_test_fixtures;
if (!dataProof.passed) throw Error('Independent numeric source review must pass first');
const names = ['finite', 'power', 'fmt', 'flow', 'direction', 'lineGeometry'];
const helpers = names.map(name => {
  const line = source.split(/\r?\n/).find(line => line.startsWith('function ' + name + '('));
  if (!line) throw Error('Cannot locate source helper ' + name);
  return line;
}).join('\n');
const context = vm.createContext({annual, defs, h: 8507, units: 'model', scale: () => 1});
vm.runInContext(helpers, context);
const tests = [];
function check(name, pass, details) { tests.push({name, passed: Boolean(pass), details}); }
function run(code) { return vm.runInContext(code, context); }
check('actual_JS_default_model_value', run('flow(3)') === fixture.default_Moses_South_model_MW,
      {hour:8508, interface:'MOSES SOUTH', value:run('flow(3)')});
context.units = 'public';
check('actual_JS_public_scale_value', Math.abs(run('flow(3)') - fixture.default_Moses_South_public_scale_MW) < 1e-10,
      {value:run('flow(3)'), gamma:defs.gamma});
check('public_scale_preserves_negative_direction', run('direction(3)') === 'reverse' && run('direction(2)') === 'positive',
      {Moses:run('direction(3)'), TotalEast:run('direction(2)')});
context.units = 'model'; context.h = fixture.source_eligible_failed_hour - 1;
check('failed_hour_helpers_return_unavailable_not_zero', run('annual.interfaceFlowsModelMW[h].every((_,i)=>flow(i)===null&&direction(i)==="unavailable")'),
      {hour:fixture.source_eligible_failed_hour});
context.h = fixture.source_excluded_hour - 1;
check('source_excluded_helpers_return_unavailable_not_zero', run('annual.interfaceFlowsModelMW[h].every((_,i)=>flow(i)===null&&direction(i)==="unavailable")'),
      {hour:fixture.source_excluded_hour});
check('null_and_zero_have_distinct_numeric_semantics', run('!finite(null)&&!finite(undefined)&&!finite(NaN)&&finite(0)&&power(0)===0&&fmt(0)==="0"'),
      {zero:run('fmt(0)'), null:run('fmt(null)')});
const display = source.match(/e\.line\.style\.display=(enabled&&from&&to&&finite\(v\)&&v!==0\?'':'none')/);
const arrow = source.match(/e\.line\.setAttribute\('d',(lineGeometry\(v<0\?to:from,v<0\?from:to,0\))\)/);
if (!display || !arrow) throw Error('The reviewed renderer arrow expressions changed');
Object.assign(context, {enabled:true, from:[1,2], to:[3,4], v:5});
const positive = run(arrow[1]); context.v = -5; const negative = run(arrow[1]);
check('actual_JS_negative_arrow_swaps_endpoints', positive.startsWith('M1,2 ') && positive.endsWith(' 3,4')
      && negative.startsWith('M3,4 ') && negative.endsWith(' 1,2'), {positive, negative});
const visibility = {};
for (const [label,value] of [['positive',5],['negative',-5],['zero',0],['null',null]]) {
  context.v = value; visibility[label] = run(display[1]);
}
check('actual_JS_zero_and_null_do_not_draw_arrows', visibility.positive === '' && visibility.negative === ''
      && visibility.zero === 'none' && visibility.null === 'none', visibility);
check('UTC_hour_widget_is_explicit', fs.readFileSync(path.join(__dirname,'map_template.html'),'utf8').includes('<label>UTC hour'),
      'The datetime-local input is explicitly labeled UTC and indexes supplied UTC timestamps');
check('chart_breaks_at_unavailable_values', source.includes('if(!finite(v)){open=false;return;}'),
      'The actual chart loop starts a new path after each null gap');
check('zero_total_and_net_native_labels_are_explicit', source.includes('Zero total') && source.includes('Net native generation'),
      'Zero interface totals are not labeled unavailable; native generation is a net quantity');
const result = {passed:tests.every(t=>t.passed),created_utc:new Date().toISOString(),
  scope:'Execute actual map-source power/format/direction helpers and arrow expressions against independent numeric fixtures',
  test_count:tests.length, tests, real_browser_rendering_test:false, simulation_run:false,
  sources:[scriptPath,annualPath,defsPath,dataProofPath,__filename].map(file=>({path:path.relative(root,file).replaceAll('\\','/'),
      sha256:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')}))};
fs.writeFileSync(path.join(out,'independent_ui_flow_math_review.json'),JSON.stringify(result,null,2)+'\n');
process.stdout.write(JSON.stringify({passed:result.passed,tests:tests.length,failures:tests.filter(t=>!t.passed)},null,2)+'\n');
if (!result.passed) process.exitCode = 1;
