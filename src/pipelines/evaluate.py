"""Evaluate the deployed extraction logic against labelled CORD samples."""
import glob
import json
import os


def _money(x):
    try:
        return round(float(str(x).replace(",", "").replace("€", "").strip()), 2)
    except (ValueError, TypeError):
        return None


def field_score(pred: dict, gt: dict) -> float:
    """Fraction of checked fields that match ground truth (total + item count)."""
    checks = [
        _money(pred.get("total_amount")) == _money(gt.get("total")),
        abs(len(pred.get("items", [])) - len(gt.get("items", []))) <= 1,
    ]
    return sum(1 for c in checks if c) / len(checks)


def evaluate(samples_dir: str = "eval_data") -> float:
    """Run the real model over every labelled sample and return mean field accuracy."""
    from PIL import Image

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
