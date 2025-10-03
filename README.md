# SimpleMCP
My simple FastMCP for hosting


# Local run
`fastmcp run main.py`

# Deploy
`https://fastmcp.cloud`

# Connect to GigaAgent
`
MCP_CONFIG = {
    "giga_tools": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "mcp-remote@latest", "https://gigachat.fastmcp.app/mcp"]
    }
}
`