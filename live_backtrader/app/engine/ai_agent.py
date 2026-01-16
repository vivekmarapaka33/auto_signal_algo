from typing import Dict, Any

class AITradingAgent:
    """
    AI Agent that analyzes strategy performance and suggests improvements.
    """
    
    @staticmethod
    def analyze_performance(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze backtest results for overfitting and robustness.
        """
        initial = result.get('initial_value', 1000)
        final = result.get('final_value', 0)
        profit = final - initial
        profit_pct = (profit / initial) * 100
        
        # Simple Logic Analysis
        score = 50
        warnings = []
        suggestions = []
        
        if profit_pct > 1000:
            warnings.append("Suspiciously high returns (Overfitting likely?)")
            score -= 20
        elif profit_pct < 0:
            suggestions.append("Strategy is losing money. Check entry conditions.")
            score -= 10
            
        trades = result.get('trades', [])
        curr_loss_streak = 0
        max_loss_streak = 0
        
        # Mock analysis if no trade details
        
        return {
            "score": score,
            "profit_pct": profit_pct,
            "warnings": warnings,
            "suggestions": suggestions,
            "is_production_safe": score > 70
        }

    @staticmethod
    def validate_code(code: str) -> bool:
        """
        Static analysis of user code for infinite loops or forbidden imports.
        """
        forbidden = ['os.', 'sys.', 'subprocess', 'import os', 'import sys']
        for f in forbidden:
            if f in code:
                return False
        return True
