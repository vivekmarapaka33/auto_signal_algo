from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import os
import json

from ..database.database import SessionLocal, Strategy, Account, Trade, StrategyAccount
from ..core.pocket_client import PocketClient

from .strategies_api import router as strategies_router

app = FastAPI()

from ..services.background_service import service as background_service
import asyncio

@app.on_event("startup")
async def startup_event():
    print("HELLO? Startup event triggered!")
    asyncio.create_task(background_service.start())

@app.on_event("shutdown")
async def shutdown_event():
    await background_service.stop()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(strategies_router)

# Static Files
# We assume 'static' folder is adjacent to 'api.py' (i.e. inside 'web/')
# But relative to this file, it is just 'static' folder if we run from package
# Using absolute path for safety
current_dir = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(current_dir, "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic Models
class AccountCreate(BaseModel):
    name: str
    ssid: str

class AccountResponse(BaseModel):
    id: int
    name: str
    ssid: str
    balance: float
    is_active: bool

class StrategyCreate(BaseModel):
    name: str
    config: dict

class SettingsUpdate(BaseModel):
    trade_amount: float
    max_drawdown: float
    stop_loss_enabled: bool
    telegram_alerts: bool
    email_summary: bool

# Settings Storage
SETTINGS_FILE = os.path.join(current_dir, "settings.json")

def load_settings_file():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {
        "trade_amount": 10,
        "max_drawdown": 50,
        "stop_loss_enabled": True,
        "telegram_alerts": True,
        "email_summary": False
    }

def save_settings_file(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

@app.get("/settings")
def get_settings():
    return load_settings_file()

@app.put("/settings")
def update_settings(settings: SettingsUpdate):
    data = settings.dict()
    save_settings_file(data)
    return {"status": "updated", "settings": data}

# --- Routes ---

@app.on_event("startup")
async def startup_event():
    print("HELLO? Startup event triggered!")
    asyncio.create_task(background_service.start())

@app.get("/")
def read_root():
    return {"status": "ok", "system": "AutoSignal Algo"}

# Accounts
@app.get("/accounts", response_model=List[AccountResponse])
def get_accounts(db: Session = Depends(get_db)):
    return db.query(Account).all()

@app.post("/accounts")
async def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    # Check if exists
    existing = db.query(Account).filter(Account.name == account.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Account with this name already exists")
    
    # Pre-validate
    print(f"DEBUG: Validating SSID for account {account.name}...")
    is_mock = account.ssid.startswith("mock")
    client = PocketClient(ssid=account.ssid, is_dry_run=is_mock)
    success = await client.connect()
    print(f"DEBUG: Connect result: {success}")
    
    if not success:
        print("DEBUG: Connection failed.")
        raise HTTPException(status_code=400, detail="Could not connect to broker with this SSID")
        
    bal = await client.get_balance()
    print(f"DEBUG: Fetched balance: {bal}")
    await client.disconnect()
    
    if bal is None:
         print("DEBUG: Balance is None.")
         raise HTTPException(status_code=400, detail="Connected but failed to fetch balance. Check SSID.")

    db_acc = Account(
        name=account.name, 
        ssid=account.ssid,
        balance=bal,
        is_active=True
    )
    db.add(db_acc)
    db.commit()
    db.refresh(db_acc)
    return db_acc

@app.put("/accounts/{account_id}")
async def update_account(account_id: int, account: AccountCreate, db: Session = Depends(get_db)):
    db_acc = db.query(Account).filter(Account.id == account_id).first()
    if not db_acc:
        raise HTTPException(status_code=404, detail="Account not found")
        
    # Check name uniqueness if changed
    if account.name != db_acc.name:
        existing = db.query(Account).filter(Account.name == account.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Account Name must be unique")
    
    # Check SSID validity if changed
    if account.ssid != db_acc.ssid:
        print(f"DEBUG: Validating new SSID for account {account.name}...")
        client = PocketClient(ssid=account.ssid)
        if await client.connect():
             bal = await client.get_balance()
             print(f"DEBUG: Fetched new balance: {bal}")
             await client.disconnect()
             if bal is not None:
                 db_acc.balance = bal
                 db_acc.is_active = True
             else:
                 print("DEBUG: Balance is None.")
                 raise HTTPException(status_code=400, detail="Could not fetch balance for new SSID")
        else:
             print("DEBUG: Connection failed.")
             raise HTTPException(status_code=400, detail="Could not connect with new SSID")
             
    db_acc.name = account.name
    db_acc.ssid = account.ssid
    
    db.commit()
    db.refresh(db_acc)
    return db_acc

@app.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    db_acc = db.query(Account).filter(Account.id == account_id).first()
    if not db_acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Optional: Delete linked strategy_accounts
    db.query(StrategyAccount).filter(StrategyAccount.account_id == account_id).delete()
    
    db.delete(db_acc)
    db.commit()
    return {"status": "deleted", "id": account_id}

@app.post("/accounts/{account_id}/validate")
async def validate_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
        
    client = PocketClient(ssid=acc.ssid)
    success = await client.connect()
    
    if success:
        bal = await client.get_balance()
        if bal is not None:
             acc.balance = bal
             acc.is_active = True
             db.commit()
             await client.disconnect()
             return {"status": "valid", "balance": bal}
    
    acc.is_active = False
    db.commit()
    raise HTTPException(status_code=400, detail="Failed to connect to broker")



@app.post("/strategies/{strategy_id}/link/{account_id}")
def link_account(strategy_id: int, account_id: int, db: Session = Depends(get_db)):
    # Check existence
    strat = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not strat or not acc:
        raise HTTPException(status_code=404, detail="Strategy or Account not found")
        
    # Create link if not exists
    link = db.query(StrategyAccount).filter(
        StrategyAccount.strategy_id == strategy_id,
        StrategyAccount.account_id == account_id
    ).first()
    
    if not link:
        link = StrategyAccount(strategy_id=strategy_id, account_id=account_id)
        db.add(link)
        db.commit()
        
    return {"status": "linked"}

# WebSocket
from .websocket_server import manager

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep alive / listen for commands from frontend if needed
            data = await websocket.receive_text()
            # echo or process
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Trades
@app.get("/trades")
def get_trades(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Trade).order_by(Trade.open_time.desc()).limit(limit).all()
