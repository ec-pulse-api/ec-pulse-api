# EC Pulse API

EC product data API and price monitoring service.

## MVP

- Product Data API: URL -> normalized product JSON
- Price Monitoring: scheduled checks and webhook notifications
- Price History: historical price data

## Local development

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open `/docs` for the interactive API documentation.

## Endpoint

`GET /health`

Returns:

```json
{"status": "ok"}
```

## Project structure

```text
app/
├── main.py
├── api/
├── models/
├── services/
└── scrapers/

tests/
```

## Status

Early MVP development.
