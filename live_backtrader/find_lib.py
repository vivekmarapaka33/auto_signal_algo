import sys
import os

try:
    import BinaryOptionsToolsV2
    print(f"Location: {os.path.dirname(BinaryOptionsToolsV2.__file__)}")
except ImportError:
    print("Not found")
except Exception as e:
    print(f"Error: {e}")
