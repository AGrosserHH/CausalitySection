"""Bounded data-only bundle validation. Never extracts ZIPs or executes content."""
import hashlib
import io
import json
import math
import networkx as nx
from pathlib import PurePosixPath
import zipfile
from .engine import AnalysisError, validate_spec

MAX_JSON=4*1024*1024
MAX_ARCHIVE=8*1024*1024
MAX_EXPANDED=20*1024*1024

def _constant(_):raise AnalysisError('Non-finite JSON is not supported.','invalid_bundle')
def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise AnalysisError('Duplicate JSON key.','invalid_bundle')
        out[k]=v
    return out

def strict_json(content):
    if len(content)>MAX_JSON:raise AnalysisError('JSON exceeds 4 MiB.','bundle_too_large')
    try:doc=json.loads(content.decode('utf-8-sig'),parse_constant=_constant,object_pairs_hook=_pairs)
    except (ValueError,UnicodeDecodeError,RecursionError) as exc:raise AnalysisError('Invalid, non-finite, duplicate-key or overly nested JSON.','invalid_bundle') from exc
    count=0
    def bounded(item,depth=0):
        nonlocal count
        count+=1
        if count>100000 or depth>30:raise AnalysisError('Bundle nesting/item limits exceeded.')
        if isinstance(item,float) and not math.isfinite(item):raise AnalysisError('Non-finite JSON value.')
        for v in item.values() if isinstance(item,dict) else item if isinstance(item,list) else []:bounded(v,depth+1)
    bounded(doc)
    if not isinstance(doc,dict):raise AnalysisError('Bundle root must be an object.')
    return doc

def read_bundle(content):
    if len(content)>MAX_ARCHIVE:raise AnalysisError('Bundle exceeds 8 MiB.','bundle_too_large')
    if content[:2]!=b'PK':return strict_json(content)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            entries=z.infolist();names=[i.filename for i in entries]
            if not 1<=len(entries)<=20 or len(names)!=len(set(names)) or 'run.json' not in names:
                raise AnalysisError('Invalid ZIP entry count, duplicate names or missing run.json.')
            if sum(i.file_size for i in entries)>MAX_EXPANDED:raise AnalysisError('Expanded ZIP size limit exceeded.')
            for info in entries:
                name=PurePosixPath(info.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in info.filename or ':' in info.filename or info.is_dir():raise AnalysisError('Unsafe ZIP path.')
                if info.file_size>MAX_JSON or info.flag_bits&1 or ((info.external_attr>>16)&0o170000)==0o120000:raise AnalysisError('Oversized, encrypted or symbolic-link ZIP member.')
                if info.file_size>1024*1024 and info.file_size/max(1,info.compress_size)>500:raise AnalysisError('Suspicious ZIP compression ratio.')
            if 'checksums.json' in names:
                checks=strict_json(z.read('checksums.json'))
                if 'run.json' not in checks:raise AnalysisError('Checksums must include run.json.')
                for name,expected in checks.items():
                    if name not in names or hashlib.sha256(z.read(name)).hexdigest()!=expected:raise AnalysisError('Bundle checksum mismatch.')
            return strict_json(z.read('run.json'))
    except (zipfile.BadZipFile,RuntimeError,OSError,KeyError) as exc:raise AnalysisError('Unreadable or corrupt ZIP.','invalid_bundle') from exc

def validate_document(doc):
    if not isinstance(doc,dict) or doc.get('schema_version')!='aitiolin.run.v1' or not isinstance(doc.get('p1'),dict) or doc['p1'].get('schema_version')!='aitiolin.p1.v1':
        raise AnalysisError('Only P1-bearing run bundles can be restored; P0-only records lack an explicit comparison schema.','unsupported_bundle')
    spec=validate_spec(doc['p1'].get('specification'))
    snap=doc.get('snapshot')
    if not isinstance(snap,dict) or not isinstance(snap.get('dag'),dict):raise AnalysisError('Missing graph snapshot.')
    nodes=snap['dag'].get('nodes');edges=snap['dag'].get('edges')
    if not isinstance(nodes,list) or not 2<=len(nodes)<=250 or not isinstance(edges,list) or len(edges)>2000:raise AnalysisError('Invalid graph size.')
    names=set();ns=[]
    for n in nodes:
        if not isinstance(n,dict) or not isinstance(n.get('name'),str) or not 1<=len(n['name'])<=100 or n['name'] in names:raise AnalysisError('Invalid or duplicate node.')
        names.add(n['name']);p=n.get('position') or {'x':100,'y':100}
        if not isinstance(p,dict) or any(type(p.get(k)) not in (int,float) or not math.isfinite(p[k]) or abs(p[k])>1e6 for k in ('x','y')):raise AnalysisError('Invalid node position.')
        ns.append({'name':n['name'],'position':{k:p[k] for k in ('x','y')}})
    if not {spec['treatment'],spec['outcome'],*[c['name'] for c in spec['covariates']]}.issubset(names):raise AnalysisError('Comparison variable absent from the imported graph.')
    es=[];seen=set()
    for e in edges:
        if not isinstance(e,dict) or not isinstance(e.get('source'),str) or not isinstance(e.get('target'),str) or e['source'] not in names or e['target'] not in names or e['source']==e['target']:raise AnalysisError('Invalid edge endpoint.')
        pair=e['source'],e['target']
        if pair in seen or e.get('directed',True) is not True:raise AnalysisError('Duplicate or undirected edge.')
        seen.add(pair);es.append({'source':pair[0],'target':pair[1],'directed':True,'manual_lock':e.get('manual_lock') is True})
    graph=nx.DiGraph();graph.add_nodes_from(names);graph.add_edges_from((e['source'],e['target']) for e in es)
    if not nx.is_directed_acyclic_graph(graph):raise AnalysisError('Imported graph contains a directed cycle.')
    data=snap.get('data')
    if not isinstance(data,dict) or data.get('effective') not in ('raw','cleaned') or 'raw' not in data:raise AnalysisError('Raw-data hash and effective-data declaration are required.')
    for kind in ('raw','cleaned'):
        if kind in data:
            item=data[kind]
            if not isinstance(item,dict) or not isinstance(item.get('sha256'),str) or len(item['sha256'])!=64 or any(c not in '0123456789abcdef' for c in item['sha256']):raise AnalysisError('Invalid data hash.')
    history=snap.get('cleaning',[])
    if not isinstance(history,list) or len(history)>40:raise AnalysisError('Cleaning history limit exceeded.')
    allowed={'drop_column':set(),'drop_duplicate_rows':set(),'coerce_numeric':{'errors'},
             'normalize_datetime':{'format'},'cap_outliers':{'method','factor'},'log_transform':{'base'},'impute_missing':{'strategy'}}
    safe=[]
    for event in history:
        if not isinstance(event,dict) or not isinstance(event.get('request'),dict):raise AnalysisError('Cleaning event needs an explicit request.')
        steps=event['request'].get('steps')
        if not isinstance(steps,list) or len(steps)>100:raise AnalysisError('Invalid cleaning steps.')
        out=[]
        for step in steps:
            if not isinstance(step,dict) or not isinstance(step.get('step_type'),str) or step['step_type'] not in allowed:raise AnalysisError('Unknown cleaning action; no scripts are imported.')
            kind=step['step_type'];params=step.get('params') or {};column=step.get('column')
            if not isinstance(params,dict) or set(params)-allowed[kind]:raise AnalysisError('Unsupported cleaning parameters.')
            if kind!='drop_duplicate_rows' and (not isinstance(column,str) or not 1<=len(column)<=100):raise AnalysisError('Invalid cleaning column.')
            if kind=='log_transform' and params.get('base','e')!='e':raise AnalysisError('Only natural-log cleaning is restored.')
            if kind=='impute_missing' and params.get('strategy') not in ('median','mode'):raise AnalysisError('Only median/mode imputation is restored.')
            if kind=='cap_outliers' and (params.get('method','iqr')!='iqr' or type(params.get('factor',3)) not in (int,float) or not .1<=params.get('factor',3)<=20):raise AnalysisError('Unsupported capping parameters.')
            out.append({'step_id':str(step.get('step_id',''))[:160],'step_type':kind,'column':column,'params':params})
        safe.append({'request':{'steps':out}})
    return {'specification':spec,'dag':{'nodes':ns,'edges':es},'data':data,'cleaning':safe,
            'notice':'Free-text edge evidence is not restored; manual locks remain user assertions, not proof.'}
