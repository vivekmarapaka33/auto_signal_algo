from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
import os

from app.core.database import get_db, Strategy

router = APIRouter()

from datetime import datetime
import uuid

class StrategySaveRequest(BaseModel):
    name: Optional[str] = None
    code: str

class StrategyResponse(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    
    class Config:
        from_attributes = True

@router.post("/strategy/save")
async def save_strategy(data: StrategySaveRequest, db: Session = Depends(get_db)):
    try:
        print(f"DEBUG: Save Request Received. Name: {data.name}, Code Len: {len(data.code)}")
        
        # Handle missing name (Caching issue or old frontend)
        strategy_name = data.name
        if not strategy_name:
            strategy_name = f"Untitled_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            print(f"DEBUG: Name missing, defaulting to {strategy_name}")

        # Check if exists
        existing = db.query(Strategy).filter(Strategy.name == strategy_name).first()
        if existing:
            existing.code = data.code
            db.commit()
            return {"success": True, "message": f"Strategy '{strategy_name}' updated", "id": existing.id}
        else:
            new_strategy = Strategy(name=strategy_name, code=data.code)
            db.add(new_strategy)
            db.commit()
            db.refresh(new_strategy)
            return {"success": True, "message": f"Strategy '{strategy_name}' created", "id": new_strategy.id}

    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/strategy/list", response_model=List[StrategyResponse])
async def list_strategies(db: Session = Depends(get_db)):
    strategies = db.query(Strategy).all()
    # We return basic info, code is optional but included here for simplicity
    return strategies

@router.get("/strategy/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy

@router.delete("/strategy/{strategy_id}")
async def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    db.delete(strategy)
    db.commit()
    return {"success": True}

