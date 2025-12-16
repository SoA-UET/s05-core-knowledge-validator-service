"""
A34 Event Handler for receiving knowledge validation requests from S12 (Partner).

Handles three events:
- snapshot_start: Begin receiving update snapshot
- snapshot_chunk: Receive data chunks
- snapshot_stop: Complete receiving update snapshot
"""

import os
import base64
import threading
from datetime import datetime
from typing import Any
from dotenv import load_dotenv

from ..services.MessageQueueService import MessageQueueService
from ..utils.seaweedfs import seaweedfs_client
from ..collections.s05 import validation_tasks_collection

load_dotenv()


class SnapshotBuffer:
    """
    Thread-safe buffer for reassembling snapshot chunks.
    Each partner_id + snapshot_id combination has its own buffer.
    """

    def __init__(self):
        self._buffers: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _make_key(self, partner_id: str, snapshot_id: str) -> str:
        return f"{partner_id}:{snapshot_id}"

    def start_snapshot(self, partner_id: str, snapshot_id: str) -> None:
        """Initialize a new snapshot buffer."""
        key = self._make_key(partner_id, snapshot_id)
        with self._lock:
            self._buffers[key] = {
                "partner_id": partner_id,
                "snapshot_id": snapshot_id,
                "chunks": {},
                "started_at": datetime.utcnow(),
            }
        print(f"Snapshot started: {key}")

    def add_chunk(
        self, partner_id: str, snapshot_id: str, seq: int, chunk_data_base64: str
    ) -> None:
        """Add a chunk to the snapshot buffer."""
        key = self._make_key(partner_id, snapshot_id)
        with self._lock:
            if key not in self._buffers:
                print(f"Warning: Received chunk for unknown snapshot: {key}")
                return
            self._buffers[key]["chunks"][seq] = chunk_data_base64
        print(f"Chunk added: {key}, seq={seq}")

    def complete_snapshot(
        self, partner_id: str, snapshot_id: str, total_chunks: int
    ) -> bytes | None:
        """
        Complete and reassemble the snapshot.
        Returns the reassembled data or None if incomplete.
        """
        key = self._make_key(partner_id, snapshot_id)
        with self._lock:
            if key not in self._buffers:
                print(f"Warning: Completing unknown snapshot: {key}")
                return None

            buffer = self._buffers[key]
            chunks = buffer["chunks"]

            # Verify all chunks received
            if len(chunks) != total_chunks:
                print(
                    f"Warning: Missing chunks for {key}. Expected {total_chunks}, got {len(chunks)}"
                )
                return None

            # Check sequence numbers are complete (1 to total_chunks)
            for i in range(1, total_chunks + 1):
                if i not in chunks:
                    print(f"Warning: Missing chunk seq={i} for {key}")
                    return None

            # Reassemble in order
            assembled_data = b""
            for i in range(1, total_chunks + 1):
                chunk_b64 = chunks[i]
                chunk_bytes = base64.b64decode(chunk_b64)
                assembled_data += chunk_bytes

            # Clean up buffer
            del self._buffers[key]

            print(f"Snapshot completed: {key}, size={len(assembled_data)} bytes")
            return assembled_data

    def cleanup_stale(self, max_age_seconds: int = 3600) -> None:
        """Remove stale snapshot buffers older than max_age_seconds."""
        now = datetime.utcnow()
        with self._lock:
            stale_keys = []
            for key, buffer in self._buffers.items():
                age = (now - buffer["started_at"]).total_seconds()
                if age > max_age_seconds:
                    stale_keys.append(key)
            for key in stale_keys:
                del self._buffers[key]
                print(f"Cleaned up stale snapshot: {key}")


# Singleton buffer
snapshot_buffer = SnapshotBuffer()


class A34EventHandler:
    """
    Handles A34 events from S12 Partner Knowledge Update Service.
    """

    def __init__(self, mq: MessageQueueService):
        self.mq = mq
        self.queue_name = os.getenv(
            "UPDATE_VALIDATION_EVENT_QUEUE", "update_validation_events"
        )

    def handle_event(self, message: dict) -> None:
        """
        Main event handler for A34 events.
        Routes to specific handlers based on event type.
        """
        event = message.get("event", "")
        data = message.get("data", {})

        try:
            if event == "snapshot_start":
                self._handle_snapshot_start(data)
            elif event == "snapshot_chunk":
                self._handle_snapshot_chunk(data)
            elif event == "snapshot_stop":
                self._handle_snapshot_stop(data)
            else:
                print(f"Unknown A34 event: {event}")
        except Exception as e:
            print(f"Error handling A34 event '{event}': {e}")

    def _handle_snapshot_start(self, data: dict) -> None:
        """Handle snapshot_start event."""
        partner_id = data.get("partner_id")
        snapshot_id = data.get("snapshot_id")

        if not partner_id or not snapshot_id:
            print("Invalid snapshot_start event: missing partner_id or snapshot_id")
            return

        snapshot_buffer.start_snapshot(partner_id, snapshot_id)

    def _handle_snapshot_chunk(self, data: dict) -> None:
        """Handle snapshot_chunk event."""
        partner_id = data.get("partner_id")
        snapshot_id = data.get("snapshot_id")
        seq = data.get("seq")
        chunk_data_base64 = data.get("chunk_data_base64")

        if not all([partner_id, snapshot_id, seq is not None, chunk_data_base64]):
            print("Invalid snapshot_chunk event: missing required fields")
            return

        snapshot_buffer.add_chunk(partner_id, snapshot_id, seq, chunk_data_base64)

    def _handle_snapshot_stop(self, data: dict) -> None:
        """Handle snapshot_stop event."""
        partner_id = data.get("partner_id")
        snapshot_id = data.get("snapshot_id")
        total_chunks = data.get("total_chunks")

        if not all([partner_id, snapshot_id, total_chunks is not None]):
            print("Invalid snapshot_stop event: missing required fields")
            return

        # Reassemble the snapshot
        assembled_data = snapshot_buffer.complete_snapshot(
            partner_id, snapshot_id, total_chunks
        )

        if assembled_data is None:
            print(f"Failed to reassemble snapshot: {partner_id}:{snapshot_id}")
            return

        # Store in SeaweedFS
        try:
            seaweed_file_id = seaweedfs_client.upload_file(
                assembled_data, f"update_{partner_id}_{snapshot_id}.json"
            )
            print(f"Stored update draft in SeaweedFS: {seaweed_file_id}")
        except Exception as e:
            print(f"Failed to upload to SeaweedFS: {e}")
            return

        # Create validation task in database
        try:
            task = {
                "seaweed_file_id": seaweed_file_id,
                "partner_id": partner_id,
                "status": "pending",
                "validator_id": None,
                "created_at": datetime.utcnow(),
                "validated_at": None,
            }
            result = validation_tasks_collection.insert_one(task)
            print(f"Created validation task: {result.inserted_id}")
        except Exception as e:
            print(f"Failed to create validation task: {e}")

    def setup(self) -> None:
        """Setup the queue and register callback."""
        self.mq.declare_queue(self.queue_name)
        self.mq.register_callback(self.queue_name, self.handle_event)
        print(f"A34 handler setup complete. Listening on queue: {self.queue_name}")


def create_a34_handler(mq: MessageQueueService) -> A34EventHandler:
    """Factory function to create and setup an A34 event handler."""
    handler = A34EventHandler(mq)
    handler.setup()
    return handler
