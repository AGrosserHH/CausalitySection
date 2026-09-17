#!/usr/bin/env python3
"""Apply only the four P1 integration edits after exact baseline checks.

Designed for a disposable integration checkout; does not install, push, or touch data.
--check verifies the wiring without writing. --apply accepts the inspected baseline
only, refuses partial integrations, and writes no runtime settings or credentials.
"""
import argparse
import ast
import hashlib
from pathlib import Path
EXPECTED={'aitiolin/causal-frontend/src/AppRoot.vue': 'c2ff642d95c9f85430029a4fc8515c9480354884', 'aitiolin/causalproject/causal_project/urls.py': '8af34f4765ae623995ddd2e9c855e6bc2587dbb1', 'aitiolin/causalproject/causal_app/services.py': '3bc4f0ac2b644113774682efdf78ab4f7c6909db', 'aitiolin/causalproject/p0/service.py': '1556857f5e7cdea0bbe6ff7041df2c2898d57ce1'}
PANEL='      <P1AnalysisPanel\n        :graph-id="graphId" :variables="variables"\n        :treatment-id="selectedTreatment" :outcome-id="selectedOutcome"\n        :graph-revision="graphRevision" :data-revision="JSON.stringify(agentCleaningResult)"\n        :prepare-graph="persistGraphEdges" @sample-loaded="loadP0Sample"\n      />\n\n'
LEGACY='def estimate_effect(\n    data_frame: pd.DataFrame,\n    treatment_name: str,\n    outcome_name: str,\n    dot_graph: str,\n    requested_method: str | None,\n) -> dict[str, Any]:\n    """Legacy DoWhy entry point: fail explicitly; never silently switch estimators.\n\n    For reviewed encoding, explicit contrasts and uncertainty use the P1 path.\n    """\n    causal_model_class = get_causal_model_class()\n    model = causal_model_class(data=data_frame, treatment=treatment_name,\n                               outcome=outcome_name, graph=dot_graph)\n    identified_estimand = model.identify_effect()\n    if identified_estimand is None:\n        raise ValueError("Causal effect not identifiable from the given graph.")\n    method_name = select_estimation_method(identified_estimand, requested_method)\n    if method_name is None or method_name == "backdoor.diff_in_means_fallback":\n        raise ValueError("No supported identified method selected. Use an explicitly labelled descriptive comparison separately.")\n    try:\n        causal_estimate = model.estimate_effect(identified_estimand, method_name=method_name)\n        value = getattr(causal_estimate, "value", getattr(causal_estimate, "estimate", None))\n        if np.ndim(value) != 0 or value is None or not np.isfinite(float(value)):\n            raise ValueError("Estimator did not return a finite scalar effect.")\n    except Exception as exc:\n        raise ValueError(\n            f"The requested estimator ({method_name}) failed. "\n            "No other method or unadjusted mean difference was substituted. "\n            "Review encoding, identification and method compatibility."\n        ) from exc\n    return {"estimated_effect": float(value), "method_name": method_name,\n            "estimand_string": str(identified_estimand)}\n'

def once(text, anchor, replacement):
    if text.count(anchor) != 1:
        raise ValueError('Changed or duplicate integration anchor; rebase the source patch.')
    return text.replace(anchor, replacement, 1)

def patch_sources(originals,legacy):
    out=dict(originals);root='aitiolin/causal-frontend/src/AppRoot.vue'
    anchor='import CausalityAgentPanel from "./components/CausalityAgentPanel.vue"'
    out[root]=once(out[root],anchor,anchor+'\nimport P1AnalysisPanel from "./components/P1AnalysisPanel.vue"')
    anchor='      <div id="inference-result-anchor">';out[root]=once(out[root],anchor,PANEL+anchor)
    url='aitiolin/causalproject/causal_project/urls.py';anchor="    path('api/p0/', include('p0.urls')),"
    out[url]=once(out[url],anchor,"    path('api/p1/', include('p1.urls')),\n"+anchor)
    service='aitiolin/causalproject/p0/service.py';anchor='(root / "causal_app", root / "p0", root / "causal_project")'
    out[service]=once(out[service],anchor,'(root / "causal_app", root / "p0", root / "p1", root / "causal_project")')
    service='aitiolin/causalproject/causal_app/services.py';tree=ast.parse(out[service]);functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='estimate_effect']
    if len(functions)!=1:raise ValueError('Expected one legacy estimate_effect definition.')
    f=functions[0];start=min([f.lineno]+[d.lineno for d in f.decorator_list]);lines=out[service].splitlines(keepends=True)
    out[service]=''.join(lines[:start-1])+legacy.rstrip()+'\n'+''.join(lines[f.end_lineno:])
    for path,text in out.items():
        if path.endswith('.py'):ast.parse(text)
    return out

def integrated(originals):
    app = originals['aitiolin/causal-frontend/src/AppRoot.vue']
    urls = originals['aitiolin/causalproject/causal_project/urls.py']
    provenance = originals['aitiolin/causalproject/p0/service.py']
    service = originals['aitiolin/causalproject/causal_app/services.py']
    functions = [n for n in ast.parse(service).body if isinstance(n, ast.FunctionDef) and n.name == 'estimate_effect']
    return (app.count('<P1AnalysisPanel') == 1
        and app.count('import P1AnalysisPanel from "./components/P1AnalysisPanel.vue"') == 1
        and urls.count("path('api/p1/', include('p1.urls'))") == 1
        and '(root / "causal_app", root / "p0", root / "p1", root / "causal_project")' in provenance
        and len(functions) == 1
        and ast.dump(functions[0], include_attributes=False) == ast.dump(ast.parse(LEGACY).body[0], include_attributes=False))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.apply == args.check:
        parser.error('Choose exactly one of --apply and --check.')
    root = Path(__file__).resolve().parents[1]
    originals = {path: (root/path).read_text(encoding='utf-8') for path in EXPECTED}
    if integrated(originals):
        print('P1 integration is present; no source edits needed.')
        return
    if args.check:
        raise SystemExit('P1 integration is missing or differs from the reviewed patch.')
    for path, expected in EXPECTED.items():
        data = (root/path).read_bytes().replace(b'\r\n', b'\n')
        actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if actual != expected:
            raise SystemExit('Baseline mismatch: '+path+'; refusing to overwrite.')
    changed = patch_sources(originals, LEGACY)
    if not integrated(changed):
        raise SystemExit('Generated integration failed its check; no files changed.')
    written = []
    try:
        for path, text in changed.items():
            (root/path).write_text(text, encoding='utf-8'); written.append(path)
    except Exception:
        for path in written:
            (root/path).write_text(originals[path], encoding='utf-8')
        raise
    print('Applied and verified the four source integration edits.')

if __name__ == '__main__':
    main()
