# healthmate_app/backend/mcp_server_logic.py
import json 
import asyncio 
from typing import Dict, Any
# Import the configured logger
from logger_config import logger

# Import the registry from the tools module
from backend.tools.mcp_tools_registry import MCP_TOOLS_REGISTRY, ToolsRegistry 

async def execute_mcp_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a registered MCP tool.
    """
    logger.info(f"MCP Server: Attempting to execute tool='{tool_name}' with input='{tool_input}'.")

    if tool_name not in MCP_TOOLS_REGISTRY:
        logger.warning(f"MCP Server: Tool='{tool_name}' not found in registry.")
        return {
            "tool_name": tool_name,
            "tool_output": {"error": f"Tool '{tool_name}' not found."},
            "error": True,
            "status": 404 
        }

    tool_function = MCP_TOOLS_REGISTRY[tool_name]

    try:
        # All registered tools are expected to be async coroutine functions
        logger.debug(f"MCP Server: Calling tool function '{tool_name}'.")
        result = await tool_function(**tool_input)
        # The tool functions themselves (or the API clients they call)
        # are responsible for detailed logging of their execution.

        logger.info(f"MCP Server: Successfully executed tool='{tool_name}'.")
        # Check if the tool's result itself indicates an error (e.g., API client error)
        tool_had_internal_error = isinstance(result, dict) and result.get("error") is not None
        
        return {
            "tool_name": tool_name,
            "tool_output": result,
            "error": tool_had_internal_error, # Reflect if the tool's output contains an error
            "status": 400 if tool_had_internal_error and isinstance(result.get("details"), str) and "Invalid input" in result.get("details", "") else (200 if not tool_had_internal_error else 500) # Basic status logic
        }
    except TypeError as te:
        logger.error(f"MCP Server: TypeError executing tool='{tool_name}' with input='{tool_input}'. Error: {te}", exc_info=True)
        return {
            "tool_name": tool_name,
            "tool_output": {
                "error": "Invalid parameters provided for the tool.",
                "details": str(te)
            },
            "error": True,
            "status": 400 
        }
    except Exception as e:
        logger.error(f"MCP Server: Unexpected error executing tool='{tool_name}': {e}", exc_info=True)
        return {
            "tool_name": tool_name,
            "tool_output": {
                "error": "An unexpected error occurred during tool execution.",
                "details": str(e)
            },
            "error": True,
            "status": 500
        }

if __name__ == '__main__':
    async def main():
        logger.info("--- Running MCP Server Logic Self-Test ---")

        logger.info("\nTest Case 1: Valid PubMed search via execute_mcp_tool")
        response1 = await execute_mcp_tool(
            tool_name="search_pubmed",
            tool_input={"query": "common cold symptoms", "max_results": 1}
        )
        logger.info(f"Response 1 (PubMed): {response1}")
        # Assertions can be added here if needed

        logger.info("\nTest Case 2: Tool not found via execute_mcp_tool")
        response2 = await execute_mcp_tool(
            tool_name="non_existent_tool",
            tool_input={"some_param": "value"}
        )
        logger.info(f"Response 2 (Tool Not Found): {response2}")

        logger.info("\nTest Case 3: FDA tool with missing 'drug_name' via execute_mcp_tool (expecting TypeError)")
        response3 = await execute_mcp_tool(
            tool_name="get_fda_drug_info",
            tool_input={} # Missing 'drug_name'
        )
        logger.info(f"Response 3 (FDA Missing Param): {response3}")
        
        logger.info("--- MCP Server Logic Self-Test Complete ---")

    asyncio.run(main())