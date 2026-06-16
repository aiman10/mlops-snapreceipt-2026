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
