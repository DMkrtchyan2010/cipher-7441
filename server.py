import base64
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from engine import run_bb84_simulation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Cipher-7441 Interactive Mesh", version="2.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:

  def __init__(self):
    self.connections: list[WebSocket] = []

  async def connect(self, ws: WebSocket):
    await ws.accept()
    self.connections.append(ws)
    logger.info(f"Client connected. Total active: {len(self.connections)}")

  def disconnect(self, ws: WebSocket):
    if ws in self.connections:
      self.connections.remove(ws)
      logger.info(f"Client disconnected. Total active: {len(self.connections)}")

  async def broadcast(self, msg: str):
    for conn in self.connections:
      try:
        await conn.send_text(msg)
      except Exception as e:
        logger.error(f"Broadcast error: {e}")


manager = ConnectionManager()


class TransmissionRequest(BaseModel):
  num_photons: int = 32
  intercept_rate_eve1: float = 0.0
  intercept_rate_eve2: float = 0.0
  threshold: float = 0.11
  message: str = ""


# WebSocket Endpoint supporting exact paths and trailing slashes
@app.websocket("/ws/mesh")
@app.websocket("/ws/mesh/")
async def websocket_endpoint(ws: WebSocket):
  logger.info("Incoming WebSocket connection handshake at /ws/mesh")
  await manager.connect(ws)
  try:
    while True:
      data = await ws.receive_text()
      await manager.broadcast(data)
  except WebSocketDisconnect:
    logger.info("WebSocket client disconnected normally")
    manager.disconnect(ws)
  except Exception as e:
    logger.error(f"WebSocket exception: {e}")
    manager.disconnect(ws)

@app.post("/api/transmit")
def transmit(req: TransmissionRequest):
  res = run_bb84_simulation(
      num_photons=req.num_photons,
      intercept_rate_eve1=req.intercept_rate_eve1,
      intercept_rate_eve2=req.intercept_rate_eve2,
      threshold=req.threshold,
  )

  if res["secure"] and req.message:
    raw_key = res.get("derived_key", "FALLBACK_KEY_7441")
    key_bytes = str(raw_key).encode("utf-8")
    msg_bytes = req.message.encode("utf-8")  # Uses the exact current message bytes

    # Strict byte-for-byte XOR encryption matching message length exactly
    encrypted_bytes = bytes(
        [b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(msg_bytes)]
    )
    res["ciphertext"] = base64.b64encode(encrypted_bytes).decode("utf-8")
    res["plaintext"] = req.message
  else:
    res["ciphertext"] = "REJECTED_BREACH_PANIC_TRIGGERED"
    res["plaintext"] = None

  return res


@app.get("/")
def read_root():
  return FileResponse(os.path.join("static", "index.html"))


# Explicit route helpers for individual node views if accessed directly
@app.get("/alice.html")
def read_alice():
  return FileResponse(os.path.join("static", "alice.html"))


@app.get("/bob.html")
def read_bob():
  return FileResponse(os.path.join("static", "bob.html"))


@app.get("/eve.html")
def read_eve():
  return FileResponse(os.path.join("static", "eve.html"))


# Mount static assets LAST so explicit API/WebSocket routes take priority
app.mount("/static", StaticFiles(directory="static"), name="static")
