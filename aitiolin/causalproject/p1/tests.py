"""Real Django/P1 integration tests (no mocked treatment-effect calculator).
Requires the complete installed upstream repository, its dependencies and P0 migration.
"""
import io,json,shutil,tempfile
from pathlib import Path
from django.conf import settings
from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from causal_app.models import CausalGraph
from p0.models import RunRecord

class P1ApiTests(TestCase):
    def setUp(self):
        self.media=tempfile.mkdtemp(prefix='aitiolin-p1-')
        self.override=override_settings(MEDIA_ROOT=self.media,OPENAI_API_KEY='')
        self.override.enable();self.addCleanup(self.override.disable);self.addCleanup(shutil.rmtree,self.media,True)
        self.client=APIClient();self.client.credentials(HTTP_X_AITIOLIN_SESSION='ef'*32,HTTP_X_AITIOLIN_SEED='42')
        r=self.client.post('/api/p1/examples/randomized/load/',{},format='json');self.assertEqual(r.status_code,200,r.content);self.loaded=r.json();self.graph_id=self.loaded['graph_id']
    def configuration(self):
        return {'name':'Campaign A','treatment':'Campaign','outcome':'Purchase','treatment_kind':'categorical','outcome_kind':'binary',
                'control_value':'0','treatment_value':'1','event_value':'1','estimand':'ATE','method':'logistic_regression',
                'covariates':[{'name':'PriorActivity','kind':'numeric'},{'name':'Channel','kind':'nominal','reference':'A'}],
                'reviewed':True,'independent_units':True,'seed':42}
    def run_comparison(self,spec=None,graph_id=None):
        gid=graph_id or self.graph_id;state=self.client.get('/api/p1/schema/',{'graph_id':gid,'treatment':'Campaign'})
        self.assertEqual(state.status_code,200,state.content)
        return self.client.post('/api/p1/estimate/',{'graph_id':gid,'state_id':state.json()['state_id'],'specification':spec or self.configuration()},format='json')
    def test_real_logistic_estimate_and_export(self):
        r=self.run_comparison();self.assertEqual(r.status_code,200,r.content);self.assertAlmostEqual(r.json()['estimated_effect'],.08,delta=.06)
        b=self.client.get(f"/api/p0/runs/{r.json()['p0_run_id']}/bundle/?file_format=json")
        self.assertEqual(b.status_code,200,b.content);self.assertFalse(b.json()['raw_data_included']);self.assertEqual(b.json()['p1']['specification']['estimand'],'ATE')
    def test_other_session_cannot_estimate(self):
        other=APIClient();other.credentials(HTTP_X_AITIOLIN_SESSION='ac'*32)
        self.assertEqual(other.get('/api/p1/schema/',{'graph_id':self.graph_id}).status_code,404)
    def test_review_required(self):
        r=self.run_comparison({**self.configuration(),'reviewed':False});self.assertEqual(r.status_code,400)
    def test_stale_state_rejected(self):
        r=self.client.post('/api/p1/estimate/',{'graph_id':self.graph_id,'state_id':'stale','specification':self.configuration()},format='json')
        self.assertEqual(r.status_code,409);self.assertEqual(r.json()['code'],'p1_stale_state')
    def test_restore_into_new_graph_without_estimation(self):
        r=self.run_comparison();self.assertEqual(r.status_code,200,r.content)
        bundle=self.client.get(f"/api/p0/runs/{r.json()['p0_run_id']}/bundle/?file_format=zip").content
        def file():
            f=io.BytesIO(bundle);f.name='analysis.zip';return f
        n=CausalGraph.objects.count();preview=self.client.post('/api/p1/bundles/preview/',{'graph_id':self.graph_id,'bundle':file()},format='multipart')
        self.assertEqual(preview.status_code,200,preview.content);self.assertEqual(CausalGraph.objects.count(),n)
        total=RunRecord.objects.count();restored=self.client.post('/api/p1/bundles/restore/',{'graph_id':self.graph_id,'bundle':file(),'confirmed':'true','approval_digest':preview.json()['approval_digest']},format='multipart')
        self.assertEqual(restored.status_code,200,restored.content);self.assertNotEqual(restored.json()['graph_id'],self.graph_id);self.assertEqual(RunRecord.objects.count(),total)
    def test_named_history_and_comparison(self):
        a=self.run_comparison();b=self.run_comparison({**self.configuration(),'name':'Campaign B','method':'linear_regression'})
        self.assertEqual(a.status_code,200,a.content);self.assertEqual(b.status_code,200,b.content)
        result=self.client.post('/api/p1/compare/',{'run_ids':[a.json()['p0_run_id'],b.json()['p0_run_id']]},format='json')
        self.assertEqual(result.status_code,200,result.content);self.assertTrue(result.json()['comparable_scale_and_sample'])
        self.assertEqual(len(self.client.get('/api/p1/history/',{'graph_id':self.graph_id}).json()['runs']),2)
    def test_deletion_removes_p1_records(self):
        self.assertEqual(self.run_comparison().status_code,200)
        r=self.client.delete('/api/p0/session/data/');self.assertEqual(r.status_code,200,r.content)
        self.assertFalse(CausalGraph.objects.filter(pk=self.graph_id).exists());self.assertEqual(RunRecord.objects.count(),0)
        self.assertFalse(any(p.is_file() for p in Path(self.media).rglob('*')))
    def test_churn_real_estimator(self):
        r=self.client.post('/api/p0/samples/churn/load/',{},format='json');self.assertEqual(r.status_code,200,r.content);gid=r.json()['graph_id']
        s={'name':'Churn one-year vs month-to-month','treatment':'Contract','outcome':'Churn','control_value':'Month-to-month','treatment_value':'One year',
           'outcome_kind':'binary','event_value':'Yes','method':'logistic_regression','covariates':[{'name':'tenure','kind':'numeric'},{'name':'gender','kind':'nominal','reference':'Female'}],
           'reviewed':True,'independent_units':True,'seed':42}
        a=self.run_comparison(s,gid);self.assertEqual(a.status_code,200,a.content);self.assertEqual(a.json()['confidence_interval']['status'],'available')
    def test_worldbank_real_estimator(self):
        import pandas as pd
        r=self.client.post('/api/p0/samples/worldbank/load/',{},format='json');self.assertEqual(r.status_code,200,r.content);gid=r.json()['graph_id']
        g=CausalGraph.objects.get(pk=gid);f=pd.read_csv(g.data_file.path)
        cols=['health_expenditure_per_capita','child_mortality_rate','gdp_per_capita','region'];f=f[cols].dropna()
        a,b=f.health_expenditure_per_capita.quantile([.25,.75]).tolist()
        s={'name':'World Bank continuous contrast','treatment':cols[0],'outcome':cols[1],'treatment_kind':'continuous','control_value':a,'treatment_value':b,
           'method':'linear_regression','covariates':[{'name':'gdp_per_capita','kind':'numeric'},{'name':'region','kind':'nominal','reference':str(f.region.mode()[0])}],
           'missing':'complete_case','reviewed':True,'independent_units':True,'seed':42,'units':'deaths per 100 live births'}
        a=self.run_comparison(s,gid);self.assertEqual(a.status_code,200,a.content)
