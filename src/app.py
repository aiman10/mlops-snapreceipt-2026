import logging

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from extract import extract

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SnapReceipt Donut Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to the SnapReceipt frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"health_check": "OK"}


@app.get("/health")
async def health():
    return {"status": "ok", "model": "donut-v1", "build": "cd-demo"}


@app.post("/extract")
async def extract_receipt(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    image_bytes = await file.read()
    try:
        return extract(image_bytes)
    except Exception as e:  # noqa: BLE001 - surface a clean 500 to the client
        logger.error("Inference failed: %s", e)
        raise HTTPException(status_code=500, detail="Model inference failed.")
