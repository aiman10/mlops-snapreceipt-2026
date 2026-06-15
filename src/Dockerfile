FROM python:3.12-slim

WORKDIR /app

COPY requirements-serve.txt .

# Install the CPU-only build of torch (App Runner has no GPU). Avoids pulling
# multi-GB CUDA libraries that would bloat the image and slow cold starts.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements-serve.txt

COPY app.py extract.py config.yml ./
COPY models/ ./models/

EXPOSE 80
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
