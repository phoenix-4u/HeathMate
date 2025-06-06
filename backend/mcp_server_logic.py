# healthmate_app/backend/mcp_server_logic.py
import json
import asyncio
from typing import Dict, Any

# Import the registry from the tools module
from backend.tools.mcp_tools_registry import MCP_TOOLS_REGISTRY

async def execute_mcp_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a registered MCP tool.

    Args:
        tool_name: The name of the tool to execute.
        tool_input: A dictionary of parameters for the tool.

    Returns:
        A dictionary containing the tool_name and its output, or an error.
    """
    print(f"MCP_SERVER_LOGIC: Attempting to execute tool='{tool_name}' with input={tool_input}")

    if tool_name not in MCP_TOOLS_REGISTRY:
        print(f"MCP_SERVER_LOGIC: Tool='{tool_name}' not found in registry.")
        return {
            "tool_name": tool_name,
            "tool_output": {"error": f"Tool '{tool_name}' not found."},
            "error": True,
            "status": 404 # Not Found
        }

    tool_function = MCP_TOOLS_REGISTRY[tool_name]

    try:
        # Directly call the async tool function (all our tools are async now)
        # The tool functions themselves should handle input validation.
        if asyncio.iscoroutinefunction(tool_function):
            result = await tool_function(**tool_input)
        else:
            # This case should ideally not happen if all registered tools are async
            print(f"MCP_SERVER_LOGIC: Warning - Tool '{tool_name}' is not an async function. Calling synchronously.")
            result = tool_function(**tool_input) # type: ignore

        print(f"MCP_SERVER_LOGIC: Successfully executed tool='{tool_name}'.")
        return {
            "tool_name": tool_name,
            "tool_output": result, # The result from the tool function
            "error": False, # Indicate no error in execution itself (tool_output might contain its own 'error' field)
            "status": 200 # OK
        }
    except TypeError as te:
        # This often happens if tool_input doesn't match the tool_function's signature
        print(f"MCP_SERVER_LOGIC: TypeError executing tool='{tool_name}': {te}. Input was: {tool_input}")
        return {
            "tool_name": tool_name,
            "tool_output": {
                "error": "Invalid parameters provided for the tool.",
                "details": str(te)
            },
            "error": True,
            "status": 400 # Bad Request
        }
    except Exception as e:
        print(f"MCP_SERVER_LOGIC: Unexpected error executing tool='{tool_name}': {e}")
        return {
            "tool_name": tool_name,
            "tool_output": {
                "error": "An unexpected error occurred during tool execution.",
                "details": str(e)
            },
            "error": True,
            "status": 500 # Internal Server Error
        }

if __name__ == '__main__':
    async def main():
        print("--- Testing MCP Server Logic ---")

        # Test case 1: Valid tool and input
        print("\nTest Case 1: Valid PubMed search")
        response1 = await execute_mcp_tool(
            tool_name="search_pubmed",
            tool_input={"query": "common cold symptoms", "max_results": 1}
        )
        print(json.dumps(response1, indent=2))
        assert not response1["error"] and response1["status"] == 200
        assert "id" in response1["tool_output"][0]

        # Test case 2: Tool not found
        print("\nTest Case 2: Tool not found")
        response2 = await execute_mcp_tool(
            tool_name="non_existent_tool",
            tool_input={"some_param": "value"}
        )
        print(json.dumps(response2, indent=2))
        assert response2["error"] and response2["status"] == 404

        # Test case 3: Valid tool, but missing required input (tool should handle or TypeError)
        print("\nTest Case 3: FDA tool with missing 'drug_name'")
        response3 = await execute_mcp_tool(
            tool_name="get_fda_drug_info",
            tool_input={} # Missing 'drug_name'
        )
        print(json.dumps(response3, indent=2))
        # This will result in a TypeError because drug_name is a required positional argument.
        assert response3["error"] and response3["status"] == 400
        assert "Invalid parameters" in response3["tool_output"]["error"]

        # Test case 4: Valid tool, incorrect input type (tool should handle)
        print("\nTest Case 4: PubMed tool with incorrect 'max_results' type")
        response4 = await execute_mcp_tool(
            tool_name="search_pubmed",
            tool_input={"query": "flu", "max_results": "one"} # max_results should be int
        )
        print(json.dumps(response4, indent=2))
        # The tool itself might correct it or error; let's assume TypeError for now if not handled inside.
        # Our current tool_search_pubmed corrects it or uses default.
        # If it was a strict type requirement for the tool function, it would be status 400.
        # In this case, our tool has a default so it might pass with default value for max_results
        assert not response4["error"] and response4["status"] == 200
        assert response4["tool_output"][0]["summary"] # Check if it ran

        # Test case 5: Symptom analyzer
        print("\nTest Case 5: Symptom Analyzer")
        response5 = await execute_mcp_tool(
            tool_name="analyze_text_for_symptoms",
            tool_input={"text": "Patient has fever and cough."}
        )
        print(json.dumps(response5, indent=2))
        assert not response5["error"] and "symptoms_detected" in response5["tool_output"]
        assert "fever" in response5["tool_output"]["symptoms_detected"]

    asyncio.run(main())