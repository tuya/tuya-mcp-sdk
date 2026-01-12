# Examples Usage 

```python
import asyncio
from mcp_sdk import create_mcpsdk

async def main():
    # Running Custom MCP Server (in background)
    # Note: MCP Server should be started separately
    
    print("MCP SDK starting...")
    
    # Create and run MCP SDK
    # Schema is auto-inferred: 'http' for localhost endpoints, 'https' for others
    async with create_mcpsdk(
        # Set access id, access secret and endpoint
        endpoint="your-endpoint",
        access_id="your-access-id",
        access_secret="your-access-secret",
        
        # Set custom MCP server URI
        custom_mcp_server_endpoint="http://localhost:8765/mcp",
    ) as mcpsdk:
        
        print("MCP SDK connected successfully!")
        print(f"MCP Server: {mcpsdk.custom_mcp_server_endpoint}")
        
        # Start background listening
        await mcpsdk.start_background()
        
        print("MCP SDK started")
        
        # Keep running
        while mcpsdk.is_running:
            await asyncio.sleep(10)
            print("MCP SDK is still running...")

if __name__ == "__main__":
    asyncio.run(main())
```
