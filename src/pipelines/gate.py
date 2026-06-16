"""Evaluate the model on labelled data and fail the pipeline if it scores below threshold.

Logs the metric to MLflow when MLFLOW_TRACKING_URI is set and reachable; logging failures
never block the gate (the metric decision is what matters)."""
import logging
import os
import sys

from pipelines.evaluate import evaluate

logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")

THRESHOLD = float(os.environ.get("EVAL_THRESHOLD", "0.6"))


def _log_to_mlflow(score: float):
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        logging.info("MLFLOW_TRACKING_URI unset; skipping remote logging.")
        return
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    try:
        import mlflow

        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("Donut Eval Gate")
        with mlflow.start_run():
            mlflow.log_metric("field_accuracy", score)
            mlflow.log_param("threshold", THRESHOLD)
        logging.info("Logged field_accuracy=%.4f to MLflow at %s", score, uri)
    except Exception as e:  # noqa: BLE001 - logging must never block the gate
        logging.warning("MLflow logging skipped (%s)", e)


def main():
    score = evaluate("eval_data")
    _log_to_mlflow(score)
    print(f"field_accuracy={score:.4f} threshold={THRESHOLD}")
    if score >= THRESHOLD:
        print("GATE PASS")
        sys.exit(0)
    print("GATE FAIL — deploy blocked")
    sys.exit(1)


if __name__ == "__main__":
    main()
