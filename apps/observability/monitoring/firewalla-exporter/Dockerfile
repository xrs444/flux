FROM python:3.13-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock exporter.py ./
RUN uv sync --frozen --no-dev

EXPOSE 9878
CMD ["uv", "run", "exporter.py"]
