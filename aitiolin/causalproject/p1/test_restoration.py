import hashlib,io,unittest
import numpy as np
import pandas as pd
from p1.engine import AnalysisError
from p1.restoration import replay
class ReplayTests(unittest.TestCase):
    def setUp(self):self.raw=b'T,Y\n0,2\n1,4\n0,8\n';self.calls=[]
    def reader(self,b):return pd.read_csv(io.BytesIO(b))
    def cleaner(self,f,steps):
        self.calls.append(steps);f=f.copy()
        for s in steps:
            if s['step_type']=='log_transform':f[s['column']]=np.log(f[s['column']])
        return f,steps
    def doc(self,cleaned=False):
        d={'data':{'raw':{'sha256':hashlib.sha256(self.raw).hexdigest()},'effective':'raw'},'dag':{'nodes':[{'name':'T'},{'name':'Y'}]},'cleaning':[]}
        if cleaned:
            f=self.reader(self.raw);f.Y=np.log(f.Y);d['data'].update(effective='cleaned',cleaned={'sha256':hashlib.sha256(f.to_csv(index=False).encode()).hexdigest()});d['cleaning']=[{'request':{'steps':[{'step_type':'log_transform','column':'Y','params':{'base':'e'}}]}}]
        return d
    def test_raw_untouched(self):
        _,b,_=replay(self.doc(),self.raw,cleaner=self.cleaner,reader=self.reader);self.assertEqual(b,self.raw);self.assertEqual(self.calls,[])
    def test_cleaning_once(self):
        f,_,_=replay(self.doc(True),self.raw,cleaner=self.cleaner,reader=self.reader);self.assertEqual(len(self.calls),1);self.assertAlmostEqual(f.Y.iloc[0],np.log(2))
    def test_raw_hash_mismatch(self):
        with self.assertRaises(AnalysisError):replay(self.doc(True),b'wrong',cleaner=self.cleaner,reader=self.reader)
        self.assertEqual(self.calls,[])
    def test_cleaned_hash_mismatch(self):
        d=self.doc(True);d['data']['cleaned']['sha256']='0'*64
        with self.assertRaises(AnalysisError):replay(d,self.raw,cleaner=self.cleaner,reader=self.reader)
    def test_graph_column_absent(self):
        d=self.doc();d['dag']['nodes'].append({'name':'missing'})
        with self.assertRaises(AnalysisError):replay(d,self.raw,cleaner=self.cleaner,reader=self.reader)
    def test_invalid_raw_declaration(self):
        d=self.doc(True);d['data']['effective']='raw'
        with self.assertRaises(AnalysisError):replay(d,self.raw,cleaner=self.cleaner,reader=self.reader)
if __name__=='__main__':unittest.main()
