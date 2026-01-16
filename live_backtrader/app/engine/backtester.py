import backtrader as bt
import pandas as pd
from app.engine.feeds import PandasData
import logging
import traceback
import sys
from io import StringIO, BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64

logger = logging.getLogger("Backtester")

class BacktestResult:
    def __init__(self):
        self.log = []
        self.trades = []
        self.initial_value = 0
        self.final_value = 0
        self.win_rate = 0.0

class Backtester:
    def __init__(self, data_list: list, strategy_code: str, strategy_params: dict = None):
        self.data_list = data_list
        self.strategy_code = strategy_code
        self.strategy_params = strategy_params or {}
        
    def run(self):
        cerebro = bt.Cerebro()
        
        # 1. Prepare Data
        if not self.data_list:
            raise ValueError("No data provided for backtest")
            
        df = pd.DataFrame(self.data_list)
        
        # Ensure standard columns exist
        if 'volume' not in df.columns:
            df['volume'] = 0
            
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        # Explicitly tell Backtrader to look for these columns
        # Note: PandasData uses None for datetime to use index
        data_feed = PandasData(dataname=df, datetime=None, volume='volume', openinterest=-1)
        cerebro.adddata(data_feed)
        
        # 2. Load Strategy from Code String
        try:
            # Create a namespace for execution
            namespace = {}
            # Inject backtrader as 'bt'
            namespace['bt'] = bt
            
            # Exec the class definition
            exec(self.strategy_code, namespace)
            
            # Find the strategy class (assuming it inherits from bt.Strategy)
            StrategyClass = None
            for name, obj in namespace.items():
                if isinstance(obj, type) and issubclass(obj, bt.Strategy) and obj is not bt.Strategy:
                    StrategyClass = obj
                    break
            
            if not StrategyClass:
                raise ValueError("No class inheriting from bt.Strategy found in code")
                
            # Add strategy to cerebro
            cerebro.addstrategy(StrategyClass, **self.strategy_params)
            
        except Exception as e:
            logger.error(f"Strategy Compilation Failed: {e}")
            return {"error": str(e), "traceback": traceback.format_exc()}

        # 3. Configure Broker (Binary Options Login - Fixed Payout)
        # Standard Backtrader doesn't support Binary Options out of box (CommInfo needed)
        # We simulate by checking win/loss in the strategy or using a custom analyzer
        cerebro.broker.setcash(1000.0)
        
        # 4. Run
        logger.info("Starting Backtest...")
        try:
            # Capture stdout
            old_stdout = sys.stdout
            sys.stdout = mystdout = StringIO()
            
            strats = cerebro.run()
            
            sys.stdout = old_stdout
            log_output = mystdout.getvalue()
            
            # 5. Extract Results
            strat = strats[0]
            final_value = cerebro.broker.getvalue()
            
            # 6. Generate Plot
            plot_image = None
            try:
                # Plot returns a list of lists of figures
                figures = cerebro.plot(style='candlestick', barup='green', bardown='red')
                if figures and figures[0]:
                    fig = figures[0][0]
                    # Save to buffer
                    buf = BytesIO()
                    fig.savefig(buf, format='png', bbox_inches='tight')
                    buf.seek(0)
                    plot_image = base64.b64encode(buf.read()).decode('utf-8')
                    plt.close(fig)
            except Exception as e:
                logger.error(f"Plot generation failed: {e}")
            
            return {
                "initial_value": 1000.0,
                "final_value": final_value,
                "log": log_output,
                "trades": [], # Extract trades from analyzer if added
                "plot_image": plot_image
            }
            
        except Exception as e:
            logger.error(f"Backtest Runtime Error: {e}")
            return {"error": str(e), "traceback": traceback.format_exc()}
