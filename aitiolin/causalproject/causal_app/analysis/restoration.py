"""Pure replay coordinator. cleaner/reader are trusted server callables, not imported code."""
import hashlib
from .engine import AnalysisError

def replay(doc,raw,*,cleaner,reader):
    if hashlib.sha256(raw).hexdigest()!=doc['data']['raw']['sha256']:
        raise AnalysisError('Raw dataset hash differs from the bundle.','data_hash_mismatch')
    frame=reader(raw);content=raw;applied=[]
    for event in doc['cleaning']:
        frame,details=cleaner(frame,event['request']['steps'])
        content=frame.to_csv(index=False).encode('utf-8')
        frame=reader(content)  # Preserve the original API's per-event CSV round trip.
        applied.extend(details)
    if doc['data']['effective']=='cleaned':
        if hashlib.sha256(content).hexdigest()!=doc['data'].get('cleaned',{}).get('sha256'):
            raise AnalysisError('Replayed cleaning does not match the recorded cleaned-data hash; check source data and environment.','cleaning_hash_mismatch')
    elif doc['cleaning']:raise AnalysisError('Raw data declared together with applied cleaning.')
    if not {n['name'] for n in doc['dag']['nodes']}.issubset(frame.columns):raise AnalysisError('A graph node is absent from the replayed data.')
    return frame,content,applied
