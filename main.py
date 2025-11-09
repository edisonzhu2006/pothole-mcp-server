import sys, os
import asyncio

def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from src.main import mcp
    mcp.run()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
