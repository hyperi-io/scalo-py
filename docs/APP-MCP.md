# MCP Applications

Model Context Protocol servers for AI tool integration.

## Quick Start

```python
from hyperi_pylib import Application

app = Application.mcp(name="my-tools", version="1.0.0")

@app.tool(
    name="get_weather",
    description="Get current weather for a city"
)
def get_weather(city: str) -> dict:
    # Your tool logic
    return {"city": city, "temp": 72, "condition": "sunny"}

@app.tool(
    name="search_docs",
    description="Search documentation"
)
def search_docs(query: str, limit: int = 10) -> list:
    # Your search logic
    results = search_index(query, limit)
    return results

if __name__ == "__main__":
    app.run()  # Runs stdio MCP server
```

Usage:

```bash
python -m my_tools serve  # Start MCP server
```

## Features

- **MCP protocol**: Compatible withDesktop, Continue, etc.
- **Tool registration**: Simple decorator-based tool definition
- **Resource support**: Expose data resources to AI clients
- **Stdio transport**: Communication via stdin/stdout
- **Graceful shutdown**: Handles client disconnect
- **Metrics**: Optional tool usage tracking

## Tool Registration

```python
@app.tool(
    name="calculate",
    description="Perform arithmetic calculation"
)
def calculate(expression: str) -> float:
    """Calculate math expression safely."""
    # Validate and evaluate expression
    result = safe_eval(expression)
    return result

@app.tool(
    name="get_user",
    description="Get user information by ID"
)
def get_user(user_id: int) -> dict:
    """Fetch user from database."""
    user = db.get_user(user_id)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email
    }
```

## Resource Registration

```python
@app.resource(
    uri="docs://readme",
    name="README",
    description="Project README file"
)
def get_readme() -> str:
    with open("README.md") as f:
        return f.read()

@app.resource(
    uri="config://app",
    name="App Config",
    description="Current application configuration"
)
def get_config() -> dict:
    return load_config()
```

## Async Tools

```python
@app.tool(
    name="fetch_api_data",
    description="Fetch data from external API"
)
async def fetch_api_data(endpoint: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint)
        return response.json()
```

## Production Example

```python
from hyperi_pylib import Application, logger
import sqlite3

app = Application.mcp(
    name="database-tools",
    version="1.0.0",
    profile="prod"
)

@app.on_startup
def connect():
    logger.info("Connecting to database...")
    global db
    db = sqlite3.connect("data.db")

@app.tool(
    name="query_database",
    description="Execute SQL query and return results"
)
def query_database(sql: str) -> list:
    """Execute safe SELECT query."""
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries allowed")

    cursor = db.execute(sql)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    return [dict(zip(columns, row)) for row in rows]

@app.tool(
    name="list_tables",
    description="List all database tables"
)
def list_tables() -> list:
    """Get list of all tables."""
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    return [row[0] for row in cursor.fetchall()]

@app.tool(
    name="get_schema",
    description="Get schema for a table"
)
def get_schema(table: str) -> str:
    """Get CREATE TABLE statement."""
    cursor = db.execute(
        "SELECT sql FROM sqlite_master WHERE name=?",
        (table,)
    )
    result = cursor.fetchone()
    return result[0] if result else None

@app.resource(
    uri="db://tables",
    name="Database Tables",
    description="List of all database tables"
)
def get_tables_resource() -> str:
    tables = list_tables()
    return "\n".join(tables)

@app.on_shutdown
def disconnect():
    logger.info("Closing database...")
    db.close()

if __name__ == "__main__":
    app.run()
```

##Desktop Integration

Add to `_desktop_config.json`:

```json
{
  "mcpServers": {
    "database-tools": {
      "command": "python",
      "args": ["-m", "database_tools", "serve"]
    }
  }
}
```

## Continue Integration

Add to `.continue/config.json`:

```json
{
  "contextProviders": [
    {
      "name": "database-tools",
      "params": {
        "command": "python -m database_tools serve"
      }
    }
  ]
}
```

## Tool Usage Tracking

```python
@app.tool(name="expensive_operation", description="Expensive API call")
def expensive_operation(data: str) -> dict:
    # Track usage
    if hasattr(app, 'track_counter'):
        app.track_counter("tool_calls", labels={"tool": "expensive_operation"})

    result = call_expensive_api(data)
    return result
```

## Error Handling

```python
@app.tool(name="risky_tool", description="Tool that might fail")
def risky_tool(input: str) -> dict:
    try:
        result = process(input)
        return {"status": "success", "result": result}
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise  # MCP server will return error to client
```

## Protocol Methods

The MCP server automatically handles:

- `tools/list`: List available tools
- `tools/call`: Execute tool with arguments
- `resources/list`: List available resources
- `resources/read`: Read resource content

## Testing

```python
def test_tool():
    app = Application.mcp(name="test")

    @app.tool(name="add", description="Add two numbers")
    def add(a: int, b: int) -> int:
        return a + b

    # Test tool registration
    assert "add" in app.tools
    assert app.tools["add"]["handler"](2, 3) == 5
```

## When to Use MCP

Use MCP applications for:

- **Database tools**: Query databases from AI assistants
- **File system tools**: Read/write files, search code
- **API integrations**: Call external APIs with AI guidance
- **Code analysis**: Static analysis, linting, testing
- **Documentation**: Provide context to AI about your codebase

Integration with:

-Desktop
- Continue (VS Code)
- Cursor
- Other MCP-compatible AI tools
