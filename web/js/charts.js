export const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const numbers = new Intl.NumberFormat(undefined, {maximumFractionDigits:0});
export const count = value => typeof value === 'number' ? numbers.format(value) : 'Unavailable';
export function valueLabel(value, key='') {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Unavailable';
  if (key.endsWith('_ms')) return `${new Intl.NumberFormat(undefined,{minimumFractionDigits:3,maximumFractionDigits:3}).format(value/1000)} s`;
  return count(value);
}
const metricNames={wall_ms:'End-to-end time',agent_ms:'Client elapsed time',initialization_ms:'Initialization time',preparation_ms:'Preparation time',verification_ms:'Verification time',checkpoint_ms:'Checkpoint time',delegation_ms:'Orchestration time',automated_edit_observed_sum_ms:'Observed editing duration sum',human_review_ms:'Human review time',human_edit_ms:'Human editing time',manual_edit_ms:'Manual editing time'};
export const human = value => metricNames[value] || String(value || 'Unknown').replaceAll('_',' ').replace(/\b\w/g, character => character.toUpperCase());
export function status(text, state='unknown') { return `<span class="status ${escape(state)}">${escape(text)}</span>`; }
export function sourceTag(kind) { return `<span class="source-tag ${escape(kind)}">${escape(({native:'Reported native observation',control:'Model-free control',demo:'Synthetic demo',session:'Imported observation'})[kind] || kind)}</span>`; }
export function empty(title, message, action='') { return `<div class="empty-state"><h2>${escape(title)}</h2><p>${escape(message)}</p>${action}</div>`; }
export function section(title, content, extra='', note='') { return `<section class="section"><div class="section-header"><div><h2>${escape(title)}</h2>${note?`<p>${escape(note)}</p>`:''}</div>${extra}</div>${content}</section>`; }
export function metric(name, value, note, provenance='') { return `<div class="metric"><div class="value ${value==='Unavailable'?'unavailable':''}">${escape(value)}</div><div class="name">${escape(name)}</div><div class="coverage">${escape(note)}${provenance?`<br>${escape(provenance)}`:''}</div></div>`; }
export function pairPlots(comparison) {
  const plots=[['input_tokens','Input tokens','Cached input is a subset, never added twice.'],['wall_ms','End-to-end time','Full recorded wall time, not sum of tool durations.']];
  return `<div class="comparison-plots">${plots.map(([key,title,note])=>{
    const m=comparison.metrics[key];const maximum=Math.max(m.baseline??0,m.treatment??0,1);const known=m.baseline!==null&&m.treatment!==null;
    return `<div class="measure-plot"><h3 class="plot-title">${escape(title)}</h3><p class="plot-caption">${escape(note)}</p>${[['A',m.baseline],['B',m.treatment]].map(([arm,value],i)=>`<div class="bar-row"><span>${i?escape(comparison.treatment.arm||'T'):arm}</span><div class="bar-track" role="img" aria-label="${i?'Treatment':'Baseline'}: ${escape(valueLabel(value,key))}"><svg class="bar-svg" viewBox="0 0 100 19" preserveAspectRatio="none" aria-hidden="true"><rect class="bar-fill ${i?'treatment':''} ${i&&known&&m.delta>0?'regression':''}" width="${value===null?0:value/maximum*100}" height="19"/></svg></div><span class="bar-value">${escape(valueLabel(value,key))}</span></div>`).join('')}<div class="delta ${known&&m.delta>0?'regression':known&&m.delta<0?'improved':''}">${known?`${m.percent===null?'Percentage unavailable':`${m.percent>0?'+':'−'}${Math.abs(m.percent).toFixed(1)}%`} ${key==='wall_ms'?(m.delta>0?'longer':m.delta<0?'shorter':'unchanged'):(m.delta>0?'more':m.delta<0?'fewer':'unchanged')}`:'Difference unavailable'}<small>${known?`${m.delta>0?'+':m.delta<0?'−':''}${valueLabel(Math.abs(m.delta),key)} · treatment minus baseline`:'Both measurements are required.'}</small></div></div>`;
  }).join('')}</div>`;
}
export function tokenTrend(buckets) {
  const maximum=Math.max(...buckets.map(row=>(row.input_tokens.value??0)+(row.output_tokens.value??0)),1);
  return `<div class="trend-chart" aria-label="Token totals by calendar bucket">${buckets.slice(-90).map((row,index)=>{
    const cached=row.cached_input_tokens.value;const uncached=row.uncached_input_tokens.value;const input=row.input_tokens.value;const output=row.output_tokens.value;
    const segments=cached!==null&&uncached!==null?[['',uncached],['cached',cached],['output',output]]:[['',input],['output',output]];
    return `<div class="trend-column"><button class="trend-stack" data-bucket="${escape(row.key)}" aria-label="${escape(row.key)}: ${escape(count(input))} input, ${escape(count(output))} output tokens"><svg class="trend-svg" viewBox="0 0 30 174" preserveAspectRatio="none" aria-hidden="true">${segments.filter(([,n])=>n!==null).map(([cls,n],i,items)=>`<rect class="segment ${cls}" x="0" y="${174-items.slice(0,i+1).reduce((sum,[,v])=>sum+(v/maximum*174),0)}" width="30" height="${n/maximum*174}"/>`).join('')}</svg></button><span class="trend-label">${index%Math.max(1,Math.ceil(buckets.length/12))===0?escape(row.key.slice(5)):''}</span></div>`;
  }).join('')}</div><div class="legend"><span><i class="swatch"></i>Uncached / cache-unspecified input</span><span><i class="swatch cached"></i>Cached input</span><span><i class="swatch output"></i>Output</span></div>`;
}
export function toolGraph(tools,selected='') {
  const bounded=tools.slice(0,12);const height=Math.max(300,bounded.length*48+48);const center=height/2;
  return `<svg class="tool-graph" viewBox="0 0 760 ${height}" role="group" aria-label="Observed session-to-tool category associations, not causal dependencies"><title>Observed call categories. Select a node or use the table.</title>${bounded.map((tool,index)=>`<line x1="150" y1="${center}" x2="490" y2="${index*48+45}"/>`).join('')}<circle cx="150" cy="${center}" r="45"/><text x="150" y="${center-4}" text-anchor="middle">Recorded</text><text x="150" y="${center+14}" text-anchor="middle">sessions</text>${bounded.map((tool,index)=>`<g class="node" tabindex="0" role="button" data-tool="${escape(tool.key)}" aria-label="${escape(human(tool.key))}, ${tool.calls} observed calls" aria-pressed="${selected===tool.key}"><circle cx="490" cy="${index*48+45}" r="${Math.min(20,10+Math.sqrt(tool.calls))}"/><text x="${520}" y="${index*48+49}">${escape(human(tool.key))} · ${count(tool.calls)}</text></g>`).join('')}</svg>${tools.length>12?'<p class="note">Showing the 12 most frequent categories. The complete table remains available.</p>':''}`;
}

export function costTrend(groups,currency) {
  const shown=groups.slice(-90);
  const values=shown.map(group=>group.cost.currencies.find(row=>row.currency===currency)?.value??null);
  const maximum=Math.max(...values.filter(value=>value!==null),0.000001);
  return `<h3 class="plot-title">Legacy configured cost scenario · ${escape(currency)}</h3><div class="trend-chart" aria-label="${escape(currency)} legacy configured cost scenarios">${shown.map((group,index)=>{
    const value=values[index],coverage=group.cost;
    const label=`${coverage.label}: ${group.key}: ${value===null?'Unavailable':currency+' '+value.toFixed(6)}; ${group.cost.currencies.find(row=>row.currency===currency)?.covered??0}/${coverage.total} observations priced in ${currency}; ${coverage.complete?'complete':'partial'} combined recorded scenario coverage; Confidence: ${coverage.confidence}; ${coverage.assumption_basis}`;
    return `<div class="trend-column"><button class="cost-stack" data-cost-bucket="${escape(group.key)}" aria-label="${escape(label)}"><svg class="trend-svg" viewBox="0 0 30 174" preserveAspectRatio="none" aria-hidden="true"><rect class="segment cached" x="0" y="${value===null?174:174-value/maximum*174}" width="30" height="${value===null?0:value/maximum*174}"/></svg></button><span class="trend-label">${index%Math.max(1,Math.ceil(shown.length/12))===0?escape(group.key.slice(5)):''}</span></div>`;
  }).join('')}</div>`;
}
