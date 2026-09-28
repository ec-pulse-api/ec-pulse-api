from app.main import app
from app.services.key_admin import register_key_routes
from app.services.research_batch_routes import register_research_batch_routes

register_key_routes(app)
register_research_batch_routes(app)

# Keep the production Git integration deployment path active.
