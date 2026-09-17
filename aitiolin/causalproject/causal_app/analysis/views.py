"""Reviewed-comparison REST API. Ownership, expiry and reservations come from the workspace guard.
No new database schema; successful comparison runs use the existing RunRecord exports.
"""
import uuid
from functools import wraps
import pandas as pd
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from causal_app.models import CausalGraph, CausalEdge
from causal_app.agent_service import apply_cleaning_plan
from causal_app.workspace.core import digest, json_ready, redact
from causal_app.workspace.guard import reply
from causal_app.workspace.models import RunRecord
from causal_app.workspace.service import WorkspaceError, owned_graph, snapshot, environment, remember_file
from causal_app.workspace.views import create_graph, parse_csv
from . import ANALYSIS_VERSION
from .engine import AnalysisError, METHODS, analyze, inspect_columns, validate_spec
from .bundles import MAX_ARCHIVE, read_bundle, validate_document
from .restoration import replay
from .examples import example

def errors(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except AnalysisError as exc:return reply({'error':str(exc),'code':exc.code},400)
        except ImportError:return reply({'error':'A declared analysis dependency is missing. Install requirements and rerun checks.','code':'dependency_missing'},503)
    return wrapped

def graph_for(request):
    value=request.GET.get('graph_id') if request.method=='GET' else request.data.get('graph_id')
    return owned_graph(request.workspace,value)

def current(graph):
    snap=snapshot(graph)
    field=graph.cleaned_file if graph.cleaned_file else graph.data_file
    with field.open('rb') as stream:content=stream.read()
    return parse_csv(content),snap,digest(snap)

@api_view(['GET'])
@errors
def schema(request):
    graph=graph_for(request);frame,snap,state=current(graph);treatment=request.GET.get('treatment','')
    return reply({'state_id':state,'columns':inspect_columns(frame),'dag':snap['dag'],
        'suggested_adjustment':sorted({e['source'] for e in snap['dag']['edges'] if e['target']==treatment}),
        'effective_data':snap['data']['effective'],'cleaning_history':snap['cleaning'],'methods':METHODS,
        'warning':'Treatment parents are a suggested sufficient adjustment set only under an appropriate graph with observed parents. Review timing and all relevant causal assumptions.'})

@api_view(['POST'])
@errors
def estimate(request):
    graph=graph_for(request);frame,before,state=current(graph)
    if request.data.get('state_id')!=state:raise WorkspaceError('Saved data or graph changed. Refresh and review the comparison before running.',409,'stale_state')
    spec=validate_spec(request.data.get('specification'))
    if spec['seed']!=request.workspace_seed:raise AnalysisError('Workspace seed and comparison seed differ; review and retry.')
    started=timezone.now();result=analyze(frame,before['dag'],spec)
    if before['data']['effective']=='cleaned':result['warnings'].insert(0,'Existing cleaned data were used. Review earlier transformations; this comparison cannot undo prior imputation or recoding.')
    analysis_key=digest({'analysis_version':ANALYSIS_VERSION,'snapshot':before,'specification':spec})
    record=RunRecord.objects.create(workspace=request.workspace,graph=graph,operation='p1_estimate',analysis_key=analysis_key,
        payload=json_ready({'snapshot':before,'query':{k:spec[k] for k in ('treatment','outcome','control_value','treatment_value','estimand')},
          'configuration':spec,'p1':{'schema_version':'aitiolin.p1.v1','version':ANALYSIS_VERSION,'specification':spec},
          'status':'completed','http_status':200,'started_at':started.isoformat(),'finished_at':timezone.now().isoformat(),
          'environment':environment(),'seed':{'requested':spec['seed'],'bootstrap':'NumPy default_rng per run','llm':'No provider call'},'result':redact(result)}))
    return reply({**result,'run_id':str(record.pk),'analysis_key':analysis_key,'state_id':state})

@api_view(['GET'])
@errors
def history(request):
    graph=graph_for(request)
    records=RunRecord.objects.filter(workspace=request.workspace,graph=graph,operation='p1_estimate').order_by('-created_at')[:50]
    return reply({'runs':[{'id':str(r.pk),'name':r.payload['p1']['specification']['name'],'created_at':r.created_at.isoformat(),
                           'effect':r.payload['result']['estimated_effect']} for r in records]})

@api_view(['POST'])
@errors
def compare(request):
    ids=request.data.get('run_ids')
    if not isinstance(ids,list) or len(ids)!=2:raise AnalysisError('Choose two recorded comparison runs.')
    try:ids=[uuid.UUID(str(v)) for v in ids]
    except (ValueError,TypeError):raise AnalysisError('Invalid run ID.') from None
    if ids[0]==ids[1]:raise AnalysisError('Choose two different runs.')
    rows=list(RunRecord.objects.filter(pk__in=ids,workspace=request.workspace,operation='p1_estimate'))
    if len(rows)!=2:raise WorkspaceError('Run not found in this session.',404)
    lookup={r.pk:r for r in rows};a,b=[lookup[v].payload for v in ids]
    sa,sb=a['p1']['specification'],b['p1']['specification'];ea,eb=a['result'],b['result']
    keys=('treatment','outcome','treatment_kind','outcome_kind','control_value','treatment_value','event_value','estimand','units')
    comparable=(all(sa.get(k)==sb.get(k) for k in keys) and a['snapshot']['data']==b['snapshot']['data']
                and ea.get('analysis_rows_sha256')==eb.get('analysis_rows_sha256') and ea['analysis_kind']==eb['analysis_kind'])
    diffs=[{'field':k,'before':sa.get(k),'after':sb.get(k)} for k in sorted(set(sa)|set(sb)) if sa.get(k)!=sb.get(k)]
    if a['snapshot']['dag']!=b['snapshot']['dag']:diffs.append({'field':'dag','before':a['snapshot']['dag'],'after':b['snapshot']['dag']})
    return reply({'comparable_scale_and_sample':comparable,'differences':diffs,'effects':[ea['estimated_effect'],eb['estimated_effect']],
                  'difference':eb['estimated_effect']-ea['estimated_effect'] if comparable else None,
                  'note':'Specification comparison, not selection of a true graph. Different targets/data/samples suppress the numerical difference.'})

def import_request(request):
    upload=request.FILES.get('bundle')
    if upload is None or upload.size>MAX_ARCHIVE:raise AnalysisError('Provide a JSON/ZIP bundle no larger than 8 MiB.')
    doc=read_bundle(upload.read());normalized=validate_document(doc);source=graph_for(request)
    current(source)
    with source.data_file.open('rb') as stream:raw=stream.read()
    frame,effective,applied=replay(normalized,raw,cleaner=apply_cleaning_plan,reader=parse_csv)
    return doc,normalized,raw,frame,effective,applied,digest(doc)

@api_view(['POST'])
@parser_classes([MultiPartParser,FormParser])
@errors
def preview_restore(request):
    doc,normalized,_raw,frame,_effective,_applied,sha=import_request(request)
    return reply({'approval_digest':sha,'specification':normalized['specification'],'dag':normalized['dag'],'cleaning':normalized['cleaning'],
                  'rows_after_cleaning':len(frame),'columns_after_cleaning':list(frame.columns),
                  'recorded_environment':doc.get('environment'),'current_environment':environment(),
                  'notice':'Review before restoring into a NEW graph. No estimation or graph creation occurs in preview. Edge annotations are not restored. Checksums do not authenticate an author.'})

@api_view(['POST'])
@parser_classes([MultiPartParser,FormParser])
@errors
def restore(request):
    _doc,normalized,raw,frame,effective,applied,sha=import_request(request)
    if request.data.get('confirmed')!='true' or request.data.get('approval_digest')!=sha:raise AnalysisError('Preview and explicitly confirm the exact bundle.','review_required')
    written=[]
    try:
        with transaction.atomic():
            payload=create_graph(request._request,raw,'Restored: '+normalized['specification']['name'])
            graph=CausalGraph.objects.get(pk=payload['graph_id']);written.append((graph.data_file.storage,graph.data_file.name))
            if normalized['data']['effective']=='cleaned':
                graph.cleaned_file.save(f'restored-{graph.pk}.csv',ContentFile(effective),save=False)
                written.append((graph.cleaned_file.storage,graph.cleaned_file.name));remember_file(request.workspace,graph,graph.cleaned_file.name)
                graph.cleaning_plan=applied
            owner=graph.ownership;owner.cleaning_history=normalized['cleaning'];owner.save(update_fields=['cleaning_history'])
            graph.variables.exclude(name__in=list(frame.columns)).delete()
            variables={v.name:v for v in graph.variables.all()}
            graph.node_positions={n['name']:n['position'] for n in normalized['dag']['nodes']};graph.save()
            for e in normalized['dag']['edges']:
                CausalEdge.objects.create(graph=graph,source=variables[e['source']],target=variables[e['target']],directed=True,manual_lock=e['manual_lock'])
            spec=normalized['specification']
            payload.update(graph_name=graph.name,variables=[{'id':v.pk,'name':v.name} for v in variables.values()],
                preview=json_ready(frame.head(3).to_dict(orient='records')),treatment_id=variables[spec['treatment']].pk,
                outcome_id=variables[spec['outcome']].pk,method_name='backdoor.linear_regression',comparison_specification=spec,
                sample={'warnings':['Imported assumptions require review. No estimate was restored as a fresh result.']})
        return reply(payload)
    except Exception:
        for storage,name in written:storage.delete(name)
        raise

@api_view(['POST'])
@errors
def load_synthetic(request,sample_id):
    frame,sample=example(sample_id)
    return reply(create_graph(request._request,frame.to_csv(index=False).encode('utf-8'),sample['title'],sample))
