import asyncio
from dedalus_labs import AsyncDedalus, DedalusRunner

async def test():
    runner = DedalusRunner(AsyncDedalus())
    out = await runner.run(
        input="List all available tools from the hazard-mcp server.",
        model="openai/gpt-4o-mini",
        mcp_servers=["ez2103/hazard-mcp"]  
    )
    print(out.final_output)

asyncio.run(test())