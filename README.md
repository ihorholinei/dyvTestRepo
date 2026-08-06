CI/CD Pipeline Demo

A minimal FastAPI application demonstrating a complete CI/CD pipeline on GitHub Actions — from pull request to a (simulated) production deployment — using uv for Python dependency management, Docker for containerization, and GitHub Container Registry (GHCR) for image storage.

No cloud provider account is used. All deployment, smoke-test, and rollback steps are intentionally mocked (echo statements), as permitted by the assignment brief. Every other step — linting, testing, Docker builds, vulnerability scanning, and pushing images to GHCR — is real and actually executes.

Application

A small FastAPI service with two endpoints:

GET / — returns a hello-world message
GET /health — returns {"status": "ok"}, used as the target for the (mocked) post-deploy smoke test

Managed entirely with uv:

pyproject.toml — project metadata and dependencies
uv.lock — exact locked versions of every dependency (committed to the repo for reproducible installs)

Run locally:

bash
uv sync
uv run uvicorn app.main:app --reload
curl localhost:8000/health

Run tests and lint locally:

bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
Docker

The Dockerfile uses a multi-stage build:

builder stage (python:3.13-slim) — installs the official uv binary, installs dependencies via uv sync --frozen (dependency layer cached separately from application code for faster rebuilds), then installs the project itself.
Final stage (python:3.13-slim) — copies only the built /app directory from the builder stage, runs as a non-root user (appuser), and starts the app with uvicorn.
bash
docker build -t cicd-pipeline-demo:local .
docker run -p 8000:8000 cicd-pipeline-demo:local
curl localhost:8000/health
Pipeline overview
flowchart TD
    A[Pull Request opened / updated against main] --> B[pr-ci.yaml]
    B --> B1[lint-test: ruff check, ruff format --check, pytest]
    B1 --> B2[build-scan-push: docker build, Trivy scan, push to ghcr.io tagged pr-N and sha-X]
    B2 --> C[Merge PR into main]
    C --> D[main-deploy.yaml]
    D --> D1[build-and-push: rebuild, push ghcr.io tagged dev and sha-X]
    D1 --> D2["deploy-dev (mocked) — GitHub Environment: dev"]
    D2 --> E[Create + publish a GitHub Release, e.g. v0.1.0]
    E --> F[release-prod.yaml]
    F --> F1[build-and-push: rebuild, push ghcr.io tagged with the release tag]
    F1 --> F2["deploy-prod (mocked) — GitHub Environment: prod, requires manual approval"]
    F2 --> F3[smoke-test (mocked): simulated GET /health check]
    F3 -. on failure only .-> F4[rollback (mocked)]

There are three separate GitHub Actions workflows, each with its own trigger, living in .github/workflows/:

1. pr-ci.yaml — Pull Request CI

Trigger: pull_request against main (opened, synchronize, reopened).

Step	Real or mocked
Checkout code	Real
Install uv, uv sync --frozen	Real
Lint (ruff check) / format check (ruff format --check)	Real
Unit tests (pytest)	Real
Docker build	Real
Security scan (Trivy)	Real, non-blocking (exit-code: 0)
Push image to ghcr.io, tagged pr-<number> and sha-<commit>	Real

The job is split in two: lint-test runs first, and build-scan-push only runs if lint-test passes (needs: lint-test) — there's no point building an image for code that doesn't even pass linting or tests. The image is built locally first, scanned, and only pushed to GHCR after the scan completes — the exact artifact that gets pushed is the one that was scanned, never an unscanned build.

2. main-deploy.yaml — Dev deployment

Trigger: push to main (i.e. after a PR is merged).

Step	Real or mocked
Docker build + push to ghcr.io, tagged dev and sha-<short-sha>	Real
Deploy to dev environment	Mocked — echo "Deploying image:<tag> to dev environment"

Runs under the dev GitHub Environment (auto-created on first run, no protection rules — dev deployments are meant to be fast and automatic).

3. release-prod.yaml — Production release

Trigger: release event, published (a GitHub Release with a version tag, e.g. v0.1.0).

Step	Real or mocked
Docker build + push to ghcr.io, tagged with the release version	Real
Deploy to prod	Mocked — echo "Deploying image:<tag> to prd environment"
Approval gate before deploy	Real — GitHub Environment prod protection rule (required reviewer)
Post-deploy smoke test	Mocked — simulated GET /health check
Rollback	Mocked, runs only if: failure() on deploy or smoke-test

The deploy-prod job references the prod GitHub Environment, which has a required reviewer protection rule configured in repo Settings → Environments. When the workflow reaches this job, it pauses with a "Waiting" status until a reviewer manually clicks Review deployments → Approve. This is the real-world equivalent of a production release gate — nothing reaches "prod" without a human sign-off, and this was verified working end-to-end (the workflow visibly paused and required manual approval before continuing).

The rollback job deliberately does not use the prod Environment gate — during an actual incident, recovery shouldn't be blocked behind the same approval gate as a routine deploy.

What's real vs. what's mocked, and why

Real: dependency installation, linting, unit tests, Docker image builds, Trivy vulnerability scanning, pushing images to GHCR, and the GitHub Environment approval gate for production. These all run on GitHub's free-tier hosted runners with no external cost or credentials.

Mocked: the actual deployment commands (dev and prod) and the post-deploy smoke test / rollback. The assignment explicitly requires no cloud provider account, so these steps are represented as echo statements that describe exactly what a real deployment would do. In a real environment, the mocked deploy-dev / deploy-prod steps would be replaced with something like aws eks update-kubeconfig && kubectl apply -f ... or helm upgrade, authenticated via OIDC federation between GitHub Actions and the cloud provider (no long-lived credentials needed) rather than static secrets.

Testing a change via Pull Request
Create a branch: git checkout -b my-change
Make a change, commit, and push: git push -u origin my-change
Open a PR against main on GitHub.
Watch the Checks tab on the PR — pr-ci.yaml runs lint, tests, builds the image, scans it, and pushes it to GHCR tagged with the PR number.
Pushing additional commits to the same branch re-triggers the workflow (synchronize event) and updates the same PR.
Triggering a release to production
Merge your PR into main — this triggers main-deploy.yaml, which deploys (mocked) to the dev environment automatically.
Go to Releases → Draft a new release.
Choose/create a tag, e.g. v0.1.0.
Click Publish release (not "Save draft" — drafts don't trigger the workflow).
This triggers release-prod.yaml. Watch it in the Actions tab: build-and-push runs automatically, then deploy-prod pauses and waits for approval under the prod Environment. Approve it via Review deployments, and the pipeline continues to smoke-test.
Assumptions and trade-offs
No cloud account, no real infrastructure. All deployment/smoke-test/rollback logic is mocked via echo, per the assignment constraints. The pipeline structure (triggers, environments, gating, tagging) is what's being demonstrated, not an actual running service.
Rebuild at every stage rather than "build once, promote." A stricter approach would reuse the exact image built and scanned during the PR at every later stage. This wasn't done because GitHub's default merge strategies (squash/rebase) produce a new commit SHA on main that doesn't match the PR head SHA, making a clean "promote by SHA" mapping unreliable without extra bookkeeping. Since dependencies are locked via uv.lock, rebuilding still produces a functionally identical image.
Trivy scan is non-blocking (exit-code: 0). Base OS images almost always carry some low/medium CVEs unrelated to application code; failing the whole pipeline on those would be noisy for a demo project. In a real production setup, this would be tuned to fail on CRITICAL severity findings in application-layer dependencies.
prod Environment allows self-review. Since this is a solo-maintained repository, "Prevent self-review" is left off so the same person who cuts a release can also approve its deployment. In a team setting, this would be turned on.
Branch protection on main (requiring the pr-ci.yaml checks to pass before merge) is recommended and was configured manually in repo Settings — it isn't expressible inside a workflow YAML file itself.
GHCR authentication uses the automatically generated GITHUB_TOKEN with packages: write permission — no additional secrets were created or stored.