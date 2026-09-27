from app.main import app
from app.services.key_admin import register_key_routes

register_key_routes(app)
