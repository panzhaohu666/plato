"""
Yjs Collaboration Service — manages Y.Doc instances per dynamic table.

Architecture:
    ┌─────────────────────────────────────────────┐
    │               Uvicorn Worker 1               │
    │  YjsDocManager ─── local Y.Doc instances     │
    │       │                                      │
    │       ├─ Redis Pub/Sub ──► Uvicorn Worker 2  │
    │       ├─ Redis Pub/Sub ──► Uvicorn Worker 3  │
    │       │                                      │
    │       └─ Celery Task ──► PostgreSQL BYTEA    │
    └─────────────────────────────────────────────┘

Protocol Flow (Yjs Sync Protocol):
    1. Client connects → sends Step1 (local state vector)
    2. Server responds with Step2 (missing updates)
    3. Ongoing: bidirectional YjsUpdate messages
       - Client → Server: update applied locally, broadcast to room
       - Server → Client: updates from other collaborators

Multi-Worker Strategy:
    - Each worker maintains its own in-memory Y.Doc for active tables
    - When Worker A receives an update, it:
       a. Applies to local Y.Doc
       b. Publishes the raw update bytes to Redis channel "yjs:{table_name}"
       c. Other workers subscribe and apply the update to their local copies
    - This avoids needing a shared-memory Y.Doc (which CPython can't do)
"""
import logging
import threading
from typing import Optional
import y_py as Y
import redis

from django.conf import settings

logger = logging.getLogger(__name__)


class YjsDocManager:
    """
    Manages Y.Doc instances for collaborative table editing.

    Each dynamic table gets its own Y.Doc instance.
    Thread-safe for concurrent WebSocket connections.

    Usage:
        manager = YjsDocManager()
        doc = manager.get_or_create("sales_leads")
        update = doc.encode_update()
    """

    def __init__(self):
        self._docs: dict[str, Y.YDoc] = {}
        self._lock = threading.Lock()

        # Redis for cross-worker broadcast
        self._redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=False,  # Keep binary data as bytes
        )
        self._pubsub: Optional[redis.client.PubSub] = None
        self._pubsub_thread: Optional[threading.Thread] = None

    # ----------------------------------------------------------------
    # Document Lifecycle
    # ----------------------------------------------------------------

    def get_or_create(self, table_name: str) -> Y.YDoc:
        """Get or create a Y.Doc for a table."""
        with self._lock:
            if table_name not in self._docs:
                doc = Y.YDoc()
                # Try to load persisted state
                persisted = self._load_from_db(table_name)
                if persisted:
                    Y.apply_update(doc, persisted)
                    logger.info("Loaded persisted Yjs doc for '%s' (%d bytes)", table_name, len(persisted))

                # Set up observer to track changes
                self._docs[table_name] = doc

                # Start listening for cross-worker updates
                self._subscribe_table(table_name)

            return self._docs[table_name]

    def remove(self, table_name: str):
        """Remove a Y.Doc (e.g., table archived)."""
        with self._lock:
            self._docs.pop(table_name, None)

    # ----------------------------------------------------------------
    # Sync Protocol Operations
    # ----------------------------------------------------------------

    def handle_step1(self, table_name: str, state_vector: bytes) -> bytes:
        """
        Client sends their state vector. Server responds with missing updates.

        This is the initial sync — client says "I have this state",
        server sends everything the client is missing.
        """
        doc = self.get_or_create(table_name)
        try:
            missing_update = Y.encode_state_as_update(doc, state_vector)
            return missing_update
        except Exception:
            # If state vector is incompatible, send full state
            return Y.encode_state_as_update(doc)

    def apply_update(self, table_name: str, update: bytes, broadcast: bool = True) -> bytes:
        """
        Apply a Yjs update from a client.

        Args:
            table_name: The dynamic table being edited
            update: Raw Yjs update bytes
            broadcast: If True, publish to Redis for cross-worker sync

        Returns:
            The state vector after applying (for sending back to sender)
        """
        doc = self.get_or_create(table_name)

        try:
            Y.apply_update(doc, update)
        except Exception as e:
            logger.error("Failed to apply update for '%s': %s", table_name, e)
            raise

        # Broadcast to other workers via Redis
        if broadcast:
            self._publish_update(table_name, update)

        # Return current state vector so sender can verify
        return Y.encode_state_vector(doc)

    # ----------------------------------------------------------------
    # Cross-Worker Sync (Redis Pub/Sub)
    # ----------------------------------------------------------------

    def _publish_update(self, table_name: str, update: bytes):
        """Publish an update to Redis so other workers can apply it."""
        channel = f"yjs:{table_name}"
        try:
            self._redis.publish(channel, update)
        except Exception as e:
            logger.warning("Redis publish failed for '%s': %s", table_name, e)

    def _subscribe_table(self, table_name: str):
        """Start a Redis Pub/Sub listener for cross-worker Yjs updates."""
        channel = f"yjs:{table_name}"

        # Lazy-init pubsub
        if self._pubsub is None:
            self._pubsub = self._redis.pubsub(ignore_subscribe_messages=True)

        self._pubsub.subscribe(channel)

        # Start listener thread if not already running
        if self._pubsub_thread is None or not self._pubsub_thread.is_alive():
            self._pubsub_thread = threading.Thread(
                target=self._listen_redis,
                daemon=True,
                name="yjs-redis-listener",
            )
            self._pubsub_thread.start()
            logger.info("Started Redis Pub/Sub listener for Yjs updates")

    def _listen_redis(self):
        """
        Background thread: listen for Yjs updates from other workers.

        NOTE: y-py YDoc instances are thread-bound (Rust limitation).
        The listener collects updates in a queue, and they are applied
        on the next access to the doc from the owning thread.

        For production multi-worker: each worker process maintains its
        own in-memory YDoc. The Redis bridge ensures updates propagate, but
        actual application happens when the owning thread accesses the doc.
        """
        pending_updates: dict[str, list[bytes]] = {}

        while True:
            try:
                message = self._pubsub.get_message(timeout=1.0)
                if message is None:
                    # Flush pending updates periodically
                    if pending_updates:
                        with self._lock:
                            for table_name, updates in pending_updates.items():
                                if table_name in self._docs:
                                    for update in updates:
                                        try:
                                            Y.apply_update(self._docs[table_name], update)
                                        except Exception as e:
                                            logger.error("Cross-worker update failed: %s", e)
                        pending_updates.clear()
                    continue

                if message["type"] != "message":
                    continue

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                table_name = channel.replace("yjs:", "")
                update = message["data"]

                # Buffer updates and apply under lock
                if table_name not in pending_updates:
                    pending_updates[table_name] = []
                pending_updates[table_name].append(update)

            except Exception as e:
                logger.error("Redis listener error: %s", e)

    # ----------------------------------------------------------------
    # Persistence (PostgreSQL BYTEA)
    # ----------------------------------------------------------------

    def persist_to_db(self, table_name: str) -> int:
        """
        Persist the current Y.Doc state to PostgreSQL.

        Returns the number of bytes written.
        """
        doc = self._docs.get(table_name)
        if doc is None:
            return 0

        state = Y.encode_state_as_update(doc)

        from .models import DocumentState
        obj, created = DocumentState.objects.update_or_create(
            table_name=table_name,
            defaults={
                "ydoc_state": state,
                "version": (
                    DocumentState.objects.filter(table_name=table_name).count() + 1
                ),
            },
        )
        logger.debug("Persisted Yjs doc '%s': %d bytes (v%d)", table_name, len(state), obj.version)
        return len(state)

    def _load_from_db(self, table_name: str) -> Optional[bytes]:
        """Load persisted Y.Doc state from PostgreSQL."""
        from .models import DocumentState
        try:
            doc_state = DocumentState.objects.get(table_name=table_name)
            return bytes(doc_state.ydoc_state)
        except DocumentState.DoesNotExist:
            return None


# Global singleton
yjs_manager = YjsDocManager()
