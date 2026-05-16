"""
unity_bridge.py — Xoltra Unity WebSocket Bridge
Async WebSocket server that sits between Flask and Unity.

Architecture:
  Flask thread  → asyncio queue → WebSocket → Unity
  Unity         → WebSocket    → event_handlers (registered by Flask routes)

Usage (started once in app.py):
    import unity_bridge
    unity_bridge.start_bridge()          # spins up thread
    unity_bridge.send(SimCommand(...))   # thread-safe, non-blocking
    unity_bridge.on_event("node_clicked", handler_fn)
"""

import asyncio
import json
import logging
import threading
import queue
from typing import Callable, Dict, Optional, Set
from simulation_types import SimCommand, EventType

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════
# BRIDGE STATE
# ═══════════════════════════════════════════════════

BRIDGE_HOST = "0.0.0.0"
BRIDGE_PORT = 5002

_loop:          Optional[asyncio.AbstractEventLoop] = None
_thread:        Optional[threading.Thread]          = None
_cmd_queue:     queue.Queue                         = queue.Queue()
_connected:     Set                                 = set()          # active WS connections
_event_handlers: Dict[str, list]                   = {}             # event_type → [fn, ...]
_bridge_ready   = threading.Event()


# ═══════════════════════════════════════════════════
# PUBLIC API  (called from Flask — any thread)
# ═══════════════════════════════════════════════════

def start_bridge():
    """
    Start the WebSocket bridge in a background daemon thread.
    Call once from app.py before the Flask server starts.
    Thread-safe and idempotent.
    """
    global _thread, _loop

    if _thread and _thread.is_alive():
        return

    _thread = threading.Thread(target=_run_loop, name="unity-bridge", daemon=True)
    _thread.start()
    _bridge_ready.wait(timeout=3.0)
    logger.info(f"[Bridge] WebSocket server on ws://{BRIDGE_HOST}:{BRIDGE_PORT}")


def send(command: SimCommand):
    """
    Queue a command for delivery to Unity. Non-blocking.
    Commands are delivered in order; dropped if no Unity client is connected.
    """
    _cmd_queue.put_nowait(command)


def send_many(commands: list):
    """Queue multiple commands atomically (preserves order)."""
    for cmd in commands:
        _cmd_queue.put_nowait(cmd)


def on_event(event_type: str, handler: Callable[[dict], None]):
    """
    Register a handler for a Unity event type.
    Handler receives the full payload dict.
    Multiple handlers per event type are supported.
    """
    _event_handlers.setdefault(event_type, []).append(handler)


def is_unity_connected() -> bool:
    """Returns True if at least one Unity client is connected."""
    return len(_connected) > 0


def get_status() -> dict:
    return {
        "connected":    is_unity_connected(),
        "clients":      len(_connected),
        "queue_depth":  _cmd_queue.qsize(),
        "bridge_port":  BRIDGE_PORT,
    }


# ═══════════════════════════════════════════════════
# ASYNC INTERNALS
# ═══════════════════════════════════════════════════

def _run_loop():
    """Entry point for the bridge thread."""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_serve())


async def _serve():
    """Start WebSocket server and drain the command queue."""
    try:
        import websockets
    except ImportError:
        logger.error("[Bridge] 'websockets' package not installed. Run: pip install websockets")
        _bridge_ready.set()
        return

    _bridge_ready.set()

    async with websockets.serve(
        _handle_connection,
        BRIDGE_HOST,
        BRIDGE_PORT,
        ping_interval=20,
        ping_timeout=10,
    ):
        # Drain command queue → connected clients
        while True:
            await _drain_queue()
            await asyncio.sleep(0.016)   # ~60 Hz flush cycle


async def _drain_queue():
    """Forward all pending commands to every connected Unity client."""
    if not _connected:
        return   # keep commands in queue until Unity connects

    batch = []
    try:
        while True:
            batch.append(_cmd_queue.get_nowait())
    except queue.Empty:
        pass

    if not batch:
        return

    import websockets
    dead = set()
    for ws in list(_connected):
        for cmd in batch:
            try:
                await ws.send(cmd.to_json())
            except websockets.exceptions.ConnectionClosed:
                dead.add(ws)
                break

    _connected -= dead
    if dead:
        logger.info(f"[Bridge] Removed {len(dead)} closed connection(s)")


async def _handle_connection(websocket, path="/"):
    """Handle a new Unity client connection."""
    client_addr = websocket.remote_address
    logger.info(f"[Bridge] Unity connected from {client_addr}")
    _connected.add(websocket)

    # Send a handshake so Unity knows the bridge version
    await websocket.send(json.dumps({
        "type":    "handshake",
        "version": "1.0",
        "payload": {}
    }))

    try:
        async for raw_message in websocket:
            _dispatch_event(raw_message)
    except Exception as e:
        logger.debug(f"[Bridge] Connection closed: {e}")
    finally:
        _connected.discard(websocket)
        logger.info(f"[Bridge] Unity disconnected ({client_addr})")


def _dispatch_event(raw: str):
    """Parse a Unity→Python event and call registered handlers."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"[Bridge] Malformed event: {raw[:100]}")
        return

    event_type = msg.get("type", "")
    payload    = msg.get("payload", {})

    handlers = _event_handlers.get(event_type, [])
    for fn in handlers:
        try:
            fn(payload)
        except Exception as e:
            logger.warning(f"[Bridge] Handler error for '{event_type}': {e}")

    if not handlers:
        logger.debug(f"[Bridge] Unhandled event: {event_type}")
