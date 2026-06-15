import re
from datetime import date

import yaml

_PROCESSOR = None
_MODEL = None
_CONFIG = None


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
