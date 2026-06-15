import re
from datetime import date

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


def parse_price(value) -> float:
    """Coerce a Donut/CORD price token into a float (0.0 on failure)."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.]", "", value)
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def extract_items(menu: list) -> list:
    """Flatten CORD menu entries into [{description, quantity, price}], including
    unitprice sub-items. Mirrors the SnapReceipt server.py extraction logic."""
    items = []
    if not isinstance(menu, list):
        return items

    for entry in menu:
        if not isinstance(entry, dict):
            continue

        name = entry.get("nm", "Unknown item")
        price = parse_price(entry.get("price"))
        cnt_str = re.sub(r"[^\d]", "", str(entry.get("cnt", "1")))
        quantity = int(cnt_str) if cnt_str else 1

        unitprice_val = entry.get("unitprice")
        if isinstance(unitprice_val, list):
            for sub in unitprice_val:
                if isinstance(sub, dict) and sub.get("nm"):
                    sub_price = parse_price(sub.get("price"))
                    sub_cnt_str = re.sub(r"[^\d]", "", str(sub.get("cnt", "1")))
                    sub_qty = int(sub_cnt_str) if sub_cnt_str else 1
                    items.append({
                        "description": sub["nm"],
                        "quantity": sub_qty,
                        "price": sub_price,
                    })
            continue

        if name and price > 0:
            items.append({
                "description": name,
                "quantity": quantity,
                "price": price,
            })

    return items


def map_to_structured(raw: dict) -> dict:
    """Map Donut/CORD-v2 output into the SnapReceipt schema. Pure + deterministic.
    (Donut-only: the DeBERTa `category` field is added by the classifier extension.)"""
    menu = raw.get("menu", [])
    if isinstance(menu, dict):
        menu = [menu]
    elif not isinstance(menu, list):
        menu = []

    sub_total = raw.get("sub_total", {})
    if not isinstance(sub_total, dict):
        sub_total = {}
    total = raw.get("total", {})
    if not isinstance(total, dict):
        total = {}

    items = extract_items(menu)
    total_amount = parse_price(total.get("total_price") or sub_total.get("subtotal_price"))
    tax = parse_price(sub_total.get("tax_price") or sub_total.get("etc"))

    merchant_name = "Unknown"
    if menu and isinstance(menu[0], dict) and menu[0].get("nm"):
        merchant_name = menu[0]["nm"]

    return {
        "merchant_name": merchant_name,
        "date": str(date.today()),
        "total_amount": total_amount,
        "tax": tax,
        "items": items,
    }


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


def run_inference(image) -> dict:
    """Run Donut on a PIL image and return the SnapReceipt schema."""
    import torch

    processor, model = _load_model()
    device = next(model.parameters()).device

    pixel_values = processor(image, return_tensors="pt").pixel_values.to(device)

    cfg = _load_config()
    task_prompt = cfg["model"]["task_token"]
    decoder_input_ids = processor.tokenizer(
        task_prompt, add_special_tokens=False, return_tensors="pt"
    ).input_ids.to(device)

    with torch.no_grad():
        outputs = model.generate(
            pixel_values,
            decoder_input_ids=decoder_input_ids,
            max_length=model.decoder.config.max_position_embeddings,
            early_stopping=True,
            pad_token_id=processor.tokenizer.pad_token_id,
            eos_token_id=processor.tokenizer.eos_token_id,
            use_cache=True,
            num_beams=1,
            bad_words_ids=[[processor.tokenizer.unk_token_id]],
            return_dict_in_generate=True,
        )

    decoded = processor.batch_decode(outputs.sequences)[0]
    decoded = decoded.replace(processor.tokenizer.eos_token, "").replace(
        processor.tokenizer.pad_token, ""
    )
    decoded = re.sub(r"<.*?>", "", decoded, count=1).strip()
    raw = processor.token2json(decoded)
    return map_to_structured(raw)


def extract(image_bytes: bytes) -> dict:
    """Open raw image bytes and run Donut inference."""
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return run_inference(image)
