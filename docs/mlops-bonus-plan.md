# SnapReceipt MLOps — Bonus / Extra-Points Implementation Plan

> **Build-later plan.** No cloud changes are made by reading this. Execute phase-by-phase when ready.
> Steps use checkbox (`- [ ]`) syntax. Run everything from inside `terraform-ai-project/`.

**Goal:** Extend the running Donut deployment to earn the teacher's bonus marks:
data/artifact verification in CI (A), a hosted MLflow server logged to from CI (B),
metric-gated deployment on real labelled data (C), continuous monitoring (D), and
champion/challenger model selection (E).

**Architecture:** The pretrained Donut model has no training loop, so "retraining on
metrics" is reframed as **continuous evaluation + metric-gated promotion**, and "pick the
best model" as **champion/challenger selection**. Real metrics come from the
`naver-clova-ix/cord-v2` **test split**, which ships ground-truth `gt_parse` JSON. That same
labelled set becomes a second DVC-tracked artifact (the eval dataset).

**Tech stack:** Terraform (AWS ~>6.0), GitHub Actions, MLflow, DVC+S3, EC2 (MLflow server),
CloudWatch, FastAPI/Donut (existing), pytest.

**Constants:** account `863745572691` · region `eu-west-1` · datastore `mlops-snapreceipt-datastore-2660`
· ECR `dev-mlops-snapreceipt-repository` · App Runner `mlops-snapreceipt-app` · approver `aiman10`
· venv python `src\.venv\Scripts\python.exe`.

> ⚠️ Each phase that touches AWS adds cost (EC2 for MLflow ~ $15/mo if left on; RDS more).
> Tear down with the per-resource `terraform destroy -target=...` after each session.

---

## Phase A — Data & model verification in the app CI/CD pipeline (#4)

*Lowest effort, do first. We already have 12 unit tests; this wires verification in before the build.*

### Task A1: Add a model-smoke test (real load + schema assertion)

**Files:**
- Create: `src/tests/test_model_smoke.py`
- Modify: `src/pyproject.toml` (new — registers the `slow` marker)

- [ ] **Step 1: Write the smoke test**

```python
# src/tests/test_model_smoke.py
"""Heavy smoke test: load the real Donut weights and assert /extract's output schema.
Marked `slow` so the fast unit suite can skip it. Requires models/donut present (dvc pull)."""
import io

import pytest
from PIL import Image, ImageDraw

pytestmark = pytest.mark.slow


def _make_receipt() -> bytes:
    img = Image.new("RGB", (480, 400), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(["CAFE", "Coffee  2  5.00", "Total  11.45"]):
        d.text((30, 30 + i * 45), line, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_extract_returns_valid_schema():
    from extract import extract

    result = extract(_make_receipt())
    assert set(result) >= {"merchant_name", "date", "total_amount", "tax", "items"}
    assert isinstance(result["items"], list)
    assert isinstance(result["total_amount"], (int, float))
```

- [ ] **Step 2: Register the `slow` marker** (so `-m "not slow"` works and there's no warning)

```toml
# src/pyproject.toml
[tool.pytest.ini_options]
markers = [
    "slow: tests that load the real model (need models/ via dvc pull)",
]
```

- [ ] **Step 3: Run the fast suite (smoke excluded) — must still pass**

Run: `cd src && .\.venv\Scripts\python.exe -m pytest -m "not slow" -q`
Expected: `12 passed`

- [ ] **Step 4: Run the smoke test locally (weights already present)**

Run: `cd src && .\.venv\Scripts\python.exe -m pytest -m slow -q`
Expected: `1 passed` (takes ~10–20s; loads the model)

- [ ] **Step 5: Commit**

```bash
git add src/tests/test_model_smoke.py src/pyproject.toml
git commit -m "test: model-smoke test asserting /extract schema (slow marker)"
```

### Task A2: Add verification steps to the app pipeline before the build

**Files:**
- Modify: `.github/workflows/app-cicd-dev.yml`

- [ ] **Step 1: Insert verification steps after `dvc pull`, before ECR login**

```yaml
      - name: Verify DVC artifact integrity
        run: dvc status -c

      - name: Install test dependencies
        run: pip install -r requirements.txt

      - name: Run unit tests (fast)
        run: python -m pytest -m "not slow" -q

      - name: Run model-smoke test (real weights)
        run: python -m pytest -m slow -q
```

> Note: `pip install -r requirements.txt` pulls torch on the runner (heavy but fine on
> GitHub-hosted runners). If you want a faster pipeline, install `requirements-serve.txt`
> plus CPU torch instead, or drop the model-smoke step and keep only the fast tests.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/app-cicd-dev.yml
git commit -m "ci(app): verify DVC integrity + run tests before build"
```

- [ ] **Step 3: Demonstrate** — open a PR touching `src/**`; the pipeline now blocks the build
      if tests or `dvc status` fail. Talking point: *"verification gate before packaging."*

---

## Phase B — MLflow tracking server on AWS (#1)

*Hosts MLflow so CI (not just your laptop) can log to it and you can watch experiments live.
Primary path: EC2 + SQLite backend + S3 artifact store (simple, cheap, demonstrable).
Advanced variant noted at the end (ECS/Fargate + RDS Postgres).*

### Task B1: Terraform module for the MLflow EC2 server

**Files:**
- Create: `terraform/modules/mlflow-server/variables.tf`
- Create: `terraform/modules/mlflow-server/main.tf`
- Create: `terraform/modules/mlflow-server/outputs.tf`
- Create: `terraform/mlflow_server.tf`
- Modify: `terraform/variables.tf`, `terraform/environments/dev.tfvars`

- [ ] **Step 1: Module variables**

```hcl
# terraform/modules/mlflow-server/variables.tf
variable "name" { type = string }
variable "artifact_bucket" { type = string }
variable "instance_type" { type = string, default = "t3.small" }
variable "allowed_cidr" {
  type        = string
  description = "Your public IP in CIDR form, e.g. 1.2.3.4/32"
}
variable "tags" { type = map(string), default = {} }
```

- [ ] **Step 2: Module resources** (IAM for S3, SG locked to your IP, user-data runs MLflow)

```hcl
# terraform/modules/mlflow-server/main.tf
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_iam_role" "mlflow" {
  name = "${var.name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "mlflow_s3" {
  name = "${var.name}-s3"
  role = aws_iam_role.mlflow.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
      Resource = [
        "arn:aws:s3:::${var.artifact_bucket}",
        "arn:aws:s3:::${var.artifact_bucket}/mlflow/*"
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "mlflow" {
  name = "${var.name}-profile"
  role = aws_iam_role.mlflow.name
}

resource "aws_security_group" "mlflow" {
  name        = "${var.name}-sg"
  description = "MLflow UI access from a single IP"
  ingress {
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

resource "aws_instance" "mlflow" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.mlflow.name
  vpc_security_group_ids = [aws_security_group.mlflow.id]

  user_data = <<-EOF
    #!/bin/bash
    set -e
    dnf install -y python3.11 python3.11-pip
    pip3.11 install "mlflow==3.13.0" boto3
    cat >/etc/systemd/system/mlflow.service <<'UNIT'
    [Unit]
    Description=MLflow Tracking Server
    After=network.target
    [Service]
    ExecStart=/usr/local/bin/mlflow server --host 0.0.0.0 --port 5000 \
      --backend-store-uri sqlite:////home/ec2-user/mlflow.db \
      --default-artifact-root s3://${var.artifact_bucket}/mlflow
    Restart=always
    User=ec2-user
    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl daemon-reload
    systemctl enable --now mlflow
  EOF

  tags = merge(var.tags, { Name = var.name })
}
```

- [ ] **Step 3: Module outputs**

```hcl
# terraform/modules/mlflow-server/outputs.tf
output "tracking_uri" {
  value = "http://${aws_instance.mlflow.public_dns}:5000"
}
```

- [ ] **Step 4: Root wiring + a variable for your IP**

```hcl
# terraform/mlflow_server.tf
module "mlflow_server" {
  source = "./modules/mlflow-server"
  count  = var.enable_mlflow_server ? 1 : 0

  name            = "mlops-snapreceipt-mlflow"
  artifact_bucket = "mlops-snapreceipt-datastore-2660"
  allowed_cidr    = var.my_ip_cidr
  tags            = {}
}

output "mlflow_tracking_uri" {
  value = var.enable_mlflow_server ? module.mlflow_server[0].tracking_uri : ""
}
```

```hcl
# append to terraform/variables.tf
variable "enable_mlflow_server" {
  type    = bool
  default = false
}
variable "my_ip_cidr" {
  type    = string
  default = "0.0.0.0/32"
}
```

- [ ] **Step 5: Enable in dev.tfvars** (set your real IP — find it with `curl ifconfig.me`)

```hcl
# append to terraform/environments/dev.tfvars
enable_mlflow_server = true
my_ip_cidr           = "YOUR.PUBLIC.IP.HERE/32"
```

- [ ] **Step 6: Apply and capture the URI**

```bash
cd terraform
terraform plan  -var-file="environments/dev.tfvars"   # ~4 to add (instance, role, sg, profile)
terraform apply -var-file="environments/dev.tfvars"
terraform output mlflow_tracking_uri                   # e.g. http://ec2-x-x.eu-west-1.compute.amazonaws.com:5000
cd ..
```

- [ ] **Step 7: Verify the UI loads** — open the printed URL in a browser (wait ~2 min for
      user-data). Commit the infra.

```bash
git add terraform/modules/mlflow-server terraform/mlflow_server.tf terraform/variables.tf terraform/environments/dev.tfvars
git commit -m "feat(infra): MLflow tracking server on EC2 (S3 artifacts)"
```

### Task B2: Log to the server from `main.py` and from CI

**Files:**
- Modify: `src/main.py` (read `MLFLOW_TRACKING_URI` from env)
- Modify: `.github/workflows/app-cicd-dev.yml` (registration step) OR a new workflow

- [ ] **Step 1: Make `main.py` honor a remote tracking URI**

Add near the top of `main()` in `src/main.py`, before `mlflow.set_experiment(...)`:

```python
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
```
(and add `import os` at the top.)

- [ ] **Step 2: Add the GitHub secret/variable** — in repo Settings → Secrets and variables →
      Actions, add a **variable** `MLFLOW_TRACKING_URI` = the URL from B1 Step 6.

- [ ] **Step 3: Add a registration job** to `app-cicd-dev.yml` after the tests, before build:

```yaml
      - name: Register model in remote MLflow
        env:
          MLFLOW_TRACKING_URI: ${{ vars.MLFLOW_TRACKING_URI }}
        run: python main.py
```

- [ ] **Step 4: Demonstrate** — push a `src/**` PR; confirm a new run + model version appears
      in the hosted MLflow UI. Talking point: *"MLflow is now part of CI, not just local."*

```bash
git add src/main.py .github/workflows/app-cicd-dev.yml
git commit -m "feat: log model registration to the hosted MLflow server from CI"
```

> **Advanced variant (more marks, more effort):** replace EC2+SQLite with **ECS Fargate +
> RDS Postgres** (`--backend-store-uri postgresql://...`) and an App Runner/ALB front. Needs a
> VPC connector for App Runner→RDS or an ALB for Fargate. Mention this as the production-grade
> design even if you ship the EC2 version.

---

## Phase C — Evaluation harness + metric-gated deploy (#2 reframed)

*Run Donut on labelled CORD-v2 receipts, score it, log to MLflow (B), and block the deploy if
the score is below threshold (or worse than the live version).*

### Task C1: Build & DVC-track the eval dataset from CORD-v2

**Files:**
- Create: `src/pipelines/build_eval_set.py`
- Output: `src/eval_data/*.png` + `*.json` (DVC-tracked)

- [ ] **Step 1: Add `datasets` to dev deps** — append `datasets` to `src/requirements.txt`,
      then `cd src && .\.venv\Scripts\python.exe -m pip install datasets`.

- [ ] **Step 2: Write the prep script** (downloads N test samples, flattens ground truth)

```python
# src/pipelines/build_eval_set.py
"""Download N labelled CORD-v2 test receipts into src/eval_data as image+gt JSON pairs."""
import json
import os

from datasets import load_dataset

OUT = "eval_data"
N = 30


def _flatten(gt_parse: dict) -> dict:
    menu = gt_parse.get("menu", [])
    if isinstance(menu, dict):
        menu = [menu]
    items = [{"description": m.get("nm", ""), "price": m.get("price")} for m in menu if isinstance(m, dict)]
    total = (gt_parse.get("total") or {}).get("total_price")
    return {"total": total, "items": items}


def main():
    os.makedirs(OUT, exist_ok=True)
    ds = load_dataset("naver-clova-ix/cord-v2", split=f"test[:{N}]")
    for i, row in enumerate(ds):
        row["image"].convert("RGB").save(os.path.join(OUT, f"{i:03d}.png"))
        gt = json.loads(row["ground_truth"])["gt_parse"]
        with open(os.path.join(OUT, f"{i:03d}.json"), "w") as f:
            json.dump(_flatten(gt), f)
    print(f"Wrote {N} samples to {OUT}/")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Generate + DVC-track + push the eval set**

```bash
cd src
.\.venv\Scripts\python.exe -m pipelines.build_eval_set
dvc add eval_data
git add eval_data.dvc .gitignore
git commit -m "feat(data): DVC-track CORD-v2 eval dataset"
git tag -a "eval-v1" -m "30 labelled CORD test receipts"
dvc push
cd ..
```

### Task C2: Evaluation metric (TDD)

**Files:**
- Create: `src/pipelines/evaluate.py`
- Create: `src/tests/test_evaluate.py`

- [ ] **Step 1: Write the failing test for the pure scoring function**

```python
# src/tests/test_evaluate.py
from pipelines.evaluate import field_score


def test_perfect_match_scores_one():
    pred = {"total_amount": 11.45, "items": [{"description": "A"}, {"description": "B"}]}
    gt = {"total": "11.45", "items": [{"description": "A"}, {"description": "B"}]}
    assert field_score(pred, gt) == 1.0


def test_total_mismatch_lowers_score():
    pred = {"total_amount": 9.99, "items": []}
    gt = {"total": "11.45", "items": []}
    assert field_score(pred, gt) < 1.0
```

- [ ] **Step 2: Run it — expect ImportError / FAIL**

Run: `cd src && .\.venv\Scripts\python.exe -m pytest tests/test_evaluate.py -q`

- [ ] **Step 3: Implement `evaluate.py`**

```python
# src/pipelines/evaluate.py
"""Evaluate the deployed extraction logic against labelled CORD samples."""
import glob
import json
import os

from PIL import Image


def _money(x):
    try:
        return round(float(str(x).replace(",", "").replace("€", "").strip()), 2)
    except (ValueError, TypeError):
        return None


def field_score(pred: dict, gt: dict) -> float:
    checks = [
        _money(pred.get("total_amount")) == _money(gt.get("total")),
        abs(len(pred.get("items", [])) - len(gt.get("items", []))) <= 1,
    ]
    return sum(1 for c in checks if c) / len(checks)


def evaluate(samples_dir: str = "eval_data") -> float:
    from extract import run_inference

    scores = []
    for img_path in sorted(glob.glob(os.path.join(samples_dir, "*.png"))):
        with open(img_path.replace(".png", ".json")) as f:
            gt = json.load(f)
        pred = run_inference(Image.open(img_path).convert("RGB"))
        scores.append(field_score(pred, gt))
    return sum(scores) / len(scores) if scores else 0.0


if __name__ == "__main__":
    print(f"field_accuracy={evaluate():.4f}")
```

- [ ] **Step 4: Run tests — expect PASS**, then commit.

```bash
git add src/pipelines/evaluate.py src/tests/test_evaluate.py
git commit -m "feat(eval): CORD field-accuracy metric + tests"
```

### Task C3: Metric gate that blocks a bad deploy

**Files:**
- Create: `src/pipelines/gate.py`
- Modify: `.github/workflows/app-cicd-dev.yml`

- [ ] **Step 1: Write the gate** (logs to MLflow, exits non-zero if below threshold)

```python
# src/pipelines/gate.py
"""Evaluate, log to MLflow, and fail the pipeline if the score is below threshold."""
import os
import sys

import mlflow

from pipelines.evaluate import evaluate

THRESHOLD = float(os.environ.get("EVAL_THRESHOLD", "0.6"))


def main():
    score = evaluate("eval_data")
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("Donut Eval Gate")
        with mlflow.start_run():
            mlflow.log_metric("field_accuracy", score)
            mlflow.log_param("threshold", THRESHOLD)
    print(f"field_accuracy={score:.4f} threshold={THRESHOLD}")
    sys.exit(0 if score >= THRESHOLD else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Wire the gate into the app pipeline** — after `dvc pull` and tests, before
      ECR login, in `.github/workflows/app-cicd-dev.yml`:

```yaml
      - name: Evaluation gate (block deploy if below threshold)
        env:
          MLFLOW_TRACKING_URI: ${{ vars.MLFLOW_TRACKING_URI }}
          EVAL_THRESHOLD: "0.6"
        run: python -m pipelines.gate
```

> The `pipelines/` dir is excluded from the Docker image via `.dockerignore`, so this is a
> CI-only gate — it never ships in the container.

- [ ] **Step 3: Demonstrate** — temporarily set `EVAL_THRESHOLD: "0.99"`, open a `src/**` PR,
      watch the pipeline **fail before building** (deploy blocked). Reset to `0.6`. Talking
      point: *"metric-gated continuous delivery — only ship if it scores well enough."*

```bash
git add src/pipelines/gate.py .github/workflows/app-cicd-dev.yml
git commit -m "feat(ci): metric gate blocks deploy below field-accuracy threshold"
```

> **Beat-the-live-version variant:** instead of a static threshold, query MLflow for the last
> deployed run's `field_accuracy` and require `score >= last_deployed`. That is the literal
> "only deploy if it scores better than the current model" bonus.

---

## Phase D — Continuous monitoring (#6)

*CloudWatch alarms on the live service + prediction-quality logging + an optional daily canary.*

### Task D1: CloudWatch alarms on App Runner (Terraform)

**Files:**
- Create: `terraform/modules/apprunner-service/monitoring.tf`

- [ ] **Step 1: Add alarms keyed off App Runner's published metrics**

```hcl
# terraform/modules/apprunner-service/monitoring.tf
resource "aws_cloudwatch_metric_alarm" "http_5xx" {
  alarm_name          = "${var.name}-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5xxStatusResponses"
  namespace           = "AWS/AppRunner"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  dimensions          = { ServiceName = aws_apprunner_service.this.service_name }
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "latency" {
  alarm_name          = "${var.name}-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "RequestLatency"
  namespace           = "AWS/AppRunner"
  period              = 300
  statistic           = "Average"
  threshold           = 60000 # ms; Donut cold inference is slow, tune to taste
  dimensions          = { ServiceName = aws_apprunner_service.this.service_name }
  tags                = var.tags
}
```

- [ ] **Step 2: Apply + verify** the alarms exist; commit.

```bash
cd terraform && terraform apply -var-file="environments/dev.tfvars" && cd ..
aws cloudwatch describe-alarms --query "MetricAlarms[].AlarmName" --output text
git add terraform/modules/apprunner-service/monitoring.tf
git commit -m "feat(monitoring): CloudWatch 5xx + latency alarms on App Runner"
```

### Task D2: Prediction-quality logging (model monitoring)

**Files:**
- Modify: `src/app.py`

- [ ] **Step 1: Log a structured quality line per prediction** in `extract_receipt`, after the
      result is produced:

```python
    result = extract(image_bytes)  # existing call (wrap the existing try/except)
    logger.info(
        "prediction quality: items=%d total_zero=%s merchant_unknown=%s",
        len(result.get("items", [])),
        result.get("total_amount") in (0, 0.0, None),
        result.get("merchant_name") == "Unknown",
    )
    return result
```

- [ ] **Step 2:** In CloudWatch, add a **metric filter** on the application log group matching
      `total_zero=True` → custom metric `DonutParseFailures`, and an alarm on its rate. (Console
      or Terraform `aws_cloudwatch_log_metric_filter`.) Talking point: *"model-quality drift
      signal, not just infra health."*

- [ ] **Step 3:** Rebuild + push the image (auto-deploys), then commit.

### Task D3 (optional): Daily canary

**Files:**
- Create: `.github/workflows/canary.yml`

- [ ] **Step 1: Scheduled probe that fails loudly if the live service regresses**

```yaml
name: Daily Canary
on:
  schedule: [{ cron: "0 6 * * *" }]
  workflow_dispatch:
jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Hit /health and /extract
        run: |
          BASE=https://xmmmuwaxsu.eu-west-1.awsapprunner.com
          curl -fsS $BASE/health
          curl -fsS -X POST $BASE/extract -F "file=@samples/canary.png" | tee out.json
          python -c "import json,sys; d=json.load(open('out.json')); sys.exit(0 if 'items' in d else 1)"
```
(Commit a small `samples/canary.png` for this — it may be a real image since it is a fixed probe.)

---

## Phase E — Champion/challenger model selection (#3 reframed)

*Evaluate multiple candidate models in parallel on the holdout, pick the best by metric,
register the winner, deploy it.*

### Task E1: Parameterize the candidate model

**Files:**
- Modify: `src/config.yml` (already has `model.id`), `src/extract.py` (read an env override)

- [ ] **Step 1:** In `extract._load_config`, allow `MODEL_ID` / `MODEL_DIR` env overrides so the
      same code can evaluate different checkpoints:

```python
    cfg = yaml.safe_load(open("config.yml"))
    cfg["model"]["id"] = os.environ.get("MODEL_ID", cfg["model"]["id"])
    cfg["model"]["local_dir"] = os.environ.get("MODEL_DIR", cfg["model"]["local_dir"])
    return cfg
```
(add `import os`.) For candidates not yet local, `evaluate` can load straight from the HF id by
pointing `local_dir` at the hub id (Donut `from_pretrained` accepts either).

### Task E2: GitHub Actions matrix — evaluate candidates in parallel

**Files:**
- Create: `.github/workflows/model-select.yml`

- [ ] **Step 1: Matrix job that scores each candidate and uploads its metric**

```yaml
name: Model Selection
on: { workflow_dispatch: {} }
jobs:
  evaluate:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        candidate:
          - naver-clova-ix/donut-base-finetuned-cord-v2
          - naver-clova-ix/donut-base-finetuned-cord-v1
    defaults: { run: { working-directory: src } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: eu-west-1
      - run: dvc pull eval_data.dvc
      - name: Evaluate candidate
        env:
          MODEL_DIR: ${{ matrix.candidate }}
        run: |
          score=$(python -c "from pipelines.evaluate import evaluate; print(evaluate())")
          echo "$score" > score.txt
          echo "candidate=${{ matrix.candidate }} score=$score"
      - uses: actions/upload-artifact@v4
        with:
          name: score-${{ strategy.job-index }}
          path: src/score.txt
```

- [ ] **Step 2: Aggregation job** that downloads all scores, picks the max, and registers the
      winner in MLflow (add a second job `pick-best` with `needs: [evaluate]`, download-artifact,
      a few lines of Python to compare). Deploy the winner by setting it as `model.id` and letting
      the app pipeline rebuild.

- [ ] **Step 3: Demonstrate** — run the workflow manually; show the parallel matrix and the
      chosen champion in the MLflow UI. Talking point: *"champion/challenger selection by metric."*

```bash
git add .github/workflows/model-select.yml src/config.yml src/extract.py
git commit -m "feat(ci): champion/challenger model selection matrix"
```

---

## Teardown (run after each session)

```bash
cd terraform
# Stop the MLflow EC2 server when not demoing (biggest idle cost):
terraform destroy -target='module.mlflow_server' -var-file="environments/dev.tfvars"
# Stop App Runner:
terraform destroy -target='module.apprunner_services' -var-file="environments/dev.tfvars"
cd ..
```
Full destroy still fails on the non-empty datastore bucket — empty it first:
`aws s3 rm s3://mlops-snapreceipt-datastore-2660/ --recursive`.

---

## Recommended order & marks-per-effort

1. **A** (verification) — 30 min, immediate bonus.
2. **B + C** (MLflow server + eval-gate) — the flagship; nails three bonuses with one story.
3. **D** (monitoring) — a few hours, rounds out the "production" narrative.
4. **E** (champion/challenger) — highest effort; do last if time remains.

**Say in the video:** Donut is pretrained, so "retraining" becomes **continuous evaluation +
metric-gated promotion** and "best model" becomes **champion/challenger** — adapting the
principle to an inference-only model is itself the MLOps insight being demonstrated.
