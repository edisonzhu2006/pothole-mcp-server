import asyncio
from dedalus_labs import AsyncDedalus, DedalusRunner

async def test():
    runner = DedalusRunner(AsyncDedalus())
    out = await runner.run(
        input="Use the tools from my MCP server at: ez2103/hazard-mcp List all the available tools exposed by that server.",
        model="openai/gpt-5-mini",
        mcp_servers=["ez2103/pothole-mcp-server"]  
    )
    print(out.final_output)

asyncio.run(test())