# Commander Demo Backend

Python FastAPI backend for the Commander Demo project.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
python -m commander.main
```

## API

- `GET /health` - Health check
- `GET /api/v1/version` - Version info
- `GET /docs` - OpenAPI documentation (debug mode only)
