# aitiolin P0 implementation package

**Target repository:** `AGrosserHH/CausalitySection`  
**Reviewed upstream revision:** `0a6ae13dddbe018aec8b9ef6ce4e903699c38c25`  
**Proposed application version:** `0.1.0-prototype.1`  
**Scope:** incremental source update for private experimentation, not a production release.

This package contains implemented backend/frontend changes, a version-checked installer, regression tests, CI and a revised public-page HTML file. It has **not** been pushed to GitHub, deployed, or applied to your existing database.

## What changes

| P0 | Implementation |
|---|---|
| Guided samples | Allowlisted Churn and World Bank presets load into separate, owned graph records. Sample hashes are checked, source CSVs are copied, roles and a reviewable hypothesis graph are supplied, and a short guide leads to estimation, diagnostics and model comparison. No account, network dataset fetch or LLM request is needed to load a sample. |
| Run bundles | The API records analysis-stage snapshots, active graph nodes/edges/evidence, cleaning history, data hashes, query/configuration, seeds, source/dependency versions and responses. Export JSON or ZIP without attaching CSV files or row previews. Matching earlier stages are included; later edits do not overwrite the recorded snapshot. |
| Privacy and deletion | A random session bearer key, graph ownership checks on existing routes, private image delivery, reviewed one-use LLM payload approvals, metadata-only prompts, explicit server-side storage descriptions, retention controls, session deletion and a purge command. |
| Evidence first | The dashboard leads with assumptions, estimator results, individual refutations, an accessible sensitivity chart/table and provenance-matched model comparison. The composite score is in a closed disclosure. |
| CI and release hygiene | Backend tests and migration checks, frontend lint/tests/build, terminology/version/runtime-file checks, a VERSION file, changelog, and a test-gated draft-prerelease workflow. |

The website keeps the existing stylesheet, main section order, image references and two compact example cards. It adds a small local-demo guide and removes the illustrative “82 / 100” hero score. The app keeps its existing canvas, agent, controls and panel order, with one compact workspace panel added below the header.

## Package contents

- `apply_p0.py`: verifies the original file hashes and integration anchors, backs up original files, and applies the source overlay.
- `overlay/`: new source files and the replacement evidence dashboard. Most modifications to existing files are performed by the installer rather than supplied as whole-file replacements.
- `tests/`: locally runnable helper, installer, RNG, terminology and JavaScript contract tests.
- `website/index.html`: complete updated public-page HTML. This is **not** the Vue application's `index.html`.
- `website/p0-guidance-snippet.html`: just the compact guide for a Webstudio HTML embed.
- `VALIDATION.md`: exact local validation status and remaining checks.
- `validation/`: test logs and static-check results.

**Do not copy `overlay/` alone.** It needs the installer’s changes to settings, URLs, API calls, AppRoot, provider calls, tests and package versions.

## Apply to an existing checkout

Start with a clean working tree on a new local branch. Stop the running frontend and backend. Back up your SQLite database, uploaded/cleaned media and `.env` separately; the installer backs up source files, not runtime data.

Run these commands from the unpacked package, with the actual path to your repository:

```sh
python apply_p0.py --repo /path/to/CausalitySection --check
python apply_p0.py --repo /path/to/CausalitySection
```

The preflight refuses any touched file that differs from the inspected baseline, any unexpected existing overlay file, or an integration anchor that no longer matches. Windows CRLF line endings are normalized for the baseline check. Do not bypass a mismatch: rebase the changes against your version instead of overwriting local edits.

If you need a separate checkout of the inspected revision, use a new Git worktree rather than resetting your existing branch. The installer does not perform Git operations or discard changes.

## Install, migrate and verify

Use the existing project virtual environment, or create a separate Python 3.11 environment for this update. With that environment activated, from the repository root:

```sh
python -m pip install -r aitiolin/causalproject/requirements.txt
python scripts/check_prototype_language.py
python scripts/check_aitiolin_version.py
python scripts/check_release_contents.py

cd aitiolin/causalproject
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test causal_app p0 --noinput
```

Then, from a second terminal at the repository root:

```sh
cd aitiolin/causal-frontend
npm ci
npm run lint
npm test
npm run build
```

**The full Django/DoWhy suite and Vue build were not executed in the delivery environment.** The included tests and CI must pass in your checkout before merging or using the update. See `VALIDATION.md` for what actually passed locally.

To start the private prototype after those checks:

```sh
# Backend terminal, from aitiolin/causalproject:
python manage.py runserver 127.0.0.1:8000

# Frontend terminal, from aitiolin/causal-frontend:
npm run dev -- --host 127.0.0.1
```

The frontend keeps using the existing `/api` proxy. This update does not create a hosted service on aitiolin.io. Prefer localhost until you have separately reviewed deployment security.

## Use the new controls

In the application, choose **Try a sample → Load guided example**. Review the preset graph and limitations, acknowledge that review, estimate, run diagnostics and compare alternative graphs. No cleaning transform or external AI request is performed simply by loading a sample. The World Bank example deliberately starts in its original units; log transformations remain an explicit cleaning choice.

Open **Reproducibility exports** after running your analysis. Choose the latest completed stage to include preceding stages with the same graph structure, dataset hashes, query and seed. Exports record what happened; they do not silently rerun a model or bundle input data.

Open **What leaves this machine?** to inspect storage and external-request behavior. LLM assistance starts off. Once enabled, each outgoing request opens a preview of the exact model/messages/settings before transmission. Canceling sends no completion request. The backend binds approval to a session, operation and payload hash, with one use and a two-minute expiry.

The OpenAI completion client is explicitly pointed at `https://api.openai.com/v1`. This patch does not enable arbitrary third-party OpenAI-compatible base URLs. `store=false` is requested; that is **not** a zero-retention guarantee. The app does not attach CSV rows or statistical profiles, but names and supplied context can still be sensitive.

## Retention, deletion and migration behavior

Default access expiry is 24 hours, with controls to shorten the remaining period. Set `P0_RETENTION_HOURS` in the backend environment to change the default, subject to the implemented bounds. Other controls are `P0_MAX_UPLOAD_BYTES` (default 10 MiB), `P0_MAX_GRAPHS` (default 10 per workspace) and `P0_MAX_ACTIVE_WORKSPACES` (default 500 unexpired sessions server-wide).

**Physical expiry cleanup requires a scheduler.** Arrange for your local scheduler, cron or Windows Task Scheduler to run this in the backend virtual environment:

```sh
python manage.py purge_p0_sessions
```

For example, schedule it hourly with its working directory set to `aitiolin/causalproject`. The command skips active reservations; it does not kill an analysis. Expired sessions lose API access even before a scheduled physical purge runs.

**Delete session data** removes owned graphs, uploads, tracked intermediate/final cleaned copies, graph images, run records and pending approvals. It does not remove source demo CSVs, downloaded bundles, host logs/backups, provider records or unrelated browser storage. A file-removal failure leaves the session locked and returns an error so deletion can be retried; it does not claim success.

A crashed worker can leave a reservation set. Stop **all** application workers before using the explicit recovery command:

```sh
python manage.py recover_p0_locks --workers-stopped
python manage.py purge_p0_sessions
```

Never run lock recovery while an application request can still write files.

Existing graphs created before this patch have no P0 owner. The migration intentionally **does not assign those graphs to the first visitor**. They remain in the database but are inaccessible through the newly protected API. Keep their backup and re-upload required datasets into a new workspace. Legacy uploads and logs are not automatically deleted by this migration or claimed to be covered by a new session's deletion action.

The session bearer token is saved in that browser tab's sessionStorage. It is not an account; losing it loses API access to that workspace until expiry/deletion. Browser-duplicated tabs may copy sessionStorage and share the same workspace. Browser storage failure or disabled storage should be resolved before uploading data.

## Website / Webstudio

Use `website/index.html` as the revised public homepage source, or the snippet for the compact local-demo guide. Preserve the existing image files and `impressum.html`, `privacy.html` and `disclaimer.html` from your site; they are **not** included or replaced here. The HTML points visitors to local setup rather than an invented live-demo URL.

Only publish the new homepage wording after applying and checking the corresponding app update. Importing the static HTML does not install Django/Vue features. The installer also places a copy under `aitiolin/website/index.html` so CI can check its terminology; it does not deploy that copy.

## Reproducibility scope and remaining limitations

This is a provenance implementation, not a complete executable replay engine. It stores seeds and versions and seeds/restores Python random and NumPy's legacy RNG around API execution. Some library-specific generators retain their own defaults, LLM outputs are not deterministic, and numeric results may vary between environments. A seed alone is not a reproducibility guarantee.

The run bundle includes dataset hashes rather than files. Reproduction requires the matching source data, cleaning operations and dependency environment. Stage association is explicit, includes earlier stages only, and never mixes records with changed data/graphs/queries/seeds. Choosing a stage before diagnostics have run produces a bundle without those later diagnostics.

These changes do not validate causal assumptions, repair every estimator, change the existing categorical-encoding strategy, add full missing-data modeling, or turn a fallback difference of means into an identified causal estimate. Source diagnostics and example caveats still apply.

Session isolation here is not a comprehensive public-hosting security design. There is no user account recovery, organisation permissions, broad abuse-rate limiter, quotas across all anonymous sessions, TLS termination, malware scanner, or full secret scanner. Do not configure a reverse proxy/CDN to serve MEDIA_ROOT publicly. The existing dependency versions are largely retained; assess and update them separately before any deployment beyond private experimentation.

## CI and draft releases

After committing the changes in your branch, the new workflow runs on pull requests and pushes. It checks backend code/migrations/tests and frontend lint/tests/build. Positive rollout/production/compliance-guarantee wording is flagged while appropriate negative disclaimers remain allowed. Tracked runtime files such as `.env`, SQLite databases and uploaded media are rejected by a separate release-content check.

`aitiolin/VERSION` is the version source. Keep it aligned with the frontend package and lockfile, and maintain the changelog. After all checks pass, a matching `aitiolin-v0.1.0-prototype.1` tag triggers a **draft prerelease**, not automatic public publication. The workflow records the tested Python dependency environment as a CI artifact.

No tag, release, GitHub push or deployment has been created by preparing this package.
