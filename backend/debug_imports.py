import time
import sys
import os
from dotenv import load_dotenv

print("Checking environment...")
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))
print("Env loaded")

modules_to_test = [
    "fastapi",
    "app.config",
    "app.services.security_service",
    "app.services.cache_service_lru",
    "app.config.database",
    "app.routes.query",
    "app.routes.pitch_deck",
    "app.services.pipeline"
]

for mod in modules_to_test:
    start = time.time()
    print(f"Importing {mod}...")
    try:
        __import__(mod)
        print(f"DONE ({time.time()-start:.2f}s)")
    except Exception as e:
        print(f"FAILED: {e}")

print("All imports tested.")
