"""Explicit comparisons in original-variable DAG space; encoded model matrices.

No Django, network, files, provider calls, hidden imputation or estimator fallbacks.
Inference assumes independent observations and the supplied causal assumptions.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import warnings
import networkx as nx
import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import norm, t as student_t
import statsmodels.api as sm
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

METHODS = {
    'linear_regression': 'Linear outcome regression (standardized contrast)',
    'logistic_regression': 'Logistic outcome regression (standardized risk difference)',
    'propensity_score_weighting': 'Normalized propensity-score weighting',
    'propensity_score_matching': 'Nearest logit-propensity matching with replacement',
    'descriptive_difference': 'Descriptive difference in means — NOT adjusted causal estimation',
}
MAX_ROWS, MAX_COLUMNS, MAX_LEVELS = 100000, 80, 40

class AnalysisError(ValueError):
    def __init__(self, message, code='invalid_comparison'):
        super().__init__(message)
        self.code = code

def key(value):
    if isinstance(value, (bool, np.bool_)):
        return 'True' if value else 'False'
    if isinstance(value, (int, float, np.integer, np.floating)):
        if not np.isfinite(value):
            raise AnalysisError('Category values must be finite.')
        return format(float(value), '.17g')
    if isinstance(value, str):
        return value
    raise AnalysisError('Category values must be strings or finite numbers.')

def clean(frame):
    return frame.copy().map(lambda v: np.nan if isinstance(v, str) and not v.strip() else v)

def inspect_columns(frame):
    result = []
    for name in frame.columns:
        values = clean(frame[[name]])[name].dropna()
        numeric = pd.to_numeric(values, errors='coerce')
        is_numeric = len(values) > 0 and numeric.notna().all() and np.isfinite(numeric).all()
        levels = sorted({key(v) for v in values})
        result.append({'name': str(name), 'suggested_kind': 'numeric' if is_numeric else 'nominal',
                       'missing': int(len(frame)-len(values)), 'unique_count': len(levels),
                       'levels': levels if len(levels) <= MAX_LEVELS else [],
                       'min': float(numeric.min()) if is_numeric else None,
                       'max': float(numeric.max()) if is_numeric else None})
    return result

def validate_spec(supplied):
    if not isinstance(supplied, dict):
        raise AnalysisError('A JSON comparison specification is required.')
    s = dict(supplied)
    allowed = {'treatment','outcome','treatment_kind','outcome_kind','control_value','treatment_value',
               'event_value','estimand','method','covariates','interactions','missing','confidence',
               'uncertainty','bootstrap_reps','seed','units','name','reviewed','independent_units'}
    if set(s)-allowed:
        raise AnalysisError('Unknown specification fields: '+', '.join(sorted(set(s)-allowed)))
    defaults = {'treatment_kind':'categorical','outcome_kind':'continuous','estimand':'ATE',
                'method':'linear_regression','covariates':[],'interactions':[], 'missing':'error',
                'confidence':.95,'uncertainty':'auto','bootstrap_reps':200,'seed':42,
                'units':'outcome units','name':'Reviewed comparison'}
    for name, value in defaults.items():
        s.setdefault(name, value)
    for name, maximum in [('treatment',100),('outcome',100),('name',160),('units',160)]:
        if not isinstance(s.get(name), str) or not 1 <= len(s[name]) <= maximum:
            raise AnalysisError(f'{name} must contain 1–{maximum} characters.')
    if s['treatment'] == s['outcome']:
        raise AnalysisError('Treatment and outcome must differ.')
    choices = {'treatment_kind':{'categorical','continuous'}, 'outcome_kind':{'binary','continuous'},
               'estimand':{'ATE','ATT','ATC'}, 'method':set(METHODS), 'missing':{'error','complete_case'},
               'uncertainty':{'auto','none'}}
    for name, options in choices.items():
        if not isinstance(s[name], str) or s[name] not in options:
            raise AnalysisError(f'Unsupported {name}.', 'unsupported_configuration')
    if s.get('reviewed') is not True or s.get('independent_units') is not True:
        raise AnalysisError('Confirm the reviewed comparison and independent observations. Clustered/panel inference is not supported in this path.', 'review_required')
    for name, lo, hi in [('seed',0,2**32-1),('bootstrap_reps',50,500)]:
        if type(s[name]) is not int or not lo <= s[name] <= hi:
            raise AnalysisError(f'{name} must be an integer from {lo} to {hi}.')
    if type(s['confidence']) not in (int,float) or not .8 <= s['confidence'] <= .99:
        raise AnalysisError('Confidence must be between 0.80 and 0.99.')
    for name in ('control_value','treatment_value'):
        if name not in s:
            raise AnalysisError('Select both control and treatment values explicitly.')
        key(s[name])
    if key(s['control_value']) == key(s['treatment_value']):
        raise AnalysisError('Control and treatment values must differ.')
    if s['outcome_kind'] == 'binary':
        if 'event_value' not in s:
            raise AnalysisError('Explicitly select the outcome event coded as 1.')
        key(s['event_value'])
    if not isinstance(s['covariates'], list) or len(s['covariates']) > 30:
        raise AnalysisError('Select at most 30 adjustment variables.')
    seen = set()
    for c in s['covariates']:
        if not isinstance(c, dict) or set(c)-{'name','kind','reference'}:
            raise AnalysisError('Covariates require name, kind and optional reference.')
        if not isinstance(c.get('name'), str) or not 1 <= len(c['name']) <= 100 or c['name'] in seen or c['name'] in {s['treatment'],s['outcome']}:
            raise AnalysisError('Covariates must be uniquely named and exclude treatment/outcome.')
        seen.add(c['name'])
        if not isinstance(c.get('kind'), str) or c['kind'] not in {'numeric','nominal'}:
            raise AnalysisError('Covariate kind must be numeric or nominal.')
        if c['kind'] == 'nominal':
            if 'reference' not in c: raise AnalysisError('Select each nominal reference category.')
            key(c['reference'])
    if not isinstance(s['interactions'], list) or any(not isinstance(n,str) for n in s['interactions']):
        raise AnalysisError('Interactions must be covariate names.')
    if len(set(s['interactions'])) != len(s['interactions']) or not set(s['interactions']).issubset(seen):
        raise AnalysisError('Interactions must be unique selected covariates.')
    if s['method'] not in {'linear_regression','logistic_regression'} and s['interactions']:
        raise AnalysisError('Treatment interactions require an outcome regression.')
    if s['method'] == 'logistic_regression' and s['outcome_kind'] != 'binary':
        raise AnalysisError('Logistic outcome regression requires a binary outcome.')
    if s['method'] == 'descriptive_difference' and (s['covariates'] or s['estimand'] != 'ATE'):
        raise AnalysisError('Descriptive differences use no adjustment and are not ATT/ATC estimates.')
    if s['treatment_kind'] == 'continuous':
        if s['estimand'] != 'ATE' or s['method'] not in {'linear_regression','logistic_regression'}:
            raise AnalysisError('Continuous treatment supports regression ATE at two fixed doses only.')
        try:
            a,b = float(s['control_value']),float(s['treatment_value'])
        except (TypeError,ValueError):
            raise AnalysisError('Continuous doses must be numeric.') from None
        if not np.isfinite([a,b]).all() or a == b:
            raise AnalysisError('Continuous doses must be finite and different.')
        s.update(control_value=a,treatment_value=b)
    return s

def identify(dag, treatment, outcome, adjustment):
    g=nx.DiGraph()
    g.add_nodes_from(n['name'] for n in dag.get('nodes',[]))
    for e in dag.get('edges',[]):
        if e.get('directed',True) is not True: raise AnalysisError('Use directed edges.')
        g.add_edge(e['source'],e['target'])
    if len(g)>250 or g.number_of_edges()>2000 or not nx.is_directed_acyclic_graph(g):
        raise AnalysisError('A bounded acyclic directed graph is required.','invalid_graph')
    if not {treatment,outcome,*adjustment}.issubset(g):
        raise AnalysisError('Every comparison/adjustment variable must be on the saved graph.','invalid_graph')
    if set(adjustment) & nx.descendants(g,treatment):
        raise AnalysisError('Do not adjust for treatment descendants in this total-effect path.','post_treatment_adjustment')
    backdoor=g.copy();backdoor.remove_edges_from(list(backdoor.out_edges(treatment)))
    ancestral={treatment,outcome,*adjustment}
    for n in list(ancestral): ancestral.update(nx.ancestors(backdoor,n))
    sub=backdoor.subgraph(ancestral);moral=sub.to_undirected()
    for n in sub:
        parents=list(sub.predecessors(n))
        for i,p in enumerate(parents):
            for q in parents[i+1:]:moral.add_edge(p,q)
    moral.remove_nodes_from(adjustment)
    if nx.has_path(moral,treatment,outcome):
        raise AnalysisError('The adjustment set leaves a backdoor path open under this graph.','not_identified')
    if not nx.has_path(g,treatment,outcome):
        raise AnalysisError('The graph implies no directed causal path. Review that hypothesis rather than fit an incompatible effect model.','no_causal_path')
    return {'strategy':'Pearl backdoor sufficient criterion','identified_under_graph':True,
            'adjustment_set':adjustment,'graph_validated_as_truth':False,
            'assumptions':['Appropriate graph and measurement timing.','No remaining unblocked common causes.',
                           'Well-defined treatment and no relevant interference.','Independent observations, overlap and suitable statistical specification.']}

@dataclass
class Prepared:
    spec: dict
    t: np.ndarray
    y: np.ndarray
    x: np.ndarray
    labels: list
    owners: list
    encoding: list
    sample: dict
    target: np.ndarray
    rows_sha256: str

def prepare(frame,s):
    if not frame.columns.is_unique or not 1<=len(frame)<=MAX_ROWS:
        raise AnalysisError('Use 1–100,000 observations with unique columns.')
    names=[s['treatment'],s['outcome'],*[c['name'] for c in s['covariates']]]
    if not set(names).issubset(frame.columns):raise AnalysisError('A selected variable is absent from the effective data.')
    f=clean(frame[names]);original=len(f);other=0
    if s['treatment_kind']=='categorical':
        k=f[s['treatment']].map(lambda v:key(v) if pd.notna(v) else None)
        keep=k.isin([key(s['control_value']),key(s['treatment_value'])])|k.isna()
        other=int((~keep).sum());f=f.loc[keep].copy()
    numeric=[c['name'] for c in s['covariates'] if c['kind']=='numeric']
    if s['treatment_kind']=='continuous':numeric.append(s['treatment'])
    if s['outcome_kind']=='continuous':numeric.append(s['outcome'])
    for n in numeric:
        values=pd.to_numeric(f[n],errors='coerce')
        if (f[n].notna() & values.isna()).any():raise AnalysisError(f"'{n}' contains nonnumeric values; review its declared type.")
        f[n]=values.replace([np.inf,-np.inf],np.nan)
    missing=int(f.isna().any(axis=1).sum())
    if missing and s['missing']=='error':
        raise AnalysisError(f'{missing} observations have missing/nonfinite selected values. Explicitly choose complete-case exclusion or review cleaning.','missing_data')
    f=f.dropna();rowhash=hashlib.sha256(json.dumps(f.index.tolist(),separators=(',',':')).encode()).hexdigest()
    f=f.reset_index(drop=True)
    if len(f)<20:raise AnalysisError('At least 20 complete observations are required.')
    if s['treatment_kind']=='categorical':
        k=f[s['treatment']].map(key)
        if set(k)!={key(s['control_value']),key(s['treatment_value'])}:raise AnalysisError('Both selected treatment groups must be present.')
        t=(k==key(s['treatment_value'])).to_numpy(float)
        if min(t.sum(),len(t)-t.sum())<5:raise AnalysisError('Each treatment group requires at least five observations.')
    else:
        t=f[s['treatment']].to_numpy(float)
        if np.ptp(t)==0 or not all(t.min()<=s[n]<=t.max() for n in ('control_value','treatment_value')):
            raise AnalysisError('Doses must be within the observed overall range. This alone does not establish conditional overlap.')
    if s['outcome_kind']=='binary':
        k=f[s['outcome']].map(key)
        if len(set(k))!=2 or key(s['event_value']) not in set(k):raise AnalysisError('The selected sample needs exactly two outcome classes, including the selected event.')
        y=(k==key(s['event_value'])).to_numpy(float)
    else:y=f[s['outcome']].to_numpy(float)
    arrays=[];labels=[];owners=[];encoding=[]
    for i,c in enumerate(s['covariates']):
        n=c['name']
        if c['kind']=='numeric':
            x=f[n].to_numpy(float)
            if np.ptp(x)==0:raise AnalysisError(f"Adjustment variable '{n}' is constant; review the specification.")
            label=f'{i}:{n}';arrays.append(x);labels.append(label);owners.append(n)
            encoding.append({'variable':n,'kind':'numeric','columns':[label]})
        else:
            k=f[n].map(key);levels=sorted(set(k));ref=key(c['reference'])
            if not 2<=len(levels)<=MAX_LEVELS or ref not in levels:raise AnalysisError(f"'{n}' requires 2–40 categories and an observed reference.")
            encoded=[]
            for level in levels:
                if level==ref:continue
                label=f'{i}:{n}={level}';arrays.append((k==level).to_numpy(float));labels.append(label);owners.append(n);encoded.append(label)
            encoding.append({'variable':n,'kind':'one_hot','reference':ref,'categories':levels,'columns':encoded})
    x=np.column_stack(arrays) if arrays else np.empty((len(f),0))
    if x.shape[1]>MAX_COLUMNS:raise AnalysisError('Too many encoded adjustment columns.')
    target=np.ones(len(f),bool)
    if s['estimand']=='ATT':target=t==1
    if s['estimand']=='ATC':target=t==0
    sample={'original':original,'analysis':len(f),'target':int(target.sum()),'excluded_other_treatment_levels':other,
            'excluded_missing':missing,'treated':int(t.sum()) if s['treatment_kind']=='categorical' else None,
            'control':int((1-t).sum()) if s['treatment_kind']=='categorical' else None}
    return Prepared(s,t,y,x,labels,owners,encoding,sample,target,rowhash)

def design(d,treatment):
    x=np.column_stack([np.ones(len(treatment)),treatment,d.x])
    idx=[i for i,n in enumerate(d.owners) if n in d.spec['interactions']]
    if idx:x=np.column_stack([x,d.x[:,idx]*treatment[:,None]])
    if x.shape[1]>MAX_COLUMNS+2:raise AnalysisError('Too many model terms after interactions.')
    return x

def propensity(t,x):
    if not x.shape[1]:return np.repeat(t.mean(),len(t))
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        try:
            scaled=StandardScaler().fit_transform(x)
            fit=LogisticRegression(C=1.0,solver='lbfgs',max_iter=2000,random_state=0).fit(scaled,t)
        except (ValueError,ConvergenceWarning) as exc:
            raise AnalysisError('Propensity model failed; review separation and covariates.','propensity_failure') from exc
    return fit.predict_proba(scaled)[:,1]

def weights(t,p,target):
    if (p<=1e-6).any() or (p>=1-1e-6).any():raise AnalysisError('Numerically extreme propensities; weighting stopped without silent clipping or trimming.','extreme_propensity')
    if target=='ATT':return t.copy(),(1-t)*p/(1-p)
    if target=='ATC':return t*(1-p)/p,1-t
    return t/p,(1-t)/(1-p)

def matches(t,p,target):
    if (p<=0).any() or (p>=1).any():raise AnalysisError('Matching cannot use propensities equal to zero or one.')
    a,b=np.flatnonzero(t==1),np.flatnonzero(t==0);l=np.log(p/(1-p))
    da,ia=NearestNeighbors(n_neighbors=1).fit(l[b,None]).kneighbors(l[a,None])
    db,ib=NearestNeighbors(n_neighbors=1).fit(l[a,None]).kneighbors(l[b,None])
    w1=np.zeros(len(t));w0=np.zeros(len(t))
    if target in {'ATE','ATT'}:w1[a]+=1;np.add.at(w0,b[ia[:,0]],1)
    if target in {'ATE','ATC'}:w0[b]+=1;np.add.at(w1,a[ib[:,0]],1)
    distances=np.r_[da[:,0],db[:,0]] if target=='ATE' else da[:,0] if target=='ATT' else db[:,0]
    return w1,w0,{'metric':'absolute logit propensity distance','replacement':True,'caliper':None,
                  'mean_distance':float(distances.mean()),'max_distance':float(distances.max())}

def ess(w):return float(w.sum()**2/(w@w)) if w@w else 0.

def diagnostics(d,p,w1=None,w0=None,method=None):
    t=d.t==1;lo=max(p[t].min(),p[~t].min());hi=min(p[t].max(),p[~t].max())
    outside=float(np.mean((p<lo)|(p>hi))) if lo<=hi else 1.
    extreme=float(np.mean((p<.01)|(p>.99)));bins=np.linspace(0,1,11)
    balance=[];alerts=[]
    for i,n in enumerate(d.labels):
        x=d.x[:,i];sd=float(np.sqrt((x[t].var(ddof=1)+x[~t].var(ddof=1))/2));diff=float(x[t].mean()-x[~t].mean())
        before=diff/sd if sd>1e-12 else 0. if abs(diff)<1e-12 else None
        after=float((np.average(x,weights=w1)-np.average(x,weights=w0))/sd) if w1 is not None and sd>1e-12 else None
        balance.append({'covariate':n,'smd_before':before,'smd_after':after,'denominator':'unweighted pooled within-group SD'})
    if outside>.1:alerts.append('More than 10% of observations lie outside the empirical common propensity range.')
    if extreme:alerts.append('Propensities below 0.01 or above 0.99 are present.')
    if any(v['smd_before'] is None or abs(v['smd_before'])>.1 for v in balance):alerts.append('Some unadjusted covariates have |SMD| > 0.10 or undefined standardization.')
    ws=None
    if w1 is not None:
        ws={'treated_ess':ess(w1),'control_ess':ess(w0),'max_treated_weight':float(w1.max()),'max_control_weight':float(w0.max())}
        if min(ess(w1),ess(w0))<20:alerts.append('Effective sample size is below 20 in an adjusted group.')
        if any(v['smd_after'] is not None and abs(v['smd_after'])>.1 for v in balance):alerts.append('Residual imbalance remains after matching/weighting.')
    return {'status':'warning' if alerts else 'no_flagged_problem','histogram':{'bin_edges':bins.tolist(),
            'treated':np.histogram(p[t],bins)[0].tolist(),'control':np.histogram(p[~t],bins)[0].tolist()},
            'empirical_common_range':[float(lo),float(hi)] if lo<=hi else None,
            'outside_common_range_fraction':outside,'extreme_fraction':extreme,'balance':balance,'weights':ws,
            'adjustment_method':method,'propensity_model':'Standardized L2 logistic propensity model, C=1.0',
            'warnings':alerts,'note':'Heuristic diagnostics, not proof of positivity or no confounding. No trimming applied.'}

def unavailable(reason):return {'status':'unavailable','lower':None,'upper':None,'standard_error':None,'reason':reason}

def regression(d):
    s=d.spec;x=design(d,d.t)
    if len(x)<=x.shape[1]+5 or np.linalg.matrix_rank(x)<x.shape[1]:raise AnalysisError('Insufficient residual degrees of freedom or rank-deficient design.','singular_design')
    a,b=(0.,1.) if s['treatment_kind']=='categorical' else (s['control_value'],s['treatment_value'])
    x0,x1=design(d,np.full(len(x),a)),design(d,np.full(len(x),b));alerts=[]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',sm.tools.sm_exceptions.PerfectSeparationWarning)
            warnings.simplefilter('error',RuntimeWarning)
            if s['method']=='logistic_regression':
                fit=sm.GLM(d.y,x,family=sm.families.Binomial()).fit(cov_type='HC0',maxiter=200)
                if not fit.converged:raise AnalysisError('Logistic outcome model did not converge.','estimation_failed')
                p0,p1=expit(x0@fit.params),expit(x1@fit.params)
                effect=float((p1-p0)[d.target].mean())
                gradient=(p1[:,None]*(1-p1[:,None])*x1-p0[:,None]*(1-p0[:,None])*x0)[d.target].mean(axis=0)
                q=norm.ppf((1+s['confidence'])/2);label='HC0 sandwich/delta; empirical target covariates fixed'
            else:
                fit=sm.OLS(d.y,x).fit(cov_type='HC3',use_t=True)
                gradient=(x1-x0)[d.target].mean(axis=0);effect=float(gradient@fit.params)
                q=student_t.ppf((1+s['confidence'])/2,fit.df_resid);label='HC3 linear contrast with t reference; empirical target covariates fixed'
                if s['outcome_kind']=='binary':
                    pred=np.r_[x0@fit.params,x1@fit.params]
                    if ((pred<0)|(pred>1)).any():alerts.append('Linear probability predictions leave [0,1] for some interventions. Consider logistic outcome regression.')
            se=float(np.sqrt(max(0.,gradient@fit.cov_params()@gradient)))
    except (ValueError,np.linalg.LinAlgError,RuntimeWarning,sm.tools.sm_exceptions.PerfectSeparationWarning,sm.tools.sm_exceptions.PerfectSeparationError) as exc:
        raise AnalysisError('Outcome regression failed or separated. No descriptive fallback was substituted.','estimation_failed') from exc
    if not np.isfinite([effect,se]).all():raise AnalysisError('Non-finite effect or uncertainty; no fallback substituted.','estimation_failed')
    return effect,{'status':'available','level':s['confidence'],'lower':float(effect-q*se),'upper':float(effect+q*se),
                   'standard_error':se,'method':label,'scope':'Independent observations; excludes graph-selection and unmeasured-confounding uncertainty.'},alerts

def bootstrap(d):
    s=d.spec
    if len(d.t)>10000:return unavailable('Full-refit weighting bootstrap is limited to 10,000 observations.')
    rng=np.random.default_rng(s['seed']);estimates=[]
    for _ in range(s['bootstrap_reps']):
        ix=rng.integers(0,len(d.t),len(d.t));t,y,x=d.t[ix],d.y[ix],d.x[ix]
        if len(np.unique(t))<2:continue
        try:
            w1,w0=weights(t,propensity(t,x),s['estimand']);v=float(np.average(y,weights=w1)-np.average(y,weights=w0))
            if np.isfinite(v):estimates.append(v)
        except AnalysisError:continue
    if len(estimates)<max(40,.9*s['bootstrap_reps']):r=unavailable('Too many bootstrap refits failed; no partial interval is presented.')
    else:
        a=(1-s['confidence'])/2;lo,hi=np.quantile(estimates,[a,1-a])
        r={'status':'available','level':s['confidence'],'lower':float(lo),'upper':float(hi),'standard_error':float(np.std(estimates,ddof=1)),
           'method':'IID percentile bootstrap, propensity refitted in every replicate','scope':'Independent observations, adequate overlap and appropriate models; no graph uncertainty.'}
    r.update(requested_replicates=s['bootstrap_reps'],successful_replicates=len(estimates),seed=s['seed']);return r

def analyze(frame,dag,supplied):
    s=validate_spec(supplied)
    if not {s['treatment'],s['outcome']}.issubset({n['name'] for n in dag.get('nodes',[])}):raise AnalysisError('Draw both comparison variables on the saved graph.','invalid_graph')
    identification=({'identified_under_graph':False,'strategy':'none — descriptive only','adjustment_set':[]}
                    if s['method']=='descriptive_difference' else identify(dag,s['treatment'],s['outcome'],[c['name'] for c in s['covariates']]))
    d=prepare(frame,s);alerts=[];extra={};diag={'status':'not_assessed','note':'These propensity diagnostics require a two-group categorical treatment.'}
    if s['method'] in {'linear_regression','logistic_regression'}:
        effect,interval,alerts=regression(d)
        if s['treatment_kind']=='categorical':
            try:diag=diagnostics(d,propensity(d.t,d.x))
            except AnalysisError as exc:diag={'status':'unavailable','note':str(exc)};alerts.append('Comparability could not be assessed; predictions may extrapolate.')
    elif s['method'] in {'propensity_score_weighting','propensity_score_matching'}:
        p=propensity(d.t,d.x)
        if s['method']=='propensity_score_weighting':
            w1,w0=weights(d.t,p,s['estimand']);interval=bootstrap(d) if s['uncertainty']=='auto' else unavailable('Not requested.')
        else:
            w1,w0,extra=matches(d.t,p,s['estimand']);interval=unavailable('Matching-appropriate variance is not implemented; ordinary bootstrap is deliberately not substituted.')
            alerts.append('Matching uses no caliper. Review match distances and remaining imbalance.')
        effect=float(np.average(d.y,weights=w1)-np.average(d.y,weights=w0));diag=diagnostics(d,p,w1,w0,s['method'])
    else:
        a,b=d.y[d.t==1],d.y[d.t==0];effect=float(a.mean()-b.mean());v1,v0=a.var(ddof=1)/len(a),b.var(ddof=1)/len(b);se=float(np.sqrt(v1+v0))
        if se:
            df=(v1+v0)**2/(v1**2/(len(a)-1)+v0**2/(len(b)-1));q=student_t.ppf((1+s['confidence'])/2,df)
            interval={'status':'available','level':s['confidence'],'lower':float(effect-q*se),'upper':float(effect+q*se),'standard_error':se,'method':'Welch independent-group mean difference'}
        else:interval=unavailable('No within-group outcome variation.')
        alerts.append('Unadjusted descriptive difference, not an identified causal estimate.')
    if s['uncertainty']=='none':interval=unavailable('Not requested.')
    if d.sample['excluded_other_treatment_levels']:alerts.append('Other treatment levels were excluded; the target is restricted to the two selected levels.')
    if d.sample['excluded_missing']:alerts.append('Reviewed complete-case exclusion was applied; selection bias remains possible.')
    alerts.extend(diag.get('warnings',[]));alerts.append('Estimates, intervals and diagnostics do not validate the causal graph or exclude unmeasured confounding.')
    return {'schema_version':'aitiolin.p1.result.v1','specification':s,
            'analysis_kind':'descriptive' if s['method']=='descriptive_difference' else 'backdoor_assumption_conditional',
            'method_label':METHODS[s['method']],'estimated_effect':effect,'confidence_interval':interval,
            'effect_scale':'risk_difference' if s['outcome_kind']=='binary' else 'outcome_difference',
            'percentage_points':effect*100 if s['outcome_kind']=='binary' else None,
            'units':'probability (0–1)' if s['outcome_kind']=='binary' else s['units'],
            'target_population':s['estimand'],'identification':identification,'analysis_rows_sha256':d.rows_sha256,
            'sample':d.sample,'encoding':d.encoding,'diagnostics':diag,'method_details':extra,'warnings':alerts}
