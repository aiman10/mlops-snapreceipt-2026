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
