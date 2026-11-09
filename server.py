import base64
import json
import logging
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global storage for active eavesdropper rates set dynamically by Eve's panel
active_eve_config = {
    "intercept_rate_eve1": 0.00,
    "intercept_rate_eve2": 0.00,
}


class TransmissionRequest(BaseModel):
  num_photons: int
  threshold: float = 0.11
  message: str


def run_bb84_simulation(
    num_photons=32,
    intercept_rate_eve1=0.0,
    intercept_rate_eve2=0.0,
    threshold=0.11,
):
  bases = ["RECTILINEAR", "DIAGONAL"]
  photon_logs = []
  alice_bits = []
  sifted_matches_count = 0
  errors = 0

  for i in range(num_photons):
    a_bit = random.randint(0, 1)
    a_basis = random.choice(bases)
    alice_bits.append(a_bit)

    # Eve interception checks based on active wiretap rates
    eve1_int = random.random() < intercept_rate_eve1
    eve2_int = random.random() < intercept_rate_eve2

    polarization = (
        "0°" if a_bit == 0 and a_basis == "RECTILINEAR" else "90°"
    )
    if a_basis == "DIAGONAL":
      polarization = "45°" if a_bit == 0 else "135°"

    # If Eve doesn't intercept, Bob matches Alice's basis perfectly (0% baseline QBER)
    b_basis = a_basis if (not eve1_int and not eve2_int) else random.choice(bases)
    b_bit = a_bit

    eve_action = "NONE"
    if eve1_int or eve2_int:
      eve_action = "INTERCEPT_COLLAPSE"
      if b_basis != a_basis:
        b_bit = random.randint(0, 1)

    matched = a_basis == b_basis
    is_error = False
    if matched:
      sifted_matches_count += 1
      if a_bit != b_bit:
        errors += 1
        is_error = True

    photon_logs.append({
        "id": i + 1,
        "alice_bit": a_bit,
        "alice_basis": a_basis,
        "bob_bit": b_bit,
        "bob_basis": b_basis,
        "polarization": polarization,
        "matched": matched,
        "eve1_intercepted": eve1_int,
        "eve2_intercepted": eve2_int,
        "eve_action": eve_action,
        "error": is_error,
    })

  qber_ratio = errors / max(1, sifted_matches_count)
  qber_percent = round(qber_ratio * 100, 2)
  secure = qber_percent <= (threshold * 100)

  derived_key = (
      "".join([str(b) for b in alice_bits[:32]]) if secure else "BREACH_LOCKED"
  )

  return {
      "secure": secure,
      "qber": qber_percent,
      "sifted_matches": f"{sifted_matches_count} / {num_photons}",
      "derived_key": derived_key,
      "photon_logs": photon_logs,
  }


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


@app.get("/bob", response_class=HTMLResponse)
def get_bob():
  with open("static/bob.html", "r", encoding="utf-8") as f:
    return f.read()


@app.post("/api/transmit")
def transmit(req: TransmissionRequest):
  try:
    res = run_bb84_simulation(
        num_photons=req.num_photons,
        intercept_rate_eve1=active_eve_config["intercept_rate_eve1"],
        intercept_rate_eve2=active_eve_config["intercept_rate_eve2"],
        threshold=req.threshold,
    )
  except Exception as e:
    logger.error(f"Simulation engine error: {str(e)}")
    return {
        "secure": False,
        "qber": 0.0,
        "sifted_matches": "0 / 32",
        "derived_key": "ERROR_FALLBACK",
        "photon_logs": [],
        "plaintext": req.message,
    }

  res["plaintext"] = req.message
  return res


@app.websocket("/ws/mesh")
@app.websocket("/ws/mesh/")
async def websocket_endpoint(ws: WebSocket):
  await manager.connect(ws)
  try:
    while True:
      data = await ws.receive_text()
      packet = json.loads(data)

      # Update global wiretap rates when Eve adjusts sliders and clicks deploy
      if packet.get("type") == "EVE_PROBE":
        active_eve_config["intercept_rate_eve1"] = packet.get(
            "intercept_rate_eve1", 0.00
        )
        active_eve_config["intercept_rate_eve2"] = packet.get(
            "intercept_rate_eve2", 0.00
        )
        logger.info(f"Updated active Eve config via wiretap: {active_eve_config}")

      # Broadcast all mesh actions (Alice emissions, Eve rate updates, panic triggers) to all nodes
      await manager.broadcast(data)

  except WebSocketDisconnect:
    manager.disconnect(ws)
  except Exception:
    manager.disconnect(ws)
