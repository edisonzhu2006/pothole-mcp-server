import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / ".env.local")

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.main import query_hazards, estimate_repair_plan, project_worsening

async def main():
    """
    Tests the MCP server's tool functions directly.
    """
    print("--- Running Hazard MCP Server Tests ---")

    location_with_most_hazards = None

    # Test 1: Query for the area with the most hazards
    print("\n[Test 1] Querying for area with most hazards...")
    try:
        result = query_hazards(kind="area_with_most_hazards")
        print("[SUCCESS] Test 1 completed.")
        print("Result:", result)
        if result and result.get("result"):
            location_with_most_hazards = result["result"][0]["location"]
    except Exception as e:
        print(f"[ERROR] Test 1 failed: {e}")

    # Test 2: Get a repair plan for a specific hazard
    print("\n[Test 2] Estimating repair plan for a hazard...")
    if location_with_most_hazards:
        try:
            # First, find a hazard to test with
            hazards = query_hazards(kind="top_severe_in_area", location=location_with_most_hazards)
            if not hazards or not hazards.get("result"):
                raise ValueError("No hazards found to test repair plan.")
            
            hazard_id = hazards["result"][0]["id"]
            result = estimate_repair_plan(hazard_id=hazard_id)
            print(f"[SUCCESS] Test 2 completed for hazard {hazard_id}.")
            print("Result:", result)
        except Exception as e:
            print(f"[ERROR] Test 2 failed: {e}")
    else:
        print("[SKIPPED] Test 2 skipped because no location was found in Test 1.")

    # Test 3: Project worsening for a location
    print("\n[Test 3] Projecting worsening for a location...")
    if location_with_most_hazards:
        try:
            result = project_worsening(location=location_with_most_hazards, horizon_days=90)
            print("[SUCCESS] Test 3 completed.")
            print("Result:", result)
        except Exception as e:
            print(f"[ERROR] Test 3 failed: {e}")
    else:
        print("[SKIPPED] Test 3 skipped because no location was found in Test 1.")

    print("\n--- All tests complete ---")

if __name__ == "__main__":
    asyncio.run(main())