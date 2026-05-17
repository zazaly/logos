"""Dev launcher for running BRU directly from source."""
import sys
from pathlib import Path

# Add the current directory to path so 'studio' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio.__main__ import main

if __name__ == "__main__":
    main()