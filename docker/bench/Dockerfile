# Benchmark image for the "small VPS" profile (docs/measurement.md). Code is copied in; data,
# artifacts and results are mounted at run time, so no page text is baked into the image.
FROM python:3.12.12-slim
WORKDIR /app
COPY docker/bench/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY src /app/src
COPY scripts /app/scripts
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1 BENCH_THREADS=1
ENTRYPOINT ["python", "scripts/bench_tier1.py"]
