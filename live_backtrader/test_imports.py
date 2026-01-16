print("Importing app.core.config...")
try:
    from app.core import config
    print("Success")
except Exception as e:
    print(f"Failed: {e}")

print("Importing app.api.endpoints...")
try:
    from app.api import endpoints
    print("Success")
except Exception as e:
    print(f"Failed: {e}")

print("Importing app.engine.live...")
try:
    from app.engine import live
    print("Success")
except Exception as e:
    print(f"Failed: {e}")
