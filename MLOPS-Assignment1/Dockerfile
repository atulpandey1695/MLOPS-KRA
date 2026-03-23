FROM python:3.8-slim AS builder

WORKDIR /build

# Install inference-only dependencies into an isolated prefix
COPY requirements-inference.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-inference.txt

# Install the local cnnClassifier package (non-editable)
COPY setup.py README.md ./
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install --no-deps .

FROM python:3.8-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/install/lib/python3.8/site-packages" \
    PATH="/install/bin:${PATH}"

# Bring in installed packages from the builder stage
COPY --from=builder /install /install

WORKDIR /app

# Copy only the files required for inference
COPY app.py         .
COPY config/        config/
COPY params.yaml    .
COPY templates/     templates/
COPY model/         model/

# Run as a least-privilege non-root user
RUN useradd --uid 1001 --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

CMD ["python", "app.py"]

