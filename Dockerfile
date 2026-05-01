FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md .python-version ./
COPY anvil ./anvil
COPY examples ./examples
COPY scenarios ./scenarios
COPY runs/.gitkeep ./runs/.gitkeep

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

CMD ["anvil", "run", "scenarios/refund_agent.yaml", "--offline"]

