from fastapi import FastAPI
from fastapi.responses import JSONResponse

try:
    from app.main import app
    from app.services.key_admin import register_key_routes
    from app.services.research_batch_routes import register_research_batch_routes

    register_key_routes(app)
    register_research_batch_routes(app)
except Exception as exc:
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def boot_error(path: str):
        return JSONResponse(
            status_code=500,
            content={
                "status": "boot_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "path": path,
            },
        )
