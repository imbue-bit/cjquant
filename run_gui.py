import sys
import os

# Ensure root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gui import main

if __name__ == '__main__':
    main()
