FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# ── Runtime user ────────────────────────────────────────────────────────────
RUN groupadd --system --gid 999 appuser \
    && useradd  --system --gid 999 --uid 999 --create-home appuser

WORKDIR /app

# ── uv configuration ────────────────────────────────────────────────────────
# Compile .pyc files at install time so the first import is fast
ENV UV_COMPILE_BYTECODE=1
# Copy packages from the uv cache instead of hard-linking (required for COPY --mount)
ENV UV_LINK_MODE=copy
# Strip dev dependencies from the final image
ENV UV_NO_DEV=1

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# ── Dependencies (cached layer) ─────────────────────────────────────────────
# Mount the uv cache and bind the lock/config files so this layer is only
# rebuilt when dependencies actually change, not on every source edit.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# ── Application source ──────────────────────────────────────────────────────
COPY . .

# Install the project package on top of the already-cached dependencies.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# ── Entrypoint ──────────────────────────────────────────────────────────────
ENTRYPOINT []
USER appuser
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
