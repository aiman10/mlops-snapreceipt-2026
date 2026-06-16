"""Download N labelled CORD-v2 test receipts into src/eval_data as image+gt JSON pairs.

The CORD-v2 test split ships ground-truth `gt_parse` JSON, which gives us real labels to
score the Donut extraction against (Phase C / metric-gated deploy)."""
import json
import os

from datasets import load_dataset

OUT = "eval_data"
N = int(os.environ.get("EVAL_N", "20"))


def _flatten(gt_parse: dict) -> dict:
    menu = gt_parse.get("menu", [])
    if isinstance(menu, dict):
        menu = [menu]
    items = [
        {"description": m.get("nm", ""), "price": m.get("price")}
        for m in menu
        if isinstance(m, dict)
    ]
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
