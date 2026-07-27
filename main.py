import sys
import os

# Append src folder to path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

import uvicorn

if __name__ == "__main__":
    print("Redirecting execution to src/main.py...")
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
