# P1 reviewed analysis integration

P1 module version: `0.1.0-p1.1`. This extends the existing private-use prototype; it is not a production or security certification.

## Scope

- A collapsed **Reviewed comparison — P1 analysis** panel above the existing inference output. The existing canvas, agent and surrounding layout are retained.
- Explicit control/treatment values, binary outcome event, units, ATE/ATT/ATC for two selected treatment categories and regression ATE contrasts for continuous doses.
- Reviewed numeric/nominal adjustment, one-hot references, treatment interactions and complete-case exclusion. No silent imputation in the P1 engine.
- Linear HC3 intervals, logistic standardized probability differences with sandwich/delta uncertainty, full-refit IID propensity-weighting bootstrap, and explicitly unavailable matching uncertainty.
- Propensity distributions, standardized balance differences, effective sample size and match-distance diagnostics.
- Named recorded P1 analyses, specification comparisons and reviewed JSON/ZIP restoration into a new owned graph after matching raw and replayed-cleaning hashes.
- Synthetic randomized campaign and poor-overlap teaching datasets; no provider calls.
- The legacy DoWhy entry point now fails explicitly instead of silently switching to another method or an unadjusted mean difference.

## Using the app

Load a sample or CSV; select treatment and outcome in Controls. Open the P1 panel and choose **Review current data and graph**. Review the treatment values, outcome event, nominal references, adjustment, missing-data policy and assumptions. Confirm independent observations and run **Run reviewed comparison**.

P1 settings apply only to this new analysis action. The legacy inference, agent, robustness and time-series controls retain their own configurations. Their historical diagnostics are not treated as evidence for a differently specified P1 comparison.

Recorded P1 stages are available in the P0 **Reproducibility exports** panel. Dataset rows are not attached; variable names and results can still be sensitive. Restoring a P1-bearing bundle requires the matching raw CSV and a successful cleaning-replay hash check. Restoration creates a new graph without importing an old estimate as a freshly computed result.

## Checks

From the repository root:

```sh
python scripts/integrate_p1_sources.py --check
python -m pip install -r aitiolin/causalproject/requirements.txt
cd aitiolin/causalproject
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test causal_app p0 p1 --noinput
```

From `aitiolin/causal-frontend`:

```sh
npm ci
npm run lint
npm test
npm run build
```

No new models or migrations are added. Existing P0 migrations, ownership, privacy, retention and scheduled-cleanup rules still apply. Restart the local backend and frontend after pulling the integration.

## Limits

P1 supports independent observations, not clustered/panel standard errors. Matching uses nearest logit propensity with replacement and no caliper; its confidence interval is deliberately unavailable. Weighting uses an IID full-refit percentile bootstrap (50–500 replicates, up to 10,000 observations). No IV/front-door extension, doubly robust estimator, causal forest, mediation or panel-design method is added.

Continuous comparisons use two fixed observed-range doses and ATE only. The backdoor check is sufficient under the supplied graph; it does not validate that graph. Bounds: 100,000 observations, 30 adjustment variables, 40 levels per nominal variable and bounded encoded model terms. Overlap flags are diagnostics, not proof of positivity or unconfoundedness. Intervals exclude graph-selection and hidden-confounding uncertainty.

Bundle input is data-only, bounded, never extracted and never executed. Checksums verify consistency, not authorship. Comparison suppresses numerical differences when targets, analyzed rows, data identities or descriptive/causal status differ.

## Integration record

Integration starts from `3b434997c81df921e76ba5d766a5b8f4b2103983`. A malformed list-comprehension bracket in the delivered numerical test was corrected before integration. The four pre-existing source edits are applied only after exact blob-hash checks. The integration branch is tested before main is updated; see the associated pull request and Actions run for actual results.

The public homepage and legal pages are not overwritten. The new static `aitiolin/website/methods.html` can be published separately. No hosted service or automatic deployment is added.
