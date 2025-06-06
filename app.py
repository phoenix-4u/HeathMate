# healthmate_app/app.py
import json
from fastapi import FastAPI, Request as FastAPIRequest, HTTPException
from fastapi.responses import JSONResponse
import uvicorn # For running FastAPI if not using Gradio's launch in some contexts

# Import the Gradio app builder function
from frontend.gradio_interface import build_gradio_app

# Import the MCP tool execution logic from the backend
from backend.mcp_server_logic import execute_mcp_tool

# --- Build the Gradio Application ---
# This function call creates the Gradio Blocks UI
gradio_app_ui = build_gradio_app()

# --- Get the underlying FastAPI app from Gradio ---
# Gradio's Blocks.launch() creates and runs a FastAPI app.
# We can access this app instance to add our own routes.
# The `app` variable here will be the FastAPI instance.
app: FastAPI = gradio_app_ui.app # type: ignore

# --- Define the MCP Server Endpoint on the FastAPI app ---
@app.post("/mcp", tags=["MCP Server"])
async def handle_mcp_request(request: FastAPIRequest):
    """
    Handles incoming MCP (Model Context Protocol) requests.
    Expects a JSON body with "tool_name" and "tool_input".
    """
    try:
        data = await request.json()
    except json.JSONDecodeError:
        print("MCP Error: Invalid JSON in request body")
        raise HTTPException(status_code=400, detail="Invalid JSON in request body.")

    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input", {}) # Default to empty dict if not provided

    if not tool_name:
        print("MCP Error: 'tool_name' is required in MCP request.")
        raise HTTPException(status_code=400, detail="'tool_name' is required in MCP request.")

    print(f"APP.PY MCP Endpoint: Received tool_name='{tool_name}', tool_input='{tool_input}'")

    # Call the central MCP tool executor from the backend
    # This executor already handles tool lookup, execution, and error packaging
    response_payload = await execute_mcp_tool(tool_name, tool_input)

    # The execute_mcp_tool function returns a dict with 'status' and 'tool_output' etc.
    # We use its status for the HTTP response.
    return JSONResponse(
        status_code=response_payload.get("status", 500), # Default to 500 if status not in payload
        content=response_payload
    )

# --- Main entry point for running the application ---
if __name__ == "__main__":
    # When running this script directly, launch the Gradio app.
    # This will serve both the Gradio UI and the FastAPI /mcp endpoint.
    print("Starting HealthMate Gradio UI and MCP Server...")
    
    # gradio_app_ui.launch() is suitable for most cases, especially local dev.
    # It will pick an available port or use 7860 by default.
    # For Hugging Face Spaces, Gradio often handles this launch automatically if `app.py`
    # defines `gradio_app_ui` (or `demo`) at the global level.
    # The `app = gradio_app_ui.app` line is key for Spaces to find the FastAPI app.
    
    gradio_app_ui.launch(
        server_name="0.0.0.0", # Bind to all interfaces for containerized environments
        # server_port=7860, # Optional: specify a port
        debug=True # Enable Gradio debug mode (shows more logs)
    )
    
    # Alternatively, to run FastAPI directly with uvicorn (less common for Gradio apps but possible):
    # uvicorn.run(app, host="0.0.0.0", port=8000)
    # But gradio_app_ui.launch() is preferred as it manages Gradio's specifics.