# healthmate_app/app.py
import json
from fastapi import FastAPI, Request as FastAPIRequest, HTTPException
from fastapi.responses import JSONResponse
# import uvicorn # Only if running uvicorn directly

# Import the configured logger first, so it's available for all other imports
from logger_config import logger

# Import the Gradio app builder function
from frontend.gradio_interface import build_gradio_app

# Import the MCP tool execution logic from the backend
from backend.mcp_server_logic import execute_mcp_tool

logger.info("HealthMate Application Starting Up...")

# --- Build the Gradio Application ---
# This function call creates the Gradio Blocks UI and logs within itself
gradio_app_ui = build_gradio_app()

# --- Get the underlying FastAPI app from Gradio ---
app: FastAPI = gradio_app_ui.app # type: ignore
logger.info("FastAPI app instance obtained from Gradio UI.")

# --- Define the MCP Server Endpoint on the FastAPI app ---
@app.post("/mcp", tags=["MCP Server"])
async def handle_mcp_request(request: FastAPIRequest):
    """
    Handles incoming MCP (Model Context Protocol) requests.
    """
    logger.info(f"MCP Endpoint: Received request. Method: {request.method}, URL: {request.url}")
    try:
        data = await request.json()
        logger.debug(f"MCP Endpoint: Request JSON data: {data}")
    except json.JSONDecodeError:
        logger.warning("MCP Endpoint: Invalid JSON in request body.", exc_info=True) # exc_info for file log
        raise HTTPException(status_code=400, detail="Invalid JSON in request body.")

    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input", {})

    if not tool_name:
        logger.warning("MCP Endpoint: 'tool_name' is required but not found in request.")
        raise HTTPException(status_code=400, detail="'tool_name' is required in MCP request.")

    logger.info(f"MCP Endpoint: Processing tool_name='{tool_name}', tool_input='{tool_input}'")

    # Call the central MCP tool executor from the backend
    # This executor function has its own detailed logging
    response_payload = await execute_mcp_tool(tool_name, tool_input)

    logger.info(f"MCP Endpoint: Tool '{tool_name}' execution finished. Response status: {response_payload.get('status', 500)}")
    logger.debug(f"MCP Endpoint: Response payload for tool '{tool_name}': {response_payload}")

    return JSONResponse(
        status_code=response_payload.get("status", 500),
        content=response_payload
    )

# --- Main entry point for running the application ---
if __name__ == "__main__":
    logger.info("Starting HealthMate Gradio UI and MCP Server via app.py __main__...")
    
    gradio_app_ui.launch(
        server_name="0.0.0.0",
        # server_port=7890, # Default or configure as needed
        # debug=False # Gradio's debug. Our logger provides app-level debug.
                     # Set to True if you need Gradio's specific debugging features (like component updates)
        share=False,  # Set to True if you want to share the app publicly
        debug=True,  # Enable Gradio's debug mode for more verbose output
        prevent_thread_lock=True,  # Prevents Gradio from blocking the event loop
    )
    logger.info("HealthMate application launch sequence complete.")