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
