FROM python:3.13-slim

# supernotelib provides the `supernote-tool` CLI used by router.py.
# Pin versions here; Renovate/uv.lock can take over later.
# supernotelib >=0.7.3 is needed for current Manta firmware (.note file
# version 20260016); 0.7.0 raises "unsupported file format" on those.
RUN pip install --no-cache-dir supernotelib==0.7.3 requests==2.32.3

WORKDIR /app
COPY router.py .

USER 65534:65534
CMD ["python", "-u", "router.py"]
