# launch.py  (in the project root)
import sys
from pathlib import Path

# Add the current directory to path so 'bru' package is importable
sys.path.insert(0, str(Path(__file__).parent))

from bru.__main__ import main

if __name__ == "__main__":
    main()