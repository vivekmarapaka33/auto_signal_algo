import sys
import os
import traceback

print(f"Python executable: {sys.executable}")
print(f"Path: {sys.path}")

try:
    import BinaryOptionsToolsV2
    print(f"BinaryOptionsToolsV2 file: {BinaryOptionsToolsV2.__file__}")
    from BinaryOptionsToolsV2.pocketoption import asyncronous
    print(f"Async file: {asyncronous.__file__}")
except:
    traceback.print_exc()
