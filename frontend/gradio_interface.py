# healthmate_app/frontend/gradio_interface.py
import gradio as gr
import json
import asyncio # For running async workflow functions with Gradio
from typing import Optional, List, Dict, Any
# Import the compiled LangGraph applications from the backend
from backend.workflows.outbreak_workflow import outbreak_detection_app, OutbreakWorkflowState
from backend.workflows.healthinfo_workflow import health_info_app, HealthInfoWorkflowState
from backend.workflows.postdischarge_workflow import post_discharge_info_app, PostDischargeWorkflowState

# --- Helper function to run workflow and format output for Gradio ---
async def run_workflow_gradio(app_name: str, compiled_app, initial_state: dict, config: dict):
    """
    A generic runner for LangGraph apps, adapted for Gradio.
    Streams the final state's relevant output and debug log.
    """
    final_state = None
    output_key = None # Key in the state dict that holds the primary output string
    debug_log = []

    if app_name == "outbreak":
        output_key = "synthesized_report"
    elif app_name == "healthinfo":
        output_key = "synthesized_answer"
    elif app_name == "postdischarge":
        output_key = "synthesized_response"

    try:
        # LangGraph's astream with stream_mode="values" yields the full state dict at each step.
        # The last event is the final state of the graph.
        async for event_state in compiled_app.astream(initial_state, config=config, stream_mode="values"):
            final_state = event_state # Keep updating, the last one is the final
        
        debug_log = final_state.get('debug_log', ['No debug log found.']) if final_state else ['Workflow did not complete.']

        if final_state and final_state.get("error_message"):
            error_msg = final_state['error_message']
            primary_output = f"Workflow Error on App '{app_name}': {error_msg}"
            # Return error as primary output and the full state for debugging
            return primary_output, json.dumps(final_state, indent=2, default=str)

        if final_state and output_key and final_state.get(output_key):
            primary_output = final_state[output_key]
            # Return primary output and the full state for debugging
            return primary_output, json.dumps(final_state, indent=2, default=str)
        
        # Fallback if no specific output key matched or no output generated
        primary_output = f"Workflow for '{app_name}' completed but no primary output was generated."
        if final_state:
             primary_output += " Please check the debug state."
             return primary_output, json.dumps(final_state, indent=2, default=str)
        else:
            primary_output = f"Workflow for '{app_name}' did not seem to run correctly. No final state."
            return primary_output, "{'error': 'No final state from workflow'}"

    except Exception as e:
        err_msg = f"Critical Gradio/Workflow execution error in '{app_name}': {str(e)}"
        print(err_msg) # Log to console as well
        # Return error message as primary output and a simple JSON error object
        return err_msg, json.dumps({"critical_error": str(e), "app_name": app_name, "initial_state": initial_state}, indent=2, default=str)


# --- Gradio UI Event Handlers (calling the helper) ---

async def handle_outbreak_analysis(raw_text_input: str):
    if not raw_text_input or not raw_text_input.strip():
        return "Input text is empty. Please provide some text for analysis.", "{'error': 'Empty input'}"
    
    initial_state: OutbreakWorkflowState = {"raw_input_text": raw_text_input} # type: ignore
    # Ensure all keys defined in OutbreakWorkflowState with potential None are initialized if not passed
    # LangGraph can be strict, but TypedDict with total=False helps. We ensure required ones.
    
    config = {"configurable": {"thread_id": f"gradio-outbreak-{asyncio.get_running_loop().time()}"}} # Unique thread_id
    return await run_workflow_gradio("outbreak", outbreak_detection_app, initial_state, config)


async def handle_health_information(query: str, claim_to_vet: Optional[str]):
    if not query or not query.strip():
        return "Health query is empty. Please ask a question.", "{'error': 'Empty query'}"

    is_misinfo = bool(claim_to_vet and claim_to_vet.strip())
    initial_state: HealthInfoWorkflowState = { # type: ignore
        "user_query": query,
        "is_misinfo_check": is_misinfo,
        "claim_to_check": claim_to_vet if is_misinfo else None
    }
    config = {"configurable": {"thread_id": f"gradio-healthinfo-{asyncio.get_running_loop().time()}"}}
    return await run_workflow_gradio("healthinfo", health_info_app, initial_state, config)


async def handle_post_discharge_info(condition: Optional[str], medication: Optional[str], question: str):
    if not question or not question.strip():
        return "Your specific question is empty. Please provide a question.", "{'error': 'Empty specific question'}"
    if not (condition and condition.strip()) and not (medication and medication.strip()) and \
       ("warning sign" not in question.lower() and "exercise" not in question.lower() and "diet" not in question.lower()): # Heuristic
        # If no context and question is very generic, prompt for more
        # return "Please provide some context (condition or medication) for more specific post-discharge information, or ask a more general question about warning signs, exercise, or diet.", "{'error': 'Insufficient context for generic question'}"
        pass # Allow it to proceed, the workflow will guide


    initial_state: PostDischargeWorkflowState = { # type: ignore
        "condition_context": condition if condition and condition.strip() else None,
        "medication_context": medication if medication and medication.strip() else None,
        "user_specific_question": question
    }
    config = {"configurable": {"thread_id": f"gradio-postdischarge-{asyncio.get_running_loop().time()}"}}
    return await run_workflow_gradio("postdischarge", post_discharge_info_app, initial_state, config)


# --- Gradio Interface Definition ---
def build_gradio_app():
    with gr.Blocks(theme=gr.themes.Soft(primary_hue=gr.themes.colors.blue, secondary_hue=gr.themes.colors.sky), title="HealthMate Assistant") as healthmate_gradio_app:
        gr.Markdown(
            """
            # ⚕️ HealthMate: Your AI Health Information Assistant & MCP Server
            Welcome to HealthMate! This application provides several AI-powered tools for health-related information and also functions as an MCP Server.
            *Disclaimer: HealthMate is a technology demonstrator using publicly available data and AI. It is **NOT** a substitute for professional medical advice, diagnosis, or treatment. Always consult with qualified healthcare providers for any medical concerns.*
            """
        )

        with gr.Tab("🚨 Outbreak Monitor (Simulated)"):
            gr.Markdown("### Public Health Anomaly Detection (Simulated)")
            gr.Markdown("Enter text describing observations that might indicate a public health anomaly (e.g., news snippets, forum posts, or simulated reports). HealthMate will analyze it for potential signals.")
            with gr.Row():
                with gr.Column(scale=2):
                    outbreak_input_text = gr.Textbox(lines=5, label="Input Text for Anomaly Analysis", placeholder="e.g., 'Several local schools report a sudden spike in students with fever and rashes.'")
                    outbreak_run_button = gr.Button("🔍 Analyze for Potential Outbreak", variant="primary")
                with gr.Column(scale=3):
                    outbreak_output_report = gr.Textbox(label="📝 Synthesized Outbreak Report", lines=12, interactive=False)
            outbreak_debug_state = gr.JSON(label="🕵️ Debug: Final Workflow State (JSON)", visible=False) # Initially hidden
            
            outbreak_run_button.click(
                fn=handle_outbreak_analysis,
                inputs=[outbreak_input_text],
                outputs=[outbreak_output_report, outbreak_debug_state]
            )
            with gr.Accordion("Show/Hide Debug State", open=False):
                 gr.Checkbox(label="Show Debug JSON Output", value=False).change(lambda x: gr.update(visible=x), inputs=gr.Checkbox(label="Show Debug JSON Output", value=False), outputs=[outbreak_debug_state])


        with gr.Tab("💡 Health Info & Misinfo Check"):
            gr.Markdown("### Ask Health Questions & Vet Information")
            gr.Markdown("Get information on health topics, conditions, or medications. You can also (optionally) provide a specific claim to be vetted against the retrieved information.")
            with gr.Row():
                with gr.Column(scale=2):
                    health_query_input = gr.Textbox(lines=3, label="Your Health Question", placeholder="e.g., 'What are the symptoms of Type 2 Diabetes?', 'Tell me about Metformin.'")
                    health_claim_input = gr.Textbox(lines=3, label="Claim to Vet (Optional)", placeholder="e.g., 'Does drinking lemon water daily cure high blood pressure?'")
                    health_run_button = gr.Button("💬 Get Info & Vet Claim", variant="primary")
                with gr.Column(scale=3):
                    health_output_answer = gr.Textbox(label="ℹ️ Information & Vetting Result", lines=15, interactive=False)
            health_debug_state = gr.JSON(label="🕵️ Debug: Final Workflow State (JSON)", visible=False)

            health_run_button.click(
                fn=handle_health_information,
                inputs=[health_query_input, health_claim_input],
                outputs=[health_output_answer, health_debug_state]
            )
            with gr.Accordion("Show/Hide Debug State", open=False):
                 gr.Checkbox(label="Show Debug JSON Output", value=False).change(lambda x: gr.update(visible=x), inputs=gr.Checkbox(label="Show Debug JSON Output", value=False), outputs=[health_debug_state])


        with gr.Tab("🏠 Post-Discharge Support"):
            gr.Markdown("### General Information for Post-Discharge Care")
            gr.Markdown("Specify a condition and/or medication along with your question to get relevant (general) post-discharge information. This is not personalized medical advice.")
            with gr.Row():
                with gr.Column(scale=2):
                    discharge_condition_input = gr.Textbox(label="Relevant Condition (Optional)", placeholder="e.g., 'Recovery after minor surgery', 'Managing a new asthma diagnosis'")
                    discharge_medication_input = gr.Textbox(label="Relevant Medication (Optional)", placeholder="e.g., 'Lisinopril', 'Pain reliever X'")
                    discharge_question_input = gr.Textbox(lines=3, label="Your Specific Question", placeholder="e.g., 'What are common recovery milestones?', 'What foods should I avoid with this medication?'")
                    discharge_run_button = gr.Button(" Rcv_Patient_Ask_EncircleGet Post-Discharge Information", variant="primary")
                with gr.Column(scale=3):
                    discharge_output_response = gr.Textbox(label="📖 Information Response", lines=15, interactive=False)
            discharge_debug_state = gr.JSON(label="🕵️ Debug: Final Workflow State (JSON)", visible=False)

            discharge_run_button.click(
                fn=handle_post_discharge_info,
                inputs=[discharge_condition_input, discharge_medication_input, discharge_question_input],
                outputs=[discharge_output_response, discharge_debug_state]
            )
            with gr.Accordion("Show/Hide Debug State", open=False):
                 gr.Checkbox(label="Show Debug JSON Output", value=False).change(lambda x: gr.update(visible=x), inputs=gr.Checkbox(label="Show Debug JSON Output", value=False), outputs=[discharge_debug_state])

        gr.Markdown(
            """
            ---
            **MCP Server Information**
            This HealthMate application also serves as an MCP (Model Context Protocol) Server.
            - **Endpoint**: Send `POST` requests to `/mcp` on this Space's URL.
            - **Request Body Format**: `{"tool_name": "your_tool_name", "tool_input": {"param1": "value1", ...}}`
            - **Available Tools**: `search_pubmed`, `get_fda_drug_info`, `get_health_gov_topic`, `analyze_text_for_symptoms`.
            *(Refer to `README.md` or `app.py` for more details on tools and parameters.)*
            """
        )
        return healthmate_gradio_app

if __name__ == '__main__':
    # This allows you to run just the Gradio UI for testing,
    # assuming your backend workflows are correctly structured and importable.
    # For the full app with MCP server, you'll run the main app.py.
    ui = build_gradio_app()
    ui.launch(debug=True)