FROM python:3.13-slim

# supernotelib provides the `supernote-tool` CLI used by router.py.
# Pin versions here; Renovate/uv.lock can take over later.
RUN pip install --no-cache-dir supernotelib==0.7.0 requests==2.32.3

WORKDIR /app
COPY router.py .

USER 65534:65534
CMD ["python", "-u", "router.py"]
