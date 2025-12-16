"""
S05 Knowledge Validator Service - Main Entry Point

This service:
1. Exposes HTTP API (H22) for Core Portal to manage partner knowledge updates
2. Consumes RabbitMQ events (A34) from Partner's S12 service
3. Emits RabbitMQ events (A08) to Core's S03 service

Uses multithreading for I/O-bound operations.
"""

import os
import sys
import threading
from dotenv import load_dotenv

load_dotenv()

# Number of worker threads for RabbitMQ consumers
NUM_MQ_WORKERS = int(os.getenv("NUM_MQ_WORKERS", "4"))


def run_http_server():
    """Run the Flask HTTP server."""
    from . import app, socketio

    host = os.getenv("HTTP_HOST", "0.0.0.0")
    port = int(os.getenv("HTTP_PORT", "5005"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    print(f"Starting HTTP server on {host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)


def run_mq_consumer():
    """Run a RabbitMQ consumer worker."""
    from .services.MessageQueueService import MessageQueueService
    from .handlers.a34_handler import create_a34_handler

    # Create a new MQ connection for this thread
    mq = MessageQueueService()

    # Setup A34 handler
    handler = create_a34_handler(mq)

    # Start consuming (blocking)
    print(f"Starting MQ consumer in thread {threading.current_thread().name}")
    mq.start_consuming()


def init_services():
    """Initialize services that need to run at startup."""
    from .utils.auth import init_auth

    # Initialize JWT authentication (fetches JWKS)
    init_auth()

    print("Services initialized")


def main():
    """Main entry point for S05 Knowledge Validator Service."""
    print("=" * 60)
    print("S05 Knowledge Validator Service")
    print("=" * 60)

    # Initialize services
    init_services()

    # Start RabbitMQ consumer threads
    mq_threads = []
    for i in range(NUM_MQ_WORKERS):
        thread = threading.Thread(
            target=run_mq_consumer,
            name=f"MQWorker-{i}",
            daemon=True,
        )
        thread.start()
        mq_threads.append(thread)

    print(f"Started {NUM_MQ_WORKERS} MQ consumer worker(s)")

    # Run HTTP server in main thread (blocking)
    run_http_server()


if __name__ == "__main__":
    main()
