"""
A08 Event Emitter for sending validated knowledge to S03 (Knowledge Service).

Emits store_validated_knowledge events to notify S03 that validated knowledge
should be stored into the knowledge database.
"""

import os
from datetime import datetime
from typing import Any
from dotenv import load_dotenv

from ..services.MessageQueueService import MessageQueueService

load_dotenv()


class A08EventEmitter:
    """
    Emits A08 events to S03 Knowledge Service.
    """

    def __init__(self, mq: MessageQueueService):
        self.mq = mq
        self.queue_name = os.getenv("KNOWLEDGE_STORE_EVENT_QUEUE", "knowledge_store_events")
        # Ensure queue is declared
        self.mq.declare_queue(self.queue_name)

    def emit_store_validated_knowledge(
        self,
        partner_id: str,
        seaweed_file_id: str,
        validated_at: datetime | None = None,
    ) -> None:
        """
        Emit a store_validated_knowledge event to S03.

        Args:
            partner_id: The partner ID that submitted the knowledge
            seaweed_file_id: The SeaweedFS file ID containing the knowledge data
            validated_at: The timestamp when validation was completed (defaults to now)
        """
        if validated_at is None:
            validated_at = datetime.utcnow()

        message = {
            "event": "store_validated_knowledge",
            "data": {
                "partner_id": partner_id,
                "seaweed_file_id": seaweed_file_id,
                "validated_at": validated_at.isoformat() + "Z",
            },
        }

        self.mq.publish_message(self.queue_name, message)
        print(
            f"Emitted store_validated_knowledge event for partner={partner_id}, file={seaweed_file_id}"
        )


# Module-level instance (will be initialized when needed)
_a08_emitter: A08EventEmitter | None = None


def get_a08_emitter() -> A08EventEmitter:
    """Get or create the A08 event emitter singleton."""
    global _a08_emitter
    if _a08_emitter is None:
        mq = MessageQueueService()
        _a08_emitter = A08EventEmitter(mq)
    return _a08_emitter


def emit_store_validated_knowledge(
    partner_id: str,
    seaweed_file_id: str,
    validated_at: datetime | None = None,
) -> None:
    """
    Convenience function to emit store_validated_knowledge event.

    Args:
        partner_id: The partner ID that submitted the knowledge
        seaweed_file_id: The SeaweedFS file ID containing the knowledge data
        validated_at: The timestamp when validation was completed
    """
    emitter = get_a08_emitter()
    emitter.emit_store_validated_knowledge(partner_id, seaweed_file_id, validated_at)
