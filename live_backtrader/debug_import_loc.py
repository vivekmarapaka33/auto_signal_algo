import sys
import os
import traceback

print(f"Exec: {sys.executable}")
try:
    import BinaryOptionsToolsV2
    print(f"Pkg: {BinaryOptionsToolsV2.__file__}")
    print(f"Dir: {os.path.dirname(BinaryOptionsToolsV2.__file__)}")
except:
    traceback.print_exc()
