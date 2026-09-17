"""Small deterministic artificial teaching datasets, not observations of real customers."""
import numpy as np
import pandas as pd
from .engine import AnalysisError

def example(name):
    rng=np.random.default_rng(20260917);n=1500;x=rng.normal(size=n);channel=rng.choice(['A','B','C'],n)
    if name=='randomized':
        t=rng.binomial(1,.5,n);risk=.18+.08*t+.04*np.tanh(x)+.03*(channel=='B')
        frame=pd.DataFrame({'Campaign':t,'Purchase':rng.binomial(1,risk),'PriorActivity':x,'Channel':channel})
        treatment,outcome='Campaign','Purchase';edges=[('Campaign','Purchase'),('PriorActivity','Purchase'),('Channel','Purchase')]
        title='Synthetic randomized campaign';lesson='The generating mechanism has an 8 percentage-point risk difference. Finite-sample estimates need not equal 0.08.'
    elif name=='poor-overlap':
        t=(x>0).astype(int);frame=pd.DataFrame({'Offer':t,'Outcome':1.5*t+2*x+rng.normal(size=n),'PriorActivity':x})
        treatment,outcome='Offer','Outcome';edges=[('PriorActivity','Offer'),('PriorActivity','Outcome'),('Offer','Outcome')]
        title='Synthetic overlap stress test';lesson='The structural coefficient is 1.5, but treatment is determined by PriorActivity. Overlap fails; model extrapolation is not empirical support.'
    else:raise AnalysisError('Unknown synthetic example.')
    return frame,{'id':'p1-'+name,'title':title,'description':lesson,'treatment':treatment,'outcome':outcome,
                  'method_name':'backdoor.linear_regression','edges':edges,'seed':20260917,
                  'warnings':['Artificial educational data; no real campaign or recommendation.',lesson]}
