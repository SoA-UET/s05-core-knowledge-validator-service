# Services package

from .validation_task_service import validation_task_service
from .MessageQueueService import MessageQueueService

# Placeholder for conversation service (if exists in original codebase)
# This is a mock service for the conversations controller
class _MockConversationService:
    """Mock conversation service for compatibility."""
    def get_collection(self, pageable):
        return []
    
    def post_item(self, data):
        return data
    
    def get_item_by_id(self, id):
        return {"id": id}
    
    def patch_item_by_id(self, id, data):
        return {"id": id, **data}
    
    def delete_item_by_id(self, id):
        pass

conversation_service = _MockConversationService()
