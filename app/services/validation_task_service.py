"""
Validation Task Service for S05 Knowledge Validator Service.

Provides business logic for managing validation tasks including:
- Listing partner updates with pagination and filtering
- Getting update details
- Approving updates (triggers A08 to S03)
- Rejecting updates
"""

from datetime import datetime
from typing import Any
from bson import ObjectId

from ..collections.s05 import validation_tasks_collection
from ..utils.seaweedfs import seaweedfs_client
from ..utils.db import serialize_mongo_doc, str_to_objectid
from ..handlers.a08_emitter import emit_store_validated_knowledge


class ValidationTaskService:
    """
    Service for managing validation tasks.
    """

    def __init__(self):
        self.collection = validation_tasks_collection

    def get_updates_list(
        self,
        status: str | None = None,
        partner_id: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Get a paginated list of partner updates.

        Args:
            status: Filter by status (pending, approved, rejected). None for all.
            partner_id: Filter by partner ID. None for all partners.
            page: Page number (1-indexed)
            limit: Items per page (max 100)

        Returns:
            Dict with pagination info and list of updates
        """
        # Build query filter
        query: dict[str, Any] = {}
        if status:
            # Map API status values to DB values
            status_map = {
                "pending": "pending",
                "approved": "validated",
                "rejected": "rejected",
            }
            db_status = status_map.get(status, status)
            query["status"] = db_status

        if partner_id:
            query["partner_id"] = partner_id

        # Enforce limits
        limit = min(limit, 100)
        skip = (page - 1) * limit

        # Get total count
        total_count = self.collection.count_documents(query)

        # Get updates sorted by created_at descending
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        updates = list(cursor)

        # Get summary counts
        summary = {
            "total": self.collection.count_documents({}),
            "pending": self.collection.count_documents({"status": "pending"}),
            "approved": self.collection.count_documents({"status": "validated"}),
            "rejected": self.collection.count_documents({"status": "rejected"}),
        }

        # Calculate total pages
        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1

        # Serialize and map status for API response
        serialized_updates = []
        for update in updates:
            serialized = serialize_mongo_doc(update)
            # Map DB status to API status
            if serialized.get("status") == "validated":
                serialized["status"] = "approved"
            serialized_updates.append(serialized)

        return {
            "status": "success",
            "total_count": total_count,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "updates": serialized_updates,
            "summary": summary,
        }

    def get_update_details(self, update_id: str) -> dict[str, Any] | None:
        """
        Get detailed information about a specific update.

        Args:
            update_id: The update ID

        Returns:
            Update details including FAQs and packages, or None if not found
        """
        obj_id = str_to_objectid(update_id)
        if not obj_id:
            return None

        task = self.collection.find_one({"_id": obj_id})
        if not task:
            return None

        serialized = serialize_mongo_doc(task)

        # Map DB status to API status
        if serialized.get("status") == "validated":
            serialized["status"] = "approved"

        # Fetch the actual data from SeaweedFS
        try:
            seaweed_file_id = task.get("seaweed_file_id")
            if seaweed_file_id:
                knowledge_data = seaweedfs_client.download_json(seaweed_file_id)
                serialized["faqs"] = knowledge_data.get("faqs", [])
                serialized["packages"] = knowledge_data.get("packages", [])
            else:
                serialized["faqs"] = []
                serialized["packages"] = []
        except Exception as e:
            print(f"Failed to fetch knowledge data from SeaweedFS: {e}")
            serialized["faqs"] = []
            serialized["packages"] = []

        return {"status": "success", "update": serialized}

    def approve_update(self, update_id: str, validator_id: str) -> dict[str, Any] | None:
        """
        Approve a partner update.

        Args:
            update_id: The update ID
            validator_id: The ID of the user approving the update

        Returns:
            Updated task info, or None if not found or not pending
        """
        obj_id = str_to_objectid(update_id)
        if not obj_id:
            return None

        # Find the task
        task = self.collection.find_one({"_id": obj_id})
        if not task:
            return None

        # Check if already processed
        if task.get("status") != "pending":
            return {"error": f"Update is already {task.get('status')}"}

        validated_at = datetime.utcnow()

        # Update the task
        result = self.collection.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "status": "validated",
                    "validator_id": validator_id,
                    "validated_at": validated_at,
                }
            },
        )

        if result.modified_count == 0:
            return None

        # Emit A08 event to S03
        try:
            emit_store_validated_knowledge(
                partner_id=task.get("partner_id"),
                seaweed_file_id=task.get("seaweed_file_id"),
                validated_at=validated_at,
            )
        except Exception as e:
            print(f"Failed to emit A08 event: {e}")
            # Don't fail the approval, S03 can handle missing data

        # Get updated task
        updated_task = self.collection.find_one({"_id": obj_id})
        serialized = serialize_mongo_doc(updated_task)
        serialized["status"] = "approved"  # Map for API

        return {"status": "success", "update": serialized}

    def reject_update(self, update_id: str, validator_id: str) -> dict[str, Any] | None:
        """
        Reject a partner update.

        Args:
            update_id: The update ID
            validator_id: The ID of the user rejecting the update

        Returns:
            Updated task info, or None if not found or not pending
        """
        obj_id = str_to_objectid(update_id)
        if not obj_id:
            return None

        # Find the task
        task = self.collection.find_one({"_id": obj_id})
        if not task:
            return None

        # Check if already processed
        if task.get("status") != "pending":
            return {"error": f"Update is already {task.get('status')}"}

        validated_at = datetime.utcnow()

        # Update the task
        result = self.collection.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "status": "rejected",
                    "validator_id": validator_id,
                    "validated_at": validated_at,
                }
            },
        )

        if result.modified_count == 0:
            return None

        # Get updated task
        updated_task = self.collection.find_one({"_id": obj_id})
        serialized = serialize_mongo_doc(updated_task)

        return {"status": "success", "update": serialized}


# Singleton instance
validation_task_service = ValidationTaskService()
