# Donut MLOps Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the pretrained `naver-clova-ix/donut-base-finetuned-cord-v2` receipt model to AWS through the full course MLOps pipeline (IaC → DVC → MLflow → Docker → ECR → App Runner → CI/CD → manual approval), as the exam "bring your own project" deliverable.

**Architecture:** A new repo `mlops-snapreceipt-2026`, seeded from the author's working `terraform-s3-ehb-course-03/mlops-course-2026`. Terraform provisions a DVC datastore S3 bucket, an ECR repo, and an App Runner service. A stateless FastAPI service runs Donut and exposes `POST /extract`. DVC versions the ~1 GB weights in S3; MLflow registers the model locally. Two GitHub Actions pipelines (infra with manual-approval gate, app build-and-push) deliver changes.

**Tech Stack:** Terraform (AWS provider ~>6.0), AWS (S3, ECR, App Runner, IAM), DVC (dvc-s3), MLflow, Hugging Face transformers + torch (CPU), FastAPI + uvicorn, Docker, GitHub Actions.

**Reused constants (from the author's existing course-03 project):**
- AWS account: `863745572691` · region: `eu-west-1`
- Remote backend bucket (created outside Terraform, reused): `tf-remote-backend-ehb-2660`
- New Terraform state key: `terraform-snapreceipt-dev.tfstate`
- New DVC datastore bucket (provisioned by Terraform): `mlops-snapreceipt-datastore-2660`
- ECR repo key: `mlops-snapreceipt-repository` → actual name `dev-mlops-snapreceipt-repository`
- App Runner service key: `mlops-snapreceipt-app`
- Image URI: `863745572691.dkr.ecr.eu-west-1.amazonaws.com/dev-mlops-snapreceipt-repository:latest`
- GitHub username / approver: `aiman10`
- `COURSE03` (copy source) = `../terraform-s3-ehb-course-03/mlops-course-2026`

**Working directory for all commands:** `terraform-ai-project/` (already a git repo with the design doc committed).

> ⚠️ **Cost & safety:** App Runner at 1 vCPU / 2 GB running a torch image costs a few dollars/day, not "one cent". Run `terraform destroy --var-file='environments/dev.tfvars'` after every session.

---

## Phase 0 — Scaffold & prerequisites (Level 0 baseline)

### Task 0.1: Verify the toolchain

**Files:** none

- [ ] **Step 1: Check all tools are installed**

Run:
```bash
terraform version && aws --version && docker --version && python --version && dvc version && git --version
```
Expected: each prints a version (Terraform ≥1.9, AWS CLI v2, Docker ≥24, Python ≥3.11, DVC ≥3, Git ≥2.4). If any is missing, install it before continuing.

- [ ] **Step 2: Confirm AWS credentials work**

Run:
```bash
aws sts get-caller-identity
```
Expected: JSON showing `"Account": "863745572691"`. If it errors, run `aws configure` with the `terraform_user` access keys.

---

### Task 0.2: Seed the project skeleton from course-03

**Files:**
- Create: `terraform/` (copied), `.github/workflows/` (copied)

- [ ] **Step 1: Copy the Terraform tree and workflows**

Run (from `terraform-ai-project/`):
```bash
COURSE03="../terraform-s3-ehb-course-03/mlops-course-2026"
mkdir -p .github/workflows
cp -r "$COURSE03/terraform" ./terraform
cp "$COURSE03/.github/workflows/tf-infra-cicd-dev.yml" .github/workflows/
cp "$COURSE03/.github/workflows/app-cicd-dev.yml" .github/workflows/
# Remove copied local state / lock so we start clean
rm -rf terraform/.terraform terraform/.terraform.lock.hcl
```

- [ ] **Step 2: Verify the structure**

Run:
```bash
find terraform .github -type f | sort
```
Expected: lists `terraform/provider.tf`, `terraform/variables.tf`, `terraform/s3_buckets.tf`, `terraform/ecr_repositories.tf`, `terraform/apprunner_services.tf`, the three `modules/`, `backends/*.conf`, `environments/dev.tfvars`, and both workflow files.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: seed terraform + workflows skeleton from course-03"
```

---

### Task 0.3: Point the project at a clean backend and clean tfvars

**Files:**
- Modify: `terraform/provider.tf`
- Modify: `terraform/backends/dev.conf`

- [ ] **Step 1: Rewrite `terraform/provider.tf` to use an empty backend block**

Replace the whole file with:
```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}
```
(The empty `backend "s3" {}` takes its values from `--backend-config='backends/dev.conf'` at init time — cleaner than hardcoding.)

- [ ] **Step 2: Rewrite `terraform/backends/dev.conf` with the new state key**

Replace the whole file with:
```hcl
bucket       = "tf-remote-backend-ehb-2660"
key          = "terraform-snapreceipt-dev.tfstate"
region       = "eu-west-1"
encrypt      = true
use_lockfile = true
```
(Reuses the existing backend bucket; the distinct `key` keeps this project's state separate from course-03's — two states can coexist in one bucket.)

- [ ] **Step 3: Commit**

```bash
git add terraform/provider.tf terraform/backends/dev.conf
git commit -m "chore: point project at clean snapreceipt backend state key"
```

---

## Phase 1 — Infrastructure as code: datastore + ECR (Level 1)

### Task 1.1: Define the datastore bucket and ECR repo in dev.tfvars

**Files:**
- Modify: `terraform/environments/dev.tfvars`

- [ ] **Step 1: Replace `terraform/environments/dev.tfvars` with the SnapReceipt resources**

Replace the whole file with (note: `apprunner_services` is intentionally empty for now — we add it in Phase 3 once an image exists in ECR):
```hcl
environment = "dev"
aws_region  = "eu-west-1"

s3_buckets = [
  {
    key  = "mlops-snapreceipt-datastore-2660"
    tags = {}
  }
]

ecr_repositories = [
  {
    key                  = "mlops-snapreceipt-repository"
    image_tag_mutability = "MUTABLE"
    image_scanning_configuration = {
      scan_on_push = true
    }
    tags = {}
  }
]

apprunner_services = []
```

- [ ] **Step 2: Commit**

```bash
git add terraform/environments/dev.tfvars
git commit -m "feat(infra): define datastore bucket and ECR repo for snapreceipt"
```

---

### Task 1.2: Initialize, validate, and plan the infrastructure

**Files:** none (operates on `terraform/`)

- [ ] **Step 1: Init with the remote backend**

Run:
```bash
cd terraform
terraform init --backend-config='backends/dev.conf'
```
Expected: `Successfully configured the backend "s3"!` and `Terraform has been successfully initialized!`

- [ ] **Step 2: Format and validate**

Run:
```bash
terraform fmt -recursive
terraform validate
```
Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Plan**

Run:
```bash
terraform plan --var-file='environments/dev.tfvars'
```
Expected: `Plan: 2 to add, 0 to change, 0 to destroy.` (the datastore S3 bucket + the ECR repo). If it shows App Runner resources, you forgot to empty `apprunner_services` — fix and re-plan.

---

### Task 1.3: Apply the infrastructure

**Files:** none

- [ ] **Step 1: Apply**

Run (still in `terraform/`):
```bash
terraform apply --var-file='environments/dev.tfvars'
```
Type `yes`. Expected: `Apply complete! Resources: 2 added.`

- [ ] **Step 2: Verify in AWS**

Run:
```bash
aws s3 ls | grep mlops-snapreceipt-datastore-2660
aws ecr describe-repositories --query "repositories[].repositoryName" --output text | tr '\t' '\n' | grep snapreceipt
```
Expected: the datastore bucket is listed, and `dev-mlops-snapreceipt-repository` is listed.

- [ ] **Step 3: Return to project root**

Run:
```bash
cd ..
```

---

## Phase 2 — The Donut model service (Level 1: versioned pipeline + DVC + MLflow)

### Task 2.1: Create the src skeleton and dependencies

**Files:**
- Create: `src/requirements.txt`
- Create: `src/.gitignore`

- [ ] **Step 1: Create `src/requirements.txt`**

```text
torch
transformers
sentencepiece
protobuf
pillow
pyyaml
python-multipart
fastapi
uvicorn
dvc-s3
mlflow
pytest
httpx
```
(`pyyaml` is imported directly by `extract.py`/`main.py`/`fetch_model.py`; list it explicitly rather than relying on the transitive dep from mlflow/dvc. `httpx` is required by FastAPI's `TestClient`; `python-multipart` by `UploadFile`.)

- [ ] **Step 2: Create `src/.gitignore`**

```text
.venv/
__pycache__/
*.pyc
/models
mlruns/
```
(`/models` is DVC-tracked; Git ignores the weights and keeps only `models.dvc`.)

- [ ] **Step 3: Create the virtual environment and install**

Run:
```bash
cd src
python -m venv .venv
source .venv/bin/activate    # Windows: .venv/Scripts/activate
pip install -r requirements.txt
```
Expected: installs complete (torch download is large — this takes a few minutes).

- [ ] **Step 4: Commit**

```bash
cd ..
git add src/requirements.txt src/.gitignore
git commit -m "feat(src): add Donut service dependencies and gitignore"
```

---

### Task 2.2: Create the config file

**Files:**
- Create: `src/config.yml`

- [ ] **Step 1: Create `src/config.yml`**

```yaml
model:
  id: "naver-clova-ix/donut-base-finetuned-cord-v2"
  task_token: "<s_cord-v2>"
  local_dir: "models/donut"
  max_length: 768
registry:
  experiment: "Donut Receipt Extraction"
  model_name: "donut_receipt_extractor"
```

- [ ] **Step 2: Commit**

```bash
git add src/config.yml
git commit -m "feat(src): add Donut config"
```

---

### Task 2.3: Implement the CORD→schema mapping (TDD)

The deterministic mapping is the unit-testable core; model inference is wrapped around it.

**Files:**
- Create: `src/extract.py`
- Test: `src/tests/test_mapping.py`

- [ ] **Step 1: Write the failing test**

Create `src/tests/test_mapping.py`:
```python
from extract import map_cord_to_schema


def test_maps_total_tax_and_items():
    cord = {
        "menu": [
            {"nm": "Coffee", "cnt": "2", "price": "5.00"},
            {"nm": "Bagel", "cnt": "1", "price": "3.00"},
        ],
        "sub_total": {"subtotal_price": "8.00", "tax_price": "0.80"},
        "total": {"total_price": "8.80"},
    }
    result = map_cord_to_schema(cord)
    assert result["total"] == 8.80
    assert result["tax"] == 0.80
    assert result["items"] == [
        {"description": "Coffee", "quantity": 2, "price": 5.00},
        {"description": "Bagel", "quantity": 1, "price": 3.00},
    ]


def test_single_item_dict_is_normalized_to_list():
    cord = {"menu": {"nm": "Water", "cnt": "1", "price": "1.50"}, "total": {"total_price": "1.50"}}
    result = map_cord_to_schema(cord)
    assert result["items"] == [{"description": "Water", "quantity": 1, "price": 1.50}]
    assert result["tax"] is None


def test_missing_fields_default_safely():
    result = map_cord_to_schema({})
    assert result["items"] == []
    assert result["total"] is None
    assert result["merchant"] == "Unknown"
    assert result["date"] is not None  # defaults to today
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd src && source .venv/bin/activate && python -m pytest tests/test_mapping.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'extract'` (or `ImportError`).

- [ ] **Step 3: Implement `src/extract.py`**

```python
import re
from datetime import date


def _to_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("€", "").strip())
    except (ValueError, TypeError):
        return None


def _to_int(value, default=1):
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def map_cord_to_schema(cord: dict) -> dict:
    """Map Donut/CORD-v2 output into the SnapReceipt schema. Pure + deterministic."""
    menu = cord.get("menu", [])
    if isinstance(menu, dict):
        menu = [menu]
    items = []
    for entry in menu:
        if not isinstance(entry, dict):
            continue
        items.append({
            "description": entry.get("nm", ""),
            "quantity": _to_int(entry.get("cnt", 1)),
            "price": _to_float(entry.get("price")),
        })

    total = _to_float((cord.get("total") or {}).get("total_price"))
    tax = _to_float((cord.get("sub_total") or {}).get("tax_price"))

    return {
        "merchant": cord.get("merchant") or "Unknown",
        "date": cord.get("date") or date.today().isoformat(),
        "total": total,
        "tax": tax,
        "items": items,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
python -m pytest tests/test_mapping.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd ..
git add src/extract.py src/tests/test_mapping.py
git commit -m "feat(src): add CORD->schema mapping with tests"
```

---

### Task 2.4: Add Donut inference to extract.py

**Files:**
- Modify: `src/extract.py`

- [ ] **Step 1: Append the model-loading and inference functions to `src/extract.py`**

Add at the end of the file:
```python
import yaml

_PROCESSOR = None
_MODEL = None
_CONFIG = None


def _load_config():
    global _CONFIG
    if _CONFIG is None:
        with open("config.yml") as f:
            _CONFIG = yaml.safe_load(f)
    return _CONFIG


def _load_model():
    global _PROCESSOR, _MODEL
    if _MODEL is None:
        import torch
        from transformers import DonutProcessor, VisionEncoderDecoderModel
        cfg = _load_config()
        path = cfg["model"]["local_dir"]
        _PROCESSOR = DonutProcessor.from_pretrained(path)
        _MODEL = VisionEncoderDecoderModel.from_pretrained(path)
        _MODEL.to("cuda" if torch.cuda.is_available() else "cpu")
        _MODEL.eval()
    return _PROCESSOR, _MODEL


def extract(image_bytes: bytes) -> dict:
    """Run Donut on a receipt image and return the SnapReceipt schema."""
    import io
    import torch
    from PIL import Image

    cfg = _load_config()
    processor, model = _load_model()
    device = next(model.parameters()).device

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pixel_values = processor(image, return_tensors="pt").pixel_values.to(device)

    task_prompt = cfg["model"]["task_token"]
    decoder_input_ids = processor.tokenizer(
        task_prompt, add_special_tokens=False, return_tensors="pt"
    ).input_ids.to(device)

    with torch.no_grad():
        outputs = model.generate(
            pixel_values,
            decoder_input_ids=decoder_input_ids,
            max_length=cfg["model"]["max_length"],
            pad_token_id=processor.tokenizer.pad_token_id,
            eos_token_id=processor.tokenizer.eos_token_id,
            use_cache=True,
            bad_words_ids=[[processor.tokenizer.unk_token_id]],
            return_dict_in_generate=True,
        )

    sequence = processor.batch_decode(outputs.sequences)[0]
    sequence = sequence.replace(processor.tokenizer.eos_token, "").replace(
        processor.tokenizer.pad_token, ""
    )
    sequence = re.sub(r"<.*?>", "", sequence, count=1).strip()
    cord = processor.token2json(sequence)
    return map_cord_to_schema(cord)
```

- [ ] **Step 2: Re-run the mapping tests to confirm nothing broke**

Run:
```bash
cd src && source .venv/bin/activate && python -m pytest tests/test_mapping.py -v
```
Expected: 3 passed (the new imports are lazy/inside functions, so the pure tests still run without torch loading a model).

- [ ] **Step 3: Commit**

```bash
cd ..
git add src/extract.py
git commit -m "feat(src): add Donut inference wrapper"
```

---

### Task 2.5: Create the FastAPI serving layer (TDD on health)

**Files:**
- Create: `src/app.py`
- Test: `src/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Create `src/tests/test_app.py`:
```python
from fastapi.testclient import TestClient
import app as app_module

client = TestClient(app_module.app)


def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"health_check": "OK"}


def test_extract_calls_model(monkeypatch):
    monkeypatch.setattr(app_module, "extract", lambda data: {"total": 8.8, "items": []})
    response = client.post("/extract", files={"file": ("r.png", b"fake-bytes", "image/png")})
    assert response.status_code == 200
    assert response.json()["total"] == 8.8
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd src && source .venv/bin/activate && python -m pytest tests/test_app.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Implement `src/app.py`**

```python
from fastapi import FastAPI, UploadFile, File
from extract import extract

app = FastAPI(title="SnapReceipt Donut Extractor")


@app.get("/")
async def root():
    return {"health_check": "OK"}


@app.post("/extract")
async def extract_receipt(file: UploadFile = File(...)):
    image_bytes = await file.read()
    return extract(image_bytes)
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
python -m pytest tests/test_app.py -v
```
Expected: 2 passed (the second test monkeypatches `extract`, so no model loads).

- [ ] **Step 5: Commit**

```bash
cd ..
git add src/app.py src/tests/test_app.py
git commit -m "feat(src): add FastAPI extract endpoint with tests"
```

---

### Task 2.6: Download the Donut weights

**Files:**
- Create: `src/pipelines/__init__.py`
- Create: `src/pipelines/fetch_model.py`

- [ ] **Step 1: Create `src/pipelines/__init__.py`** (empty file)

```python
```

- [ ] **Step 2: Create `src/pipelines/fetch_model.py`**

```python
"""One-time: download the pretrained Donut weights into models/donut for DVC tracking."""
import yaml
from transformers import DonutProcessor, VisionEncoderDecoderModel


def main():
    with open("config.yml") as f:
        cfg = yaml.safe_load(f)
    model_id = cfg["model"]["id"]
    local_dir = cfg["model"]["local_dir"]

    print(f"Downloading {model_id} -> {local_dir} ...")
    processor = DonutProcessor.from_pretrained(model_id)
    model = VisionEncoderDecoderModel.from_pretrained(model_id)
    processor.save_pretrained(local_dir)
    model.save_pretrained(local_dir)
    print("Done.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it to download the weights**

Run:
```bash
cd src && source .venv/bin/activate && python -m pipelines.fetch_model
```
Expected: `Done.` and `models/donut/` now contains `config.json`, `model.safetensors` (~800 MB+), `preprocessor_config.json`, tokenizer files.

- [ ] **Step 4: Verify the weights exist**

Run:
```bash
ls -la models/donut/
```
Expected: lists the model + processor files.

- [ ] **Step 5: Commit the script (weights are git-ignored)**

```bash
cd ..
git add src/pipelines/__init__.py src/pipelines/fetch_model.py
git commit -m "feat(src): add Donut weight download script"
```

---

### Task 2.7: Version the weights with DVC and push to S3

**Files:**
- Create: `src/.dvc/config`, `src/models.dvc` (generated by DVC)

- [ ] **Step 1: Initialize DVC inside src**

Run:
```bash
cd src
dvc init --subdir
git commit -m "chore: initialize dvc in src"
```
Expected: `Initialized DVC repository.`

- [ ] **Step 2: Configure the S3 datastore as the default remote**

Run:
```bash
dvc remote add -d storage s3://mlops-snapreceipt-datastore-2660/models
git commit .dvc/config -m "chore: configure dvc s3 remote"
```

- [ ] **Step 3: Track the weights with DVC**

Run:
```bash
dvc add models
```
Expected: produces `models.dvc` and adds `/models` to `src/.gitignore`. Prints `To track the changes with git, run: git add models.dvc .gitignore`.

- [ ] **Step 4: Commit the pointer and tag the version**

Run:
```bash
git add models.dvc .gitignore
git commit -m "feat(data): track Donut weights with DVC"
git tag -a "donut-v1" -m "base donut-base-finetuned-cord-v2 weights"
```

- [ ] **Step 5: Push the weights to S3**

Run:
```bash
dvc push
```
Expected: uploads the files to `s3://mlops-snapreceipt-datastore-2660/models`. Verify:
```bash
aws s3 ls s3://mlops-snapreceipt-datastore-2660/ --recursive | head
```
Expected: object(s) under the bucket.

- [ ] **Step 6: Return to project root**

```bash
cd ..
```

---

### Task 2.8: Register the model in MLflow (Level-1 model versioning)

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Create `src/main.py`**

```python
"""Register the pretrained Donut model into the MLflow Model Registry."""
import logging
import yaml
import mlflow
import mlflow.pyfunc

logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")


class DonutReceiptModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        from transformers import DonutProcessor, VisionEncoderDecoderModel
        path = context.artifacts["donut_dir"]
        self.processor = DonutProcessor.from_pretrained(path)
        self.model = VisionEncoderDecoderModel.from_pretrained(path)

    def predict(self, context, model_input):
        # Demonstration entry point; serving is handled by app.py/extract.py.
        return [{"loaded": True}]


def main():
    with open("config.yml") as f:
        cfg = yaml.safe_load(f)

    mlflow.set_experiment(cfg["registry"]["experiment"])
    with mlflow.start_run() as run:
        mlflow.log_params({
            "base_model": cfg["model"]["id"],
            "task_token": cfg["model"]["task_token"],
            "max_length": cfg["model"]["max_length"],
        })
        mlflow.set_tag("model_type", "vision-encoder-decoder (Donut)")
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=DonutReceiptModel(),
            artifacts={"donut_dir": cfg["model"]["local_dir"]},
        )
        model_uri = f"runs:/{run.info.run_id}/model"
        mlflow.register_model(model_uri, cfg["registry"]["model_name"])
        logging.info("Registered %s from %s", cfg["registry"]["model_name"], model_uri)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it to register version 1**

Run:
```bash
cd src && source .venv/bin/activate && python main.py
```
Expected: log line `Registered donut_receipt_extractor ...` and `Successfully registered model 'donut_receipt_extractor'. Created version '1'`.

- [ ] **Step 3: Open the MLflow UI and confirm**

Run (in a second terminal, from `src/`):
```bash
mlflow ui
```
Visit `http://127.0.0.1:5000`. Expected: experiment "Donut Receipt Extraction" with one run; "Models" tab shows `donut_receipt_extractor` version 1. Stop the UI with Ctrl+C when done.

- [ ] **Step 4: Run again to demonstrate version 2**

Run:
```bash
python main.py
```
Expected: `Created version '2'`. (Re-open the UI to show v1 and v2 side by side during the exam.)

- [ ] **Step 5: Commit**

```bash
cd ..
git add src/main.py
git commit -m "feat(src): register Donut in MLflow registry"
```

---

### Task 2.9: Package the service in Docker and test locally

**Files:**
- Create: `src/Dockerfile`
- Create: `src/.dockerignore`

- [ ] **Step 1: Create `src/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so Docker caches this layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app code, config, and the DVC-pulled model weights
COPY app.py extract.py config.yml ./
COPY models/ ./models/

EXPOSE 80
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
```

- [ ] **Step 2: Create `src/.dockerignore`**

```text
.venv/
__pycache__/
tests/
mlruns/
.dvc/
*.dvc
.dvcignore
pipelines/
```
(The weights are already in `models/` from `dvc pull`/`fetch_model`; we bundle them but exclude dev-only dirs.)

- [ ] **Step 3: Build the image**

Run:
```bash
cd src
docker build -t snapreceipt-donut:latest .
```
Expected: `Successfully tagged snapreceipt-donut:latest` (build is multi-GB and takes several minutes due to torch).

- [ ] **Step 4: Run the container**

Run:
```bash
docker run -d -p 8080:80 --name donut snapreceipt-donut:latest
sleep 20
curl http://localhost:8080/
```
Expected: `{"health_check":"OK"}`.

- [ ] **Step 5: Test extraction with a sample receipt**

Run (replace `sample.png` with any receipt image; download a CORD sample if you have none):
```bash
curl -X POST http://localhost:8080/extract -F "file=@sample.png"
```
Expected: JSON with `merchant`, `date`, `total`, `tax`, `items[]`. (First call is slow — model load + CPU inference.)

- [ ] **Step 6: Stop the container and commit**

Run:
```bash
docker rm -f donut
cd ..
git add src/Dockerfile src/.dockerignore
git commit -m "feat(src): containerize Donut service"
```

---

## Phase 3 — Cloud deploy + App Runner + app CI/CD (Level 2)

### Task 3.1: Push the project to GitHub and store the ECR secret

**Files:** none

- [ ] **Step 1: Create the GitHub repo and push**

Create a new repo `mlops-snapreceipt-2026` on github.com (Public, no README/.gitignore). Then:
```bash
git remote add origin https://github.com/aiman10/mlops-snapreceipt-2026.git
git branch -M main
git push -u origin main
```

- [ ] **Step 2: Add GitHub Secrets**

In the repo: Settings → Secrets and variables → Actions. Add:
- `AWS_ACCESS_KEY_ID` = the `terraform_user` access key id
- `AWS_SECRET_ACCESS_KEY` = the `terraform_user` secret
- `ECR_REPOSITORY` = `dev-mlops-snapreceipt-repository`

Expected: three repository secrets listed.

---

### Task 3.2: Simplify the app CI/CD workflow for an inference-only model

**Files:**
- Modify: `.github/workflows/app-cicd-dev.yml`

- [ ] **Step 1: Replace `.github/workflows/app-cicd-dev.yml`**

Replace the whole file with (removes the "Retrain model" step — Donut isn't trained; CI only needs `dvc pull` to fetch weights, then build+push. MLflow registration stays local per the spec):
```yaml
name: Application CI/CD

on:
  pull_request:
    branches: [ "main" ]
    paths:
      - 'src/**'
  workflow_dispatch:

jobs:
  pull-build-push:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: src

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install DVC
        run: pip install dvc-s3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: eu-west-1

      - name: Pull model weights with DVC
        run: dvc pull

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build, tag, and push docker image to Amazon ECR
        env:
          REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          REPOSITORY: ${{ secrets.ECR_REPOSITORY }}
          IMAGE_TAG: latest
        run: |
          docker build -t $REGISTRY/$REPOSITORY:$IMAGE_TAG .
          docker push $REGISTRY/$REPOSITORY:$IMAGE_TAG
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/app-cicd-dev.yml
git commit -m "ci: app pipeline pulls weights, builds, pushes (no in-CI training)"
git push
```

---

### Task 3.3: Build and push the first image (seed ECR before App Runner)

App Runner needs an image present in ECR before it can be created. Push once via the app pipeline.

**Files:** none

- [ ] **Step 1: Trigger the app workflow manually**

In GitHub → Actions → "Application CI/CD" → "Run workflow" on `main`. Wait for it to go green.
Expected: the run pulls weights, builds the image, pushes `:latest` to ECR.

- [ ] **Step 2: Verify the image is in ECR**

Run:
```bash
aws ecr list-images --repository-name dev-mlops-snapreceipt-repository --query "imageIds[].imageTag" --output text
```
Expected: `latest` appears.

---

### Task 3.4: Add the App Runner service and deploy

**Files:**
- Modify: `terraform/environments/dev.tfvars`

- [ ] **Step 1: Add `apprunner_services` to `terraform/environments/dev.tfvars`**

Replace the `apprunner_services = []` line with:
```hcl
apprunner_services = [
  {
    key = "mlops-snapreceipt-app"
    source_configuration = {
      image_repository = {
        image_identifier      = "863745572691.dkr.ecr.eu-west-1.amazonaws.com/dev-mlops-snapreceipt-repository:latest"
        image_repository_type = "ECR"
        image_configuration = {
          port = 80
        }
      }
      autodeployments_enabled = true
    }
    tags = {}
  }
]
```

- [ ] **Step 2: Plan and apply**

Run:
```bash
cd terraform
terraform plan --var-file='environments/dev.tfvars'
```
Expected: `Plan: 3 to add` (App Runner service + its IAM role + role policy attachment). Then:
```bash
terraform apply --var-file='environments/dev.tfvars'
```
Type `yes`. Expected: `Apply complete!` (App Runner takes a few minutes to reach RUNNING).

- [ ] **Step 3: Get the public URL**

Run:
```bash
aws apprunner list-services --query "ServiceSummaryList[?ServiceName=='mlops-snapreceipt-app'].ServiceUrl" --output text
```
Expected: a URL like `xxxxx.eu-west-1.awsapprunner.com`.

- [ ] **Step 4: Verify the cloud service**

Run (replace `<URL>`):
```bash
curl https://<URL>/
curl -X POST https://<URL>/extract -F "file=@src/sample.png"
```
Expected: health check `{"health_check":"OK"}`, then a real extraction JSON — from the cloud, not your laptop.

- [ ] **Step 5: Commit and push**

```bash
cd ..
git add terraform/environments/dev.tfvars
git commit -m "feat(infra): deploy Donut service to App Runner"
git push
```

---

## Phase 4 — Manual-approval gate on the infra pipeline (Level 2)

The infra workflow copied from course-03 already contains the `trstringer/manual-approval@v1` gate. This phase confirms and exercises it.

### Task 4.1: Confirm the approval gate config

**Files:**
- Modify (if needed): `.github/workflows/tf-infra-cicd-dev.yml`

- [ ] **Step 1: Open `.github/workflows/tf-infra-cicd-dev.yml` and verify these are present**

Confirm the file contains:
- `permissions:` block with `issues: write` (the approval action posts an issue)
- `Terraform Plan` step ending in `-out=plan.tfout`
- An `Approval` step using `trstringer/manual-approval@v1`, `timeout-minutes: 60`, `approvers: aiman10`
- `Terraform Apply` step running `terraform apply -auto-approve plan.tfout`

If `approvers:` is not `aiman10`, change it to `aiman10`. Expected: no other changes needed (this matches the course-03 working file).

- [ ] **Step 2: Commit only if you changed it**

```bash
git add .github/workflows/tf-infra-cicd-dev.yml
git commit -m "ci: confirm manual-approval gate on infra pipeline"
git push
```

---

### Task 4.2: Exercise the approval flow with a real change

**Files:**
- Modify: `terraform/environments/dev.tfvars` (temporary, harmless change)

- [ ] **Step 1: Make a small infra change on a feature branch**

Run:
```bash
git checkout -b feature/approval-demo
```
In `terraform/environments/dev.tfvars`, add a second harmless bucket to `s3_buckets`:
```hcl
s3_buckets = [
  {
    key  = "mlops-snapreceipt-datastore-2660"
    tags = {}
  },
  {
    key  = "mlops-snapreceipt-history-2660"
    tags = {}
  }
]
```

- [ ] **Step 2: Push and open a PR**

Run:
```bash
git add terraform/environments/dev.tfvars
git commit -m "demo: add history bucket to exercise approval gate"
git push -u origin feature/approval-demo
```
Open a pull request against `main` on GitHub.

- [ ] **Step 3: Watch the gate**

In Actions, the `tf-infra-cicd-dev` workflow runs: format → init → validate → plan → then **pauses at Approval**. It opens an Issue titled "Deploy Terraform Plan to dev" tagging `aiman10`.
Expected: the Apply step is blocked, waiting.

- [ ] **Step 4: Approve and confirm apply**

Comment `approved` on that issue. Expected: the workflow resumes and the Apply step runs, creating the history bucket. Verify:
```bash
aws s3 ls | grep mlops-snapreceipt-history-2660
```
Expected: the history bucket exists. Merge the PR.

- [ ] **Step 5: (Optional) Clean up the demo bucket**

Revert the history bucket from `dev.tfvars` on `main` later, or leave it for the video. Either is fine.

---

## Phase 5 — The CD-of-model loop & MLflow demo (Level 2 / "Continuous Training")

### Task 5.1: Demonstrate a weights/code change redeploying automatically

**Files:** none (process demonstration)

- [ ] **Step 1: Make a trivial src change on a branch**

Run:
```bash
git checkout main && git pull
git checkout -b feature/donut-tweak
```
Edit `src/app.py` `root()` to return a version field:
```python
@app.get("/")
async def root():
    return {"health_check": "OK", "model": "donut-v1"}
```

- [ ] **Step 2: Push, PR, and watch the app pipeline**

Run:
```bash
git add src/app.py
git commit -m "feat: add model tag to health check"
git push -u origin feature/donut-tweak
```
Open a PR. Expected: `Application CI/CD` runs (triggered by `src/**`), pulls weights, rebuilds, pushes `:latest` to ECR. Because App Runner has `autodeployments_enabled = true`, it auto-deploys the new image.

- [ ] **Step 3: Confirm the live service updated**

After the App Runner deployment finishes (a few minutes), run:
```bash
curl https://<URL>/
```
Expected: `{"health_check":"OK","model":"donut-v1"}`. Merge the PR.

This is the exam's **Continuous Delivery of the model**: a change in `src/` (or a new DVC weights version) → automatic rebuild → automatic redeploy.

---

### Task 5.2: Rehearse the MLflow versioning story

**Files:** none

- [ ] **Step 1: Show the registry locally**

Run:
```bash
cd src && source .venv/bin/activate && mlflow ui
```
Visit `http://127.0.0.1:5000` → Models → `donut_receipt_extractor`. Expected: versions 1 and 2 (from Task 2.8). For the video, narrate: "MLflow gives the model registry and versioning; each `python main.py` produces a new version." Stop with Ctrl+C.

- [ ] **Step 2: Return to root**

```bash
cd ..
```

---

## Phase 6 — Exam prep, bonus, and teardown

### Task 6.1: Tear down to control cost

**Files:** none

- [ ] **Step 1: Destroy the expensive resources (recommended: keep the cheap datastore)**

The costly resource is App Runner; S3 + ECR are pennies. Also, a **full** `terraform destroy` will FAIL on the datastore bucket because it is non-empty (the `s3-bucket` module does not set `force_destroy`) and because it holds your DVC weights. So the clean per-session teardown targets only App Runner:

Run:
```bash
cd terraform
terraform destroy -target='module.apprunner_services' --var-file='environments/dev.tfvars'
cd ..
```
Type `yes`. Expected: `Destroy complete! Resources: 3 destroyed.` (service + IAM role + attachment). The datastore bucket and your pushed weights stay, so next session is just `terraform apply` + a fresh image push — no 1 GB re-upload.

- [ ] **Step 2 (only for a FULL teardown): empty the datastore bucket first**

If you really want everything gone:
```bash
aws s3 rm s3://mlops-snapreceipt-datastore-2660/ --recursive
cd terraform
terraform destroy --var-file='environments/dev.tfvars'
cd ..
```
Type `yes`. Expected: `Destroy complete!` (you will need `dvc push` again next time).

- [ ] **Step 3: Confirm App Runner is gone**

Run:
```bash
aws apprunner list-services --query "ServiceSummaryList[].ServiceName" --output text
```
Expected: `mlops-snapreceipt-app` no longer listed.

---

### Task 6.2: Record the exam video (reference, not code)

**Files:** none

- [ ] **Step 1: Follow the 20-minute structure from the design doc §8 and the course guide Part 11.3**

Cover, with *problem → solution* for each:
1. Maturity Level 0 and why notebooks-on-a-laptop is bad (your SnapReceipt `localhost:8080` is literally L0).
2. L0 → L1 → L2 transitions, naming the tool + principle at each step.
3. Infrastructure as code (Terraform, remote backend + state lock, modules, `for_each`).
4. CI/CD (two pipelines, feature-branch/PR flow, GitHub Secrets) + manual-approval gate (four-eyes).
5. DVC versioning the Donut weights in S3 (Git holds only `models.dvc`).
6. The Donut service: OCR-free encoder→decoder, `POST /extract`, Docker, ECR, App Runner, live `curl`.
7. MLflow registry + versioning (v1/v2).
8. CD-of-model loop (src/weights change → rebuild → redeploy).
9. **Bonus:** explain why the other four SnapReceipt models (esp. Qwen 3B) need GPU compute (SageMaker/EC2-GPU) and can't run on this free-tier path — the GPU-economics discussion the teacher rewards.

---

## Self-review notes

- **Spec coverage:** §3 repo layout → Tasks 0.2–2.9; §4 components → Tasks 2.3–2.9; §5 DVC/MLflow → Tasks 2.7–2.8; §6 pipelines → Tasks 3.2, 4.1; §7 approval → Phase 4; §8 maturity narrative → Task 6.2; §9 cost/destroy → Task 6.1; §10 out-of-scope/§11 bonus → Task 6.2 step 9. All covered.
- **MLflow-in-CI:** explicitly kept local (Task 2.8) and removed from the app workflow (Task 3.2), matching spec §6.
- **App Runner sizing:** the reused module defaults to cpu `1024` / memory `2048` (1 vCPU / 2 GB) — sufficient for Donut; no override needed.
- **Naming consistency:** ECR repo is `dev-mlops-snapreceipt-repository` (env-prefixed by the module's `locals.tf`) everywhere — tfvars key, GitHub secret, image URI, App Runner `image_identifier`.
