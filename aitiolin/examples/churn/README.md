# IBM Telco churn: does contract commitment cause retention?

Example analysis for the causal question **"Does moving customers onto longer
contracts causally reduce churn - or do loyal, long-tenure customers simply
self-select into longer contracts?"** The answer decides whether contract-upgrade
incentives are worth real money.

This is the companion example to `../worldbank/`: there, adjustment revealed a
raw correlation to be essentially a wealth effect (no detectable causal effect);
here, the effect **survives** adjustment and every refutation test. Together the
two show the toolchain discriminating a robust effect from a spurious one.

## Files

| File | What it is |
|---|---|
| `churn.pdf` | Full analysis report produced with the app's real pipeline: agent profiling/cleaning, two LLM model drafts + analyst merge, identification, estimation, robustness, competing-model comparison. |
| dataset | `../../Churn.csv` (repository root) - IBM Telco customer churn, 7,043 customers x 21 columns. Not duplicated here; it is the app's built-in demo dataset. |

## Headline result

- **Treatment:** `Contract` (month-to-month -> one-year -> two-year, coded 0/1/2)
- **Outcome:** `Churn` (0/1)
- **Identified confounder / adjustment set:** `tenure`
- **Adjusted effect:** one contract tier ~= **-14.2 percentage points churn probability**
- Naive (unadjusted) estimate: -22.4pp - **overstates the true effect by ~58%**
  because loyal customers both pick longer contracts and churn less anyway
- Worst-case confounder-stressed model still leaves **-5.7pp**; all four
  refutation tests pass; the effect barely moves under the unobserved-confounder
  sensitivity sweep (-0.142 -> -0.117 at strength 0.5)

## Suggested walkthrough in the app

1. Upload `Churn.csv` from the Dataset sidebar.
2. **Causality Agent -> 1. Profile data**: expect `customerID` flagged as an
   identifier and `TotalCharges` flagged for missing values (the dataset's
   well-known 11 blank cells for zero-tenure customers).
3. **2. Suggest cleaning plan -> apply** the two default-accepted steps
   (drop `customerID`, impute `TotalCharges` with the median).
4. **3. Suggest causal model.** The first draft tends to be a "star" model -
   every edge pointing straight into `Churn`, no confounding structure, empty
   adjustment set. That shape is the naive feature-importance view. Re-run with
   context asking the agent to model relationships *among* covariates
   (e.g. "include how tenure influences contract choice and charges").
5. **Analyst merge (the important step):** make sure `tenure` points into
   *both* `Contract` and `Churn` on the canvas - only then is it recognized as
   a confounder. Keep the statistically supported edges from both drafts.
6. **Identification**: with the merged graph, the backdoor path
   `Contract <- tenure -> Churn` is detected and the minimal adjustment set is
   `{tenure}` (badge: trust).
7. Select `Contract` as treatment, `Churn` as outcome -> **4. Run estimation**
   (linear regression; the 3-level treatment rules out propensity methods).
8. **Robustness Dashboard**: all four refuters should pass with tiny deltas.
   The formal partial-R2 statistic is unavailable for this graph shape (DoWhy
   does not support effect modifiers); the manual confounder sweep covers it.
9. **5. Compare competing models**: naive vs adjusted vs confounder-stressed
   brackets the effect (-0.22 / -0.14 / -0.06, all the same sign).

## Caveats (detailed in the report)

- `Contract` is coded ordinally (0/1/2): the estimate assumes equal steps
  between tiers; binary contrasts would refine it.
- Binary outcome estimated by linear regression (linear probability model).
- Only `tenure` is adjusted for, because that is what the drawn graph implies;
  unmeasured traits (price sensitivity, satisfaction) could still confound.
  The sensitivity sweep bounds their plausible impact.
- Cross-sectional data; an A/B test of contract incentives on new cohorts would
  be the confirmatory next step.
