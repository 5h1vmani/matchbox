# Cross-platform run target: identical on macOS, Windows, and Linux through
# Docker. It bakes in weasyprint's Pango/Cairo system libraries -- the one piece
# that is painful to install natively on Windows. (The native-Windows path
# without Docker is the Chromium PDF backend: pip install "matchbox[chromium]";
# see src/matchbox/pdf_backend.py.)
#
# Build the SPA first so the web UI is served:
#   cd frontend && npm install && npm run build
# Without it the JSON API and the CLIs still work; the UI route returns 503.
#
# Build + run (port bound to loopback only, matching the localhost-only design):
#   docker build -t matchbox .
#   docker run --rm -p 127.0.0.1:8765:8765 -v "$PWD/people:/app/people" matchbox

FROM python:3.12-slim

# weasyprint runtime system libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY schemas ./schemas
COPY shared ./shared
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache -e .

EXPOSE 8765
ENV MATCHBOX_PDF_BACKEND=weasyprint
# Bind 0.0.0.0 inside the container; the host maps it to 127.0.0.1 (see above),
# so the localhost-only security boundary is preserved.
CMD ["python", "-c", "from matchbox.web.app import run; run(host='0.0.0.0', port=8765)"]
