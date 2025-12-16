"""
MongoDB collections for S05 Knowledge Validator Service.
Database: telcenter_core_s05
"""

from pymongo import MongoClient, DESCENDING
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")

if not MONGO_URL:
    print("Environment variable MONGO_URL is missing.")
    import sys

    sys.exit(1)

# Connect to MongoDB
client = MongoClient(MONGO_URL)

# Use the S05 database
db = client.telcenter_core_s05

# Collection: validation_tasks
# Tracks validation tasks and history
validation_tasks_collection = db.validation_tasks

# Create indexes for common queries
validation_tasks_collection.create_index([("status", 1)])
validation_tasks_collection.create_index([("partner_id", 1)])
validation_tasks_collection.create_index([("created_at", DESCENDING)])
validation_tasks_collection.create_index([("status", 1), ("created_at", DESCENDING)])
