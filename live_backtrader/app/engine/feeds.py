import backtrader as bt
from datetime import datetime

class PandasData(bt.feeds.PandasData):
    """
    Pandas DataFeed for Backtrader
    """
    params = (
        ('datetime', 'time'),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),
    )

class DictListFeed(bt.feeds.PandasData):
    """
    Convert List of Dicts to DataFrame for Backtrader
    """
    # ... Helper to convert list[dict] to pandas df then to feed ...
    pass
