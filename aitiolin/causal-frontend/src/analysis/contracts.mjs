export const METHODS=[['linear_regression','Linear outcome regression'],['logistic_regression','Logistic outcome regression — risk difference'],['propensity_score_weighting','Propensity weighting'],['propensity_score_matching','Propensity matching — interval unavailable'],['descriptive_difference','Descriptive group difference — not causal']]
export function availableMethods(treatmentKind,outcomeKind){return METHODS.filter(([m])=>!(m==='logistic_regression'&&outcomeKind!=='binary')&&!(treatmentKind==='continuous'&&!['linear_regression','logistic_regression'].includes(m)))}
export function numberText(v){return v===null||v===undefined||v===''||!Number.isFinite(Number(v))?'Not available':Number(v).toFixed(4)}
export function requestSpec(form,{treatment,outcome,seed,reviewed,independent}){
 return {name:form.name,treatment,outcome,treatment_kind:form.treatment_kind,outcome_kind:form.outcome_kind,control_value:form.control_value,treatment_value:form.treatment_value,
 ...(form.outcome_kind==='binary'?{event_value:form.event_value}:{}),estimand:form.estimand,method:form.method,units:form.units,
 covariates:form.covariates.filter(c=>c.enabled).map(c=>({name:c.name,kind:c.kind,...(c.kind==='nominal'?{reference:c.reference}:{})})),
 interactions:form.covariates.filter(c=>c.enabled&&c.interaction).map(c=>c.name),missing:form.missing,uncertainty:form.uncertainty,confidence:Number(form.confidence),bootstrap_reps:Number(form.bootstrap_reps),seed:seed===''||seed==null?42:Number(seed),reviewed:Boolean(reviewed),independent_units:Boolean(independent)}
}
export function histogramRows(h){if(!h?.bin_edges||h.bin_edges.length!==11)return [];return Array.from({length:10},(_,i)=>({label:`${h.bin_edges[i].toFixed(1)}–${h.bin_edges[i+1].toFixed(1)}`,treated:h.treated[i],control:h.control[i]}))}
