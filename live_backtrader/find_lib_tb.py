import sys
import os
import traceback

try:
    import BinaryOptionsToolsV2
    print(f"Location: {os.path.dirname(BinaryOptionsToolsV2.__file__)}")
except:
    traceback.print_exc()
