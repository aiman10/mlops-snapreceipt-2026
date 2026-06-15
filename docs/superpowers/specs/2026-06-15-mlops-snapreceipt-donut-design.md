# Design — MLOps deployment of the Donut receipt model

**Date:** 2026-06-15
**Author:** Aiman
**Status:** Approved design, pre-implementation
**Context:** MLOps postgraduate exam project (EHB). Reproduces the four-class course
(`geekzyn/mlops-course-2025`) but swaps the toy insurance model for a real model
from the author's own SnapReceipt project — the teacher-sanctioned "bring your own
project" bonus path.

---

## 1. Goal

Stand up a **new, self-contained MLOps project** that publishes one model from the
SnapReceipt stack — `naver-clova-ix/donut-base-finetuned-cord-v2` (Donut) — to the
cloud, following the full course maturity journey (Level 0 → 1 → 2 with continuous
delivery). The deliverable is a project that lets the author record the 20-minute
exam video explaining, for each step, *the problem and the solution*.

The exam is graded on **understanding of MLOps foundations**, not Python or the ML
algorithm. So the project must visibly demonstrate: infrastructure as code, remote
state with locking, Terraform modules, CI/CD with GitHub Actions, a manual-approval
gate, data/artifact versioning (DVC), model versioning (MLflow registry),
containerization, and a running cloud service.

## 2. Settled decisions

These three calls shape the whole design:

1. **One model only: Donut.** It is CPU-runnable (~200M params, encoder–decoder),
   the most impressive to demo (OCR-free receipt parsing, no regex), and tells the
   cleanest single-service story. The other four SnapReceipt models are explicitly
   out of scope (see §10).
2. **DVC versions the model weights.** Donut is *pretrained*, not trained in-loop,
   so there is no training dataset to version. Instead DVC tracks the ~1 GB Donut
   weight files in the S3 datastore bucket; Git holds only the small `models.dvc`
   pointer. This is a canonical use of DVC (large binary artifacts) and remains an
   honest "version your data/artifacts in S3" story.
3. **Lightweight / free-tier-ish hosting.** Serve on AWS App Runner (CPU). No GPU.
   Cost is pennies-to-a-couple-dollars per active day, not the course's "one cent" —
   mitigated by `terraform destroy` after each session.

## 3. Architecture

Two halves, same as the course:

- **Terraform side** — provisions all AWS infrastructure as code: remote backend
  (S3 + state lock), a datastore S3 bucket (DVC remote), an ECR repository, and an
  App Runner service. Driven by an infra CI/CD pipeline with a manual-approval gate.
- **Application side** — the Donut FastAPI service in `src/`, its DVC-tracked
  weights, its Dockerfile, and an app CI/CD pipeline that pulls the weights, builds
  the image, pushes to ECR, and (via App Runner auto-deploy) ships it.

The Python service is **stateless** — it loads the model bundled in its image and
serves predictions. It does not touch any database (mirrors SnapReceipt's design).

### Repository layout

New repo `mlops-snapreceipt-2026`, scaffolded in `terraform-ai-project/`, seeded
from the author's working `terraform-s3-ehb-course-03/mlops-course-2026`:

```
terraform-ai-project/
├─ terraform/
│  ├─ backends/{dev,tst,prd}.conf        # remote S3 backend config per env
│  ├─ environments/dev.tfvars            # bucket + ecr + apprunner values
│  ├─ modules/
│  │  ├─ s3-bucket/                       # reused from course
│  │  ├─ ecr-repository/                  # reused from course
│  │  └─ apprunner-service/               # reused from course (resized)
│  ├─ provider.tf
│  ├─ variables.tf
│  ├─ s3_buckets.tf
│  ├─ ecr_repositories.tf
│  └─ apprunner_services.tf
├─ src/
│  ├─ pipelines/
│  │  ├─ fetch_model.py      # one-time: download Donut weights from HF
│  │  ├─ register_model.py   # log + register Donut into MLflow registry
│  │  └─ extract.py          # Donut inference: image bytes → structured JSON
│  ├─ models/                # Donut weights — DVC-tracked, git-ignored
│  ├─ models.dvc             # small pointer Git holds
│  ├─ config.yml             # model id, task token, image size, field map
│  ├─ main.py                # orchestrator: prepare + register model
│  ├─ app.py                 # FastAPI: GET / health, POST /extract
│  ├─ requirements.txt
│  └─ Dockerfile
├─ .github/workflows/
│  ├─ tf-infra-cicd-dev.yml  # infra pipeline + manual-approval gate
│  └─ app-cicd-dev.yml       # app pipeline: dvc pull → build → push ECR
├─ docs/superpowers/specs/   # this design doc
└─ .gitignore
```

## 4. Components (each unit: purpose · interface · depends on)

- **`extract.py`** — *Purpose:* run Donut on one image and return structured fields.
  *Interface:* `extract(image_bytes) -> dict{merchant, date, total, tax, items[]}`.
  *Depends on:* transformers, torch, Pillow, the local weights in `models/`.
  Primes Donut with `<s_cord-v2>`, decodes with `token2json`, maps CORD fields to
  SnapReceipt's schema. Defaults a missing date to today (SnapReceipt behavior).
- **`fetch_model.py`** — *Purpose:* one-time download of Donut weights from Hugging
  Face into `models/` so they can be DVC-tracked. *Interface:* CLI, run once.
  *Depends on:* transformers/huggingface_hub.
- **`register_model.py`** — *Purpose:* register the pretrained Donut into the MLflow
  Model Registry as `donut_receipt_extractor`. *Interface:* called by `main.py`.
  *Depends on:* mlflow. Logs model id + config as params; registers a model version.
- **`main.py`** — *Purpose:* orchestrator. Ensures weights are present (DVC pull or
  fetch), then registers the model. *Interface:* `python main.py`.
- **`app.py`** — *Purpose:* serve the model. *Interface:* `GET /` → `{"status":"ok"}`;
  `POST /extract` (image upload) → extracted JSON. *Depends on:* fastapi, uvicorn,
  `extract.py`. Loads the model once at startup from the bundled `models/`.
- **`Dockerfile`** — *Purpose:* package interpreter + deps + weights + app into one
  image. Bundles `models/` so the runtime has no S3 dependency. EXPOSE 80,
  `uvicorn app:app --host 0.0.0.0 --port 80`.

## 5. DVC + MLflow strategy

**DVC (artifact versioning):**
- One-time bootstrap: `fetch_model.py` downloads weights → `dvc add models/` →
  `dvc push` to the S3 datastore → commit `models.dvc` + `git tag v1`.
- The app CI/CD pipeline runs `dvc pull` to materialize the exact weight version
  before building the image. A new weights version = new tag = new image.

**MLflow (model registry / versioning):**
- Runs locally for the course (`mlflow ui`, `http://127.0.0.1:5000`).
- `register_model.py` does `set_experiment` → `start_run` → `log_params` (model id,
  task token, image size) → register `donut_receipt_extractor`. Re-running bumps to
  version 2, demonstrating registry versioning.
- Per the settled decision, MLflow's role is model registry/versioning; no training
  metrics are required. (Optional bonus: log a field-extraction sanity metric.)

## 6. CI/CD pipelines (GitHub Actions)

- **Infra pipeline (`tf-infra-cicd-dev.yml`)** — triggers on PRs touching
  `terraform/**` and `workflow_dispatch`. Steps: checkout → setup Terraform →
  configure AWS creds (GitHub Secrets) → fmt → init with `backends/dev.conf` →
  validate → `plan -out=plan.tfout` → **manual-approval gate** → `apply plan.tfout`.
- **App pipeline (`app-cicd-dev.yml`)** — triggers on PRs touching `src/**` and
  `workflow_dispatch`. Steps: checkout → setup Python → install deps → configure AWS
  creds → `dvc pull` (fetch weights) → ECR login → docker build (weights bundled) →
  push image (`latest`) to ECR. App Runner auto-deploys the new image.
  *Note:* MLflow registration is **not** run in CI — a GitHub Actions runner cannot
  reach a local MLflow tracking server, so it would log to throwaway `./mlruns`. The
  MLflow registry step is demonstrated **locally** as part of Level 1. Logging from
  CI to a **deployed** MLflow server is a §11 bonus, not the baseline.

This is the project's **Continuous Delivery of the model** ("CT" reframed): because
Donut is not trained in-loop, the trigger is a weights/code change rather than new
training data, but the automated retrain-equivalent → rebuild → redeploy loop is the
same shape the course teaches.

## 7. Manual approval gate

Reuse the course's `trstringer/manual-approval@v1` pattern on the infra pipeline:
`permissions: issues: write`, `timeout-minutes: 60`, approvers = the author's GitHub
username, plan saved with `-out=plan.tfout` and applied with
`terraform apply -auto-approve plan.tfout`. Demonstrates the four-eyes principle.

## 8. Maturity-level narrative (the exam spine)

| Level | Course parallel | Donut realization |
|---|---|---|
| 0 — no MLOps | Class 1 | Donut runs by hand locally (SnapReceipt `localhost:8080`); not reproducible. The "why we don't want L0" opener. |
| 1 — automated pipeline | Class 2–3 | Versioned `src/` scripts; DVC-versioned weights in S3; MLflow-registered model; `main.py` orchestration. |
| 2 — full CI/CD | Class 3–4 | Docker → ECR → App Runner via Terraform IaC with remote backend + state lock; two GitHub Actions pipelines; manual-approval gate. |
| CT → CD-of-model | Class 4 | Weights/`src` change triggers app pipeline → rebuild → ECR → App Runner auto-deploy. |

## 9. Cost & safety

- App Runner at ~1 vCPU / 2 GB (needed for torch + Donut). Not "one cent"; budget a
  few dollars max if left running. **`terraform destroy` after each session.**
- ECR image storage ~$0.10/GB/month (trivial). torch image is multi-GB; fine.
- All S3 bucket names must be globally unique — use a personal suffix.
- Secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ECR_REPOSITORY`) live in
  GitHub Secrets; the `terraform_user` IAM machine user is reused/recreated.

## 10. Out of scope

- The other four SnapReceipt models (DeBERTa categorizer, Chronos-2 forecaster,
  MOMENT anomaly detector, Qwen2.5-3B chat). Qwen in particular needs a GPU and is
  unsuitable for free-tier hosting. **Their GPU-economics is discussed as an exam
  bonus point, not implemented.**
- Supabase, the React frontend, and the database — this project is the model-serving
  / MLOps layer only.

## 11. Bonus opportunities (teacher-listed)

- Deploy MLflow as a server (not just local) and have the pipeline log to it.
- Add data/artifact verification to the app CI/CD pipeline.
- Restrict the App Runner / security-group exposure; mention load balancer / API
  gateway for production.
- Explain how the heavy SnapReceipt models would be deployed on GPU compute
  (SageMaker endpoint, EC2-GPU, or ECS-GPU) and why the free tier cannot host them.

## 12. Assumptions / defaults

- GitHub repo name: `mlops-snapreceipt-2026`. AWS region: `eu-west-1`.
- Serve target: App Runner (ECS Fargate is the documented fallback if App Runner is
  blocked on the account).
- Weights are **bundled into the image at build time** (no runtime S3 dependency).
- A handful of sample receipt images will be used for local/manual `POST /extract`
  testing (from SnapReceipt or public CORD samples).
