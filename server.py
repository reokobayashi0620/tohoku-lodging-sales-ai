from app import app
from bulk_actions import register_bulk_actions
from miyagi_enrichment import register_miyagi_enrichment

register_bulk_actions(app)
register_miyagi_enrichment(app)
