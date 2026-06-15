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
