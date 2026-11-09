import base64
import json
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
# (Import your run_bb84_simulation engine function here)

app = FastAPI()

# Mount static directory for HTML/JS frontends
app.mount("/static", StaticFiles(directory="static"), name="static")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global storage for active eavesdropper rates set dynamically by Eve's panel
active_eve_config = {
    "intercept_rate_eve1": 0.30,
    "intercept_rate_eve2": 0.00,
}


class TransmissionRequest(BaseModel):
  num_photons: int
  threshold: float = 0.11
  message: str


class ConnectionManager:

  def __init__(self):
    self.active_connections: list[WebSocket] = []

  async def connect(self, websocket: WebSocket):
    await websocket.accept()
    self.active_connections.append(websocket)

  def disconnect(self, websocket: WebSocket):
    if websocket in self.active_connections:
      self.active_connections.remove(websocket)

  async def broadcast(self, message: str):
    for connection in self.active_connections:
      try:
        await connection.send_text(message)
      except Exception:
        pass


manager = ConnectionManager()


@app.get("/alice", response_class=HTMLResponse)
def get_alice():
  with open("static/alice.html", "r", encoding="utf-8") as f:
    return f.read()


@app.get("/eve", response_class=HTMLResponse)
def get_eve():
  with open("static/eve.html", "r", encoding="utf-8") as f:
    return f.read()


@app.post("/api/transmit")
def transmit(req: TransmissionRequest):
  # Uses the live intercept rates configured by Eve via WebSocket
  res = run_bb84_simulation(
      num_photons=req.num_photons,
      intercept_rate_eve1=active_eve_config["intercept_rate_eve1"],
      intercept_rate_eve2=active_eve_config["intercept_rate_eve2"],
      threshold=req.threshold,
  )

  if res["secure"] and req.message:
    raw_key = res.get("derived_key", "FALLBACK_KEY_7441")
    if not raw_key:
      raw_key = "FALLBACK_KEY_7441"

    key_bytes = str(raw_key).encode("utf-8")
    msg_bytes = req.message.encode("utf-8")

    encrypted_bytes = bytes(
        [b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(msg_bytes)]
    )
    res["ciphertext"] = base64.b64encode(encrypted_bytes).decode("utf-8")
    res["plaintext"] = req.message
  else:
    res["ciphertext"] = "REJECTED_BREACH_PANIC_TRIGGERED"
    res["plaintext"] = None

  return res


@app.websocket("/ws/mesh")
@app.websocket("/ws/mesh/")
async def websocket_endpoint(ws: WebSocket):
  await manager.connect(ws)
  try:
    while True:
      data = await ws.receive_text()
      packet = json.loads(data)
      # Catch Eve's probe updates and sync global engine rates
      if packet.get("type") == "EVE_PROBE":
        active_eve_config["intercept_rate_eve1"] = packet.get(
            "intercept_rate_eve1", 0.30
        )
        active_eve_config["intercept_rate_eve2"] = packet.get(
            "intercept_rate_eve2", 0.00
        )
        logger.info(f"Updated active Eve config: {active_eve_config}")
      await manager.broadcast(data)
  except WebSocketDisconnect:
    manager.disconnect(ws)
  except Exception:
    manager.disconnect(ws)
