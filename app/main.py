from fastapi import FastAPI

app = FastAPI(
    title="EC Pulse API",
    description="EC product data API and price monitoring service",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}
