"""
WebSocket consumer for Yjs-powered real-time table collaboration.

Protocol: Yjs Sync Protocol over WebSocket

Message Types (first byte identifies type):
  0x00 — SyncStep1: Client → Server (state vector)
  0x01 — SyncStep2: Server → Client (missing updates)
  0x02 — SyncUpdate: Bidirectional (document update)

Connection flow:
  1. Client connects with JWT token in query string
  2. Server authenticates, joins the room group
  3. Client sends SyncStep1 (0x00 + state_vector)
  4. Server responds with SyncStep2 (0x01 + missing_updates)
  5. Ongoing: bidirectional SyncUpdate (0x02 + update_bytes)
"""
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

# Yjs sync protocol message types
MSG_SYNC_STEP1 = 0  # Client → Server: state vector
MSG_SYNC_STEP2 = 1  # Server → Client: diff update
MSG_SYNC_UPDATE = 2  # Bidirectional: document update


class YjsCollaborationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for Yjs collaborative editing on a dynamic table."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.table_name: str = ""
        self.room_group_name: str = ""
        self.user_id: str = ""

    async def connect(self):
        self.table_name = self.scope["url_route"]["kwargs"]["table_name"]
        self.room_group_name = f"yjs_table_{self.table_name}"

        user = self.scope.get("user")
        if user is None or user.is_anonymous:
            await self.close(code=4001)
            return

        self.user_id = str(user.pk)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        logger.info("Yjs connected: user=%s table=%s", self.user_id, self.table_name)

    async def disconnect(self, close_code):
        if self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        logger.info("Yjs disconnected: user=%s table=%s", self.user_id, self.table_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming Yjs binary messages."""
        if bytes_data is None or len(bytes_data) < 1:
            return

        msg_type = bytes_data[0]
        payload = bytes_data[1:]

        if msg_type == MSG_SYNC_STEP1:
            await self._handle_sync_step1(payload)
        elif msg_type == MSG_SYNC_UPDATE:
            await self._handle_sync_update(payload)

    async def _handle_sync_step1(self, state_vector: bytes):
        """Client sends state vector → server returns missing updates."""
        try:
            from .yjs_service import yjs_manager
            missing = await sync_to_async(yjs_manager.handle_step1)(
                self.table_name, state_vector
            )
            await self.send(bytes_data=bytes([MSG_SYNC_STEP2]) + missing)
            logger.debug("Step1→Step2: %d bytes for table=%s", len(missing), self.table_name)
        except Exception as e:
            logger.error("Step1 error table=%s: %s", self.table_name, e)

    async def _handle_sync_update(self, update: bytes):
        """Apply update to server doc and broadcast to all other clients."""
        try:
            from .yjs_service import yjs_manager
            await sync_to_async(yjs_manager.apply_update)(
                self.table_name, update, broadcast=True
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "yjs.relay_update",
                    "update": update,
                    "sender_channel": self.channel_name,
                },
            )
        except Exception as e:
            logger.error("Update error table=%s: %s", self.table_name, e)

    async def yjs_relay_update(self, event: dict):
        """Relay update from another client (skip self)."""
        if event.get("sender_channel") == self.channel_name:
            return
        await self.send(bytes_data=bytes([MSG_SYNC_UPDATE]) + event["update"])
