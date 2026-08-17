FROM python:3.13-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock exporter.py ./
RUN uv sync --frozen --no-dev

EXPOSE 9878
# Invoke the already-synced venv's interpreter directly rather than `uv run`
# -- uv needs a writable cache dir even when the venv is fully in sync, which
# breaks under a non-root/no-HOME securityContext (runAsUser: 65534 has no
# writable home, "Failed to initialize cache at /nonexistent/.cache/uv").
CMD ["/app/.venv/bin/python", "exporter.py"]
