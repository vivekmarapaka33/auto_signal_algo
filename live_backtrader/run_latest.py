import asyncio
import websockets
import json
import logging
from app.core.database import SessionLocal, Strategy

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("TestRunner")

async def run_latest_strategy():
    # 1. Fetch Latest Strategy from DB
    db = SessionLocal()
    try:
        strategy = db.query(Strategy).order_by(Strategy.id.desc()).first()
        if not strategy:
            logger.error("No strategies found in database!")
            return
        
        logger.info(f"Loaded Strategy: {strategy.name} (ID: {strategy.id})")
        code = strategy.code
    finally:
        db.close()

    # 2. Connect to WebSocket
    uri = "ws://localhost:8000/ws/live"
    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"Connected to {uri}")

            # 3. Send Start Command
            start_payload = {
                "command": "start_forward_test",
                "asset": "EURUSD_otc", # Default
                "timeframe": 60,       # Default
                "expiry": 60,          # Default
                "risk_percent": 1.0,
                "martingale_multiplier": 2.0,
                "code": code
            }
            
            await websocket.send(json.dumps(start_payload))
            logger.info("Sent 'start_forward_test' command with loaded code.")

            # 4. Listen for Confirmation/Logs (briefly)
            logger.info("Listening for updates (Press Ctrl+C to stop monitoring)...")
            try:
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    if data.get("type") == "log":
                        print(f"[{data.get('color', 'TERM')}] {data.get('message')}")
                    elif data.get("type") == "error":
                        print(f"[ERROR] {data.get('message')}")
                        
            except KeyboardInterrupt:
                logger.info("Stopping monitor...")
                
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        logger.info("Ensure the server (main.py) is running on localhost:8000")

if __name__ == "__main__":
    asyncio.run(run_latest_strategy())
