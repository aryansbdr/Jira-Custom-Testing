import sys
import os

# Append src folder to path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

import src.cli_run

if __name__ == "__main__":
    print("Redirecting execution to src/cli_run.py...")
    src.cli_run.main()
