import copy
import unittest
import numpy as np
import pandas as pd
from causal_app.analysis.engine import AnalysisError, analyze, identify, inspect_columns, validate_spec, weights

DAG={'nodes':[{'name':v} for v in ['T','Y','X','Region']], 'edges':[{'source':a,'target':b} for a,b in [('X','T'),('X','Y'),('T','Y'),('Region','Y')]]}
def data(n=1000):
    r=np.random.default_rng(142);x=r.normal(size=n);t=r.binomial(1,1/(1+np.exp(-.8*x)))
    return pd.DataFrame({'X':x,'T':t,'Y':2*t+3*x+r.normal(size=n),'Region':r.choice(['A','B','C'],n)})
def spec(**kw):
    s={'treatment':'T','outcome':'Y','control_value':'0','treatment_value':'1','covariates':[{'name':'X','kind':'numeric'}],'reviewed':True,'independent_units':True};s.update(kw);return s
class EngineTests(unittest.TestCase):
    def test_linear_effect_and_interval(self):
        a=analyze(data(),DAG,spec());self.assertAlmostEqual(a['estimated_effect'],2,delta=.15)
        self.assertLess(a['confidence_interval']['lower'],2);self.assertGreater(a['confidence_interval']['upper'],2)
    def test_reverse_comparison(self):
        a=analyze(data(),DAG,spec());b=analyze(data(),DAG,spec(control_value='1',treatment_value='0'))
        self.assertAlmostEqual(a['estimated_effect'],-b['estimated_effect'],places=8)
    def test_interactions_target_population(self):
        f=data();f['Y']=(1+f.X)*f['T']+f.X
        for target,expected in [('ATE',1+f.X.mean()),('ATT',1+f.loc[f['T']==1,'X'].mean()),('ATC',1+f.loc[f['T']==0,'X'].mean())]:
            a=analyze(f,DAG,spec(interactions=['X'],estimand=target));self.assertAlmostEqual(a['estimated_effect'],expected,places=8)
    def test_nominal_label_invariance(self):
        s=spec(covariates=[{'name':'X','kind':'numeric'},{'name':'Region','kind':'nominal','reference':'A'}]);f=data();a=analyze(f,DAG,s)
        f.Region=f.Region.map({'A':'z','B':'m','C':'a'});s['covariates'][1]['reference']='z';b=analyze(f,DAG,s)
        self.assertAlmostEqual(a['estimated_effect'],b['estimated_effect'],places=8);self.assertEqual(a['encoding'][1]['kind'],'one_hot')
    def test_binary_event_mapping(self):
        f=data();r=np.random.default_rng(21);f.Y=np.where(r.binomial(1,1/(1+np.exp(-(-.6+.8*f['T']+.3*f.X)))),'leave','stay')
        s=spec(method='logistic_regression',outcome_kind='binary',event_value='leave');a=analyze(f,DAG,s);b=analyze(f,DAG,{**s,'event_value':'stay'})
        self.assertGreater(a['estimated_effect'],0);self.assertAlmostEqual(a['estimated_effect'],-b['estimated_effect'],places=7)
        self.assertEqual(a['percentage_points'],a['estimated_effect']*100)
    def test_binary_logistic_interval(self):
        f=data();r=np.random.default_rng(27);f.Y=r.binomial(1,1/(1+np.exp(-(-1+.5*f['T']+.1*f.X))))
        a=analyze(f,DAG,spec(method='logistic_regression',outcome_kind='binary',event_value='1'));self.assertEqual(a['confidence_interval']['status'],'available')
    def test_no_silent_missing_imputation(self):
        f=data();f.loc[0,'Y']=np.nan
        with self.assertRaisesRegex(AnalysisError,'complete-case'):analyze(f,DAG,spec())
        self.assertEqual(analyze(f,DAG,spec(missing='complete_case'))['sample']['excluded_missing'],1)
    def test_bad_numeric_values_fail(self):
        f=data();f.X=f.X.astype(object);f.loc[0,'X']='bad'
        with self.assertRaisesRegex(AnalysisError,'nonnumeric'):analyze(f,DAG,spec())
    def test_other_treatment_levels_reported(self):
        f=data();f.loc[:19,'T']=2;self.assertEqual(analyze(f,DAG,spec())['sample']['excluded_other_treatment_levels'],20)
    def test_continuous_contrast(self):
        f=data();f['T']=np.linspace(10,100,len(f));f.Y=3*f['T']+f.X
        self.assertAlmostEqual(analyze(f,DAG,spec(treatment_kind='continuous',control_value=20,treatment_value=40))['estimated_effect'],60,places=7)
    def test_continuous_att_rejected(self):
        with self.assertRaises(AnalysisError):validate_spec(spec(treatment_kind='continuous',estimand='ATT'))
    def test_dose_extrapolation_rejected(self):
        with self.assertRaises(AnalysisError):analyze(data(),DAG,spec(treatment_kind='continuous',control_value=-1,treatment_value=4))
    def test_unknown_method_rejected(self):
        with self.assertRaises(AnalysisError):validate_spec(spec(method='magic'))
    def test_review_required(self):
        with self.assertRaises(AnalysisError):validate_spec(spec(reviewed=False))
    def test_independence_confirmation(self):
        with self.assertRaises(AnalysisError):validate_spec(spec(independent_units=False))
    def test_weight_formulas(self):
        t=np.array([1.,0.]);p=np.array([.2,.8])
        a,b=weights(t,p,'ATT');np.testing.assert_allclose(a,[1,0]);np.testing.assert_allclose(b,[0,4])
        a,b=weights(t,p,'ATC');np.testing.assert_allclose(a,[4,0]);np.testing.assert_allclose(b,[0,1])
    def test_weighting_effect_and_balance(self):
        a=analyze(data(1500),DAG,spec(method='propensity_score_weighting',uncertainty='none'))
        self.assertAlmostEqual(a['estimated_effect'],2,delta=.35);row=a['diagnostics']['balance'][0]
        self.assertLess(abs(row['smd_after']),abs(row['smd_before']));self.assertGreater(a['diagnostics']['weights']['treated_ess'],0)
    def test_matching_interval_explicitly_unavailable(self):
        a=analyze(data(),DAG,spec(method='propensity_score_matching'))
        self.assertAlmostEqual(a['estimated_effect'],2,delta=.5);self.assertEqual(a['confidence_interval']['status'],'unavailable')
        self.assertIn('bootstrap',a['confidence_interval']['reason'])
    def test_matching_all_targets(self):
        for target in ['ATE','ATT','ATC']:self.assertEqual(analyze(data(),DAG,spec(method='propensity_score_matching',estimand=target))['target_population'],target)
    def test_poor_overlap_despite_treatment_variation(self):
        f=data();f['T']=(f.X>0).astype(int);a=analyze(f,DAG,spec())
        self.assertEqual(a['diagnostics']['status'],'warning');self.assertGreater(a['diagnostics']['outside_common_range_fraction'],.9)
    def test_bootstrap_repeatability(self):
        s=spec(method='propensity_score_weighting',bootstrap_reps=50);a=analyze(data(250),DAG,s);b=analyze(data(250),DAG,s)
        self.assertEqual(a['confidence_interval'],b['confidence_interval']);self.assertEqual(a['confidence_interval']['successful_replicates'],50)
    def test_descriptive_result_not_identified(self):
        a=analyze(data(),DAG,spec(method='descriptive_difference',covariates=[]));self.assertEqual(a['analysis_kind'],'descriptive');self.assertFalse(a['identification']['identified_under_graph'])
    def test_unblocked_confounder_rejected(self):
        with self.assertRaisesRegex(AnalysisError,'backdoor'):analyze(data(),DAG,spec(covariates=[]))
    def test_mediator_rejected(self):
        d=copy.deepcopy(DAG);d['edges'].append({'source':'T','target':'Region'})
        with self.assertRaisesRegex(AnalysisError,'descendants'):identify(d,'T','Y',['X','Region'])
    def test_collider_conditioning_opens_path(self):
        d={'nodes':[{'name':n} for n in ['T','Y','A','B','C']],'edges':[{'source':a,'target':b} for a,b in [('A','T'),('A','C'),('B','C'),('B','Y'),('T','Y')]]}
        identify(d,'T','Y',[])
        with self.assertRaises(AnalysisError):identify(d,'T','Y',['C'])
    def test_cycles_rejected(self):
        d=copy.deepcopy(DAG);d['edges'].append({'source':'Y','target':'T'})
        with self.assertRaises(AnalysisError):identify(d,'T','Y',['X'])
    def test_singular_design_no_fallback(self):
        f=data();f.Region=f.X
        with self.assertRaisesRegex(AnalysisError,'rank-deficient'):analyze(f,DAG,spec(covariates=[{'name':'X','kind':'numeric'},{'name':'Region','kind':'numeric'}]))
    def test_profile_does_not_encode_or_mutate(self):
        f=data();old=f.copy();cols=inspect_columns(f);self.assertEqual(next(c for c in cols if c['name']=='Region')['suggested_kind'],'nominal');pd.testing.assert_frame_equal(f,old)
    def test_seed_bounds(self):
        for value in [True,-1,1.5,2**32]:
            with self.assertRaises(AnalysisError):validate_spec(spec(seed=value))
    def test_three_outcome_classes_not_binary(self):
        f=data();f.Y=np.arange(len(f))%3
        with self.assertRaisesRegex(AnalysisError,'exactly two'):analyze(f,DAG,spec(outcome_kind='binary',event_value=1))
if __name__=='__main__':unittest.main()
