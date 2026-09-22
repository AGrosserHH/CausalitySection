# Reviewed comparisons

Module version: `0.1.0-p1.1` (a label recorded inside run bundles). This extends the existing private-use prototype; it is not a production or security certification.

## Scope

- A collapsed **Reviewed comparison** panel above the existing inference output. The existing canvas, agent and surrounding layout are retained.
- Explicit control/treatment values, binary outcome event, units, ATE/ATT/ATC for two selected treatment categories and regression ATE contrasts for continuous doses.
- Reviewed numeric/nominal adjustment, one-hot references, treatment interactions and complete-case exclusion. No silent imputation in the comparison engine.
- Linear HC3 intervals, logistic standardized probability differences with sandwich/delta uncertainty, full-refit IID propensity-weighting bootstrap, and explicitly unavailable matching uncertainty.
- Propensity distributions, standardized balance differences, effective sample size and match-distance diagnostics.
- Named recorded analyses, specification comparisons and reviewed JSON/ZIP restoration into a new owned graph after matching raw and replayed-cleaning hashes.
- Synthetic randomized campaign and poor-overlap teaching datasets; no provider calls.
- The legacy DoWhy entry point now fails explicitly instead of silently switching to another method or an unadjusted mean difference.

## Using the app

Load a sample or CSV; select treatment and outcome in Controls. Open the **Reviewed comparison** panel and choose **Review current data and graph**. Review the treatment values, outcome event, nominal references, adjustment, missing-data policy and assumptions. Confirm independent observations and run **Run reviewed comparison**.

These settings apply only to this analysis action. The legacy inference, agent, robustness and time-series controls retain their own configurations. Their historical diagnostics are not treated as evidence for a differently specified comparison.

Recorded comparison stages are available in the **Reproducibility exports** panel. Dataset rows are not attached; variable names and results can still be sensitive. Restoring a bundle that contains a reviewed comparison requires the matching raw CSV and a successful cleaning-replay hash check. Restoration creates a new graph without importing an old estimate as a freshly computed result.

## Checks

From the repository root:

```sh
python -m pip install -r aitiolin/causalproject/requirements.txt
cd aitiolin/causalproject
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test causal_app --noinput
```

From `aitiolin/causal-frontend`:

```sh
npm ci
npm run lint
npm test
npm run build
```

The comparison path adds no models of its own; it records into the workspace tables (`causal_app` migration `0010_workspace_models`). Workspace ownership, privacy, retention and scheduled-cleanup rules apply. Run `python manage.py migrate` and restart the backend and frontend after pulling.

## Limits

This path supports independent observations, not clustered/panel standard errors. Matching uses nearest logit propensity with replacement and no caliper; its confidence interval is deliberately unavailable. Weighting uses an IID full-refit percentile bootstrap (50–500 replicates, up to 10,000 observations). No IV/front-door extension, doubly robust estimator, causal forest, mediation or panel-design method is added.

Continuous comparisons use two fixed observed-range doses and ATE only. The backdoor check is sufficient under the supplied graph; it does not validate that graph. Bounds: 100,000 observations, 30 adjustment variables, 40 levels per nominal variable and bounded encoded model terms. Overlap flags are diagnostics, not proof of positivity or unconfoundedness. Intervals exclude graph-selection and hidden-confounding uncertainty.

Bundle input is data-only, bounded, never extracted and never executed. Checksums verify consistency, not authorship. Comparison suppresses numerical differences when targets, analyzed rows, data identities or descriptive/causal status differ.

## History

Delivered as a separate `p1` package on top of `0d5e8da` and merged in `45ae96f`, then consolidated into `causal_app/analysis/` next to the workspace layer in `causal_app/workspace/`. Identifiers that live inside exported bundles (`aitiolin.p1.v1`, the `p1` payload key, the `p1_estimate` operation) were kept so existing exports stay restorable.

The public homepage and legal pages are not overwritten. The new static `aitiolin/website/methods.html` can be published separately. No hosted service or automatic deployment is added.
