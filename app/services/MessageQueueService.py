"""
RabbitMQ Message Queue Service wrapper.
Uses pika internally for RabbitMQ communication.
"""

import os
import json
import pika
from typing import Callable, Any
from dotenv import load_dotenv

load_dotenv()


class MessageQueueService:
    """
    A wrapper for RabbitMQ operations using pika.
    Supports cloning for thread-safe operations.
    """

    def __init__(self, connection: pika.BlockingConnection | None = None):
        """
        Initialize the MessageQueueService.
        If no connection is provided, creates a new one from RABBITMQ_URL env var.
        """
        self._connection = connection
        self._channel = None
        self._callbacks: dict[str, Callable[[dict], None]] = {}

    def _ensure_connection(self) -> pika.BlockingConnection:
        """Ensure connection is established."""
        if self._connection is None or self._connection.is_closed:
            rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672")
            parameters = pika.URLParameters(rabbitmq_url)
            self._connection = pika.BlockingConnection(parameters)
        return self._connection

    def _ensure_channel(self) -> pika.adapters.blocking_connection.BlockingChannel:
        """Ensure channel is created."""
        if self._channel is None or self._channel.is_closed:
            connection = self._ensure_connection()
            self._channel = connection.channel()
        return self._channel

    def clone(self) -> "MessageQueueService":
        """
        Create a new MessageQueueService instance with a fresh connection.
        Useful for thread-safe operations where each thread needs its own connection.
        """
        return MessageQueueService()

    def declare_queue(self, queue_name: str, durable: bool = True) -> None:
        """
        Declare a queue. Creates it if it doesn't exist.

        Args:
            queue_name: Name of the queue
            durable: If True, queue survives broker restart
        """
        channel = self._ensure_channel()
        channel.queue_declare(queue=queue_name, durable=durable)

    def publish_message(self, queue_name: str, message: dict) -> None:
        """
        Publish a message to a queue.

        Args:
            queue_name: Name of the queue
            message: Dictionary to be JSON-serialized and sent
        """
        channel = self._ensure_channel()
        body = json.dumps(message, ensure_ascii=False, default=str)
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=body.encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
                content_type="application/json",
            ),
        )

    def register_callback(
        self, queue_name: str, callback: Callable[[dict], None]
    ) -> None:
        """
        Register a callback function for messages from a queue.

        Args:
            queue_name: Name of the queue to consume from
            callback: Function to call when a message is received.
                      The message is already parsed from JSON to dict.
        """
        self._callbacks[queue_name] = callback

    def start_consuming(self) -> None:
        """
        Start consuming messages from all registered queues.
        This is a blocking call that runs indefinitely.
        """
        channel = self._ensure_channel()

        for queue_name, callback in self._callbacks.items():
            # Wrap callback to handle message parsing
            def make_wrapped_callback(cb: Callable[[dict], None]):
                def wrapped_callback(ch, method, properties, body):
                    try:
                        message = json.loads(body.decode("utf-8"))
                        cb(message)
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        # Negative acknowledge - requeue the message
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

                return wrapped_callback

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=queue_name,
                on_message_callback=make_wrapped_callback(callback),
                auto_ack=False,
            )

        print(f"Starting to consume from queues: {list(self._callbacks.keys())}")
        channel.start_consuming()

    def close(self) -> None:
        """Close the connection."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
