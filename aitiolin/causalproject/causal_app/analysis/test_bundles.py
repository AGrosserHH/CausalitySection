import hashlib,io,json,unittest,zipfile
from causal_app.analysis.bundles import read_bundle,validate_document
from causal_app.analysis.engine import AnalysisError

def doc():return {'schema_version':'aitiolin.run.v1','p1':{'schema_version':'aitiolin.p1.v1','specification':{'treatment':'T','outcome':'Y','control_value':0,'treatment_value':1,'reviewed':True,'independent_units':True}},'snapshot':{'dag':{'nodes':[{'name':'T'},{'name':'Y'}],'edges':[{'source':'T','target':'Y'}]},'data':{'raw':{'sha256':'a'*64},'effective':'raw'},'cleaning':[]}}
def archive(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for k,v in files.items():z.writestr(k,v)
    return out.getvalue()
class BundleTests(unittest.TestCase):
    def test_json(self):self.assertEqual(read_bundle(json.dumps(doc()).encode()),doc())
    def test_zip_checksums(self):
        raw=json.dumps(doc()).encode();self.assertEqual(read_bundle(archive({'run.json':raw,'checksums.json':json.dumps({'run.json':hashlib.sha256(raw).hexdigest()})})),doc())
    def test_checksum_tamper(self):
        with self.assertRaises(AnalysisError):read_bundle(archive({'run.json':json.dumps(doc()),'checksums.json':json.dumps({'run.json':'wrong'})}))
    def test_traversal(self):
        with self.assertRaises(AnalysisError):read_bundle(archive({'run.json':json.dumps(doc()),'../evil':'x'}))
    def test_absolute_path(self):
        with self.assertRaises(AnalysisError):read_bundle(archive({'run.json':json.dumps(doc()),'/tmp/evil':'x'}))
    def test_duplicate_json(self):
        with self.assertRaises(AnalysisError):read_bundle(b'{"a":1,"a":2}')
    def test_nonfinite(self):
        for content in [b'{"a":NaN}',b'{"a":Infinity}',b'{"a":1e999}']:
            with self.assertRaises(AnalysisError):read_bundle(content)
    def test_depth_limit(self):
        with self.assertRaises(AnalysisError):read_bundle(b'{"a":'+b'['*40+b'0'+b']'*40+b'}')
    def test_pickle_rejected(self):
        with self.assertRaises(AnalysisError):read_bundle(b'\x80\x04pickle')
    def test_scripts_rejected(self):
        d=doc();d['snapshot']['cleaning']=[{'request':{'steps':[{'step_type':'exec','params':{'code':'evil'}}]}}]
        with self.assertRaises(AnalysisError):validate_document(d)
    def test_workspace_only_bundle_rejected(self):
        d=doc();del d['p1']
        with self.assertRaises(AnalysisError):validate_document(d)
    def test_locks_preserved(self):
        d=doc();d['snapshot']['dag']['edges'][0]['manual_lock']=True;self.assertTrue(validate_document(d)['dag']['edges'][0]['manual_lock'])
    def test_free_text_evidence_not_restored(self):
        d=doc();d['snapshot']['dag']['edges'][0]['evidence']=[{'html':'<script>x</script>'}];self.assertNotIn('evidence',validate_document(d)['dag']['edges'][0])
    def test_unknown_schema(self):
        d=doc();d['schema_version']='unknown'
        with self.assertRaises(AnalysisError):validate_document(d)
    def test_duplicate_nodes(self):
        d=doc();d['snapshot']['dag']['nodes'].append({'name':'T'})
        with self.assertRaises(AnalysisError):validate_document(d)
    def test_malformed_p1(self):
        d=doc();d['p1']=[]
        with self.assertRaises(AnalysisError):validate_document(d)
    def test_malformed_edge(self):
        d=doc();d['snapshot']['dag']['edges'][0]['source']=[]
        with self.assertRaises(AnalysisError):validate_document(d)
    def test_malformed_step(self):
        d=doc();d['snapshot']['cleaning']=[{'request':{'steps':[{'step_type':[]}]}}]
        with self.assertRaises(AnalysisError):validate_document(d)
    def test_bad_import_seed(self):
        d=doc();d['p1']['specification']['seed']=-1
        with self.assertRaises(AnalysisError):validate_document(d)
    def test_unsupported_cleaning_parameters(self):
        d=doc();d['snapshot']['cleaning']=[{'request':{'steps':[{'step_type':'log_transform','column':'Y','params':{'base':10}}]}}]
        with self.assertRaises(AnalysisError):validate_document(d)
if __name__=='__main__':unittest.main()
