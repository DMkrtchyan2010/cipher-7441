from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from engine import run_bb84_simulation
import base64
import os

app = FastAPI(title="Cipher-7441 Interactive Mesh", version="2.3.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

class ConnectionManager:
    def __init__(self): self.connections: list[WebSocket] = []
    async def connect(self, ws: WebSocket): await ws.accept(); self.connections.append(ws)
    def disconnect(self, ws: WebSocket): self.connections.remove(ws)
    async def broadcast(self, msg: str):
        for conn in self.connections: await conn.send_text(msg)

manager = ConnectionManager()

class TransmissionRequest(BaseModel):
    num_photons: int = 32
    intercept_rate_eve1: float = 0.0
    intercept_rate_eve2: float = 0.0
    threshold: float = 0.11
    message: str = ""

@app.websocket("/ws/mesh")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(ws)

@app.post("/api/transmit")
def transmit(req: TransmissionRequest):
    res = run_bb84_simulation(
        num_photons=req.num_photons, 
        intercept_rate_eve1=req.intercept_rate_eve1,
        intercept_rate_eve2=req.intercept_rate_eve2,
        threshold=req.threshold
    )
    if res["secure"] and req.message:
        key_bytes = res["derived_key"].encode('utf-8')
        msg_bytes = req.message.encode('utf-8')
        res["ciphertext"] = base64.b64encode(bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(msg_bytes)])).decode('utf-8')
        res["plaintext"] = req.message
    else:
        res["ciphertext"] = "REJECTED_BREACH_PANIC_TRIGGERED"
        res["plaintext"] = None
    return res

# Root endpoint loads your tactical index.html boot launcher automatically
@app.get("/")
def read_root():
    return FileResponse(os.path.join("static", "index.html"))

# Mount static folder so /static/alice.html, etc. work seamlessly
app.mount("/static", StaticFiles(directory="static"), name="static")