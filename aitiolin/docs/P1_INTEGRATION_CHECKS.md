# P1 integration checks

This branch integrates the reviewed P1 comparison package into the existing aitiolin application. The preparation workflow applies four baseline-checked source edits and runs the complete backend and frontend checks before committing the wiring to this branch.

The integration workflow is restricted to `integrate-p1-20260917`; it never merges or pushes to `main`. The final pull request must contain the actual source integration edits, and its P1 backend/frontend jobs must pass before merging.

A syntax error in the delivered collider test has been corrected. The standalone numerical/helper/installer suite and native JavaScript contract suite were rerun locally; complete application results are reported by GitHub Actions, not inferred from those helper tests.

No production deployment, server migration, provider request, or release is requested by this change. The homepage and existing compact examples remain unchanged.
