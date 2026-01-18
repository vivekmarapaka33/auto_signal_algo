import uvicorn
import os
import json
import asyncio
from typing import List
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.core.config import settings
# from app.api.endpoints import router as api_router
from app.engine.live import get_live_engine

# Initialize App
app = FastAPI(title=settings.PROJECT_NAME)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

# API Router
# API Router
from app.api.strategy_api import router as strategy_router
from app.api.endpoints import router as endpoints_router

app.include_router(strategy_router, prefix="/api")
app.include_router(endpoints_router, prefix="/api")

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except:
                pass

manager = ConnectionManager()

# --- UI Routes ---
@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/live")
def live_page(request: Request):
    return templates.TemplateResponse("live.html", {"request": request})

@app.get("/strategy")
def strategy_page(request: Request):
    return templates.TemplateResponse("strategy.html", {"request": request})

@app.get("/account")
def account_page(request: Request):
    return templates.TemplateResponse("account.html", {"request": request})

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# --- WebSocket Route ---
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Get Main Loop for Threadsafe calling
    loop = asyncio.get_running_loop()
    engine = get_live_engine(manager.broadcast, loop)

    # Send current state on connect
    state = engine.get_state()
    if state['running']:
        await websocket.send_text(json.dumps(state))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("command") == "start":
                asset = message.get("asset", "EURUSD_otc")
                timeframe = message.get("timeframe", 5)
                engine.start(asset=asset, timeframe=timeframe)
            elif message.get("command") == "stop":
                engine.stop()
            elif message.get("command") == "start_forward_test":
                asset = message.get("asset", "EURUSD_otc")
                timeframe = message.get("timeframe", 60)
                expiry = message.get("expiry", 60)
                mode = message.get("mode", "FORWARD_TEST")
                code = message.get("code")
                risk = message.get("risk_percent", 1.0)
                martingale = message.get("martingale_multiplier", 2.0)
                engine.start(asset=asset, timeframe=timeframe, expiry=expiry, mode=mode, code=code, risk_percent=risk, martingale_multiplier=martingale)
            elif message.get("command") == "toggle_auto_select":
                enabled = message.get("enabled", False)
                engine.toggle_auto_select(enabled)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WS Error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    print("🚀 Starting Unified Live Backtrader Platform...")
    print(f"📡 Serving at http://localhost:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
