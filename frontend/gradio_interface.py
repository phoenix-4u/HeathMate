# healthmate_app/frontend/gradio_interface.py
import gradio as gr
import json
import asyncio
from typing import Optional, List, Dict, Any 

# Import the configured logger
from logger_config import logger

# Import the compiled LangGraph applications from the backend
# from backend.workflows.outbreak_workflow import outbreak_detection_app, OutbreakWorkflowState # If you kept it
from backend.workflows.healthinfo_workflow import health_info_app, HealthInfoWorkflowState
from backend.workflows.postdischarge_workflow import post_discharge_info_app, PostDischargeWorkflowState

# --- Helper function to run workflow and format output for Gradio ---
async def run_workflow_gradio(app_name: str, compiled_app, initial_state: dict, config: dict):
    logger.info(f"Gradio: Running workflow '{app_name}' with initial state: {initial_state}")
    final_state = None
    output_key = None
    
    # if app_name == "outbreak": # If outbreak workflow is used
    #     output_key = "synthesized_report"
    if app_name == "healthinfo":
        output_key = "synthesized_answer"
    elif app_name == "postdischarge":
        output_key = "synthesized_response"

    try:
        async for event_state in compiled_app.astream(initial_state, config=config, stream_mode="values"):
            final_state = event_state
            logger.debug(f"Gradio: Workflow '{app_name}' - intermediate state keys: {list(event_state.keys()) if event_state else 'None'}")
        
        # The workflow itself should log its internal state via logger.debug in its nodes
        # Here we log the final outcome from Gradio's perspective.
        
        if final_state and final_state.get("error_message"):
            error_msg = final_state['error_message']
            primary_output = f"Workflow Error on App '{app_name}': {error_msg}"
            logger.warning(f"Gradio: Workflow '{app_name}' completed with error: {error_msg}. Final state: {final_state}")
            return primary_output, json.dumps(final_state, indent=2, default=str)

        if final_state and output_key and final_state.get(output_key):
            primary_output = final_state[output_key]
            logger.info(f"Gradio: Workflow '{app_name}' completed successfully. Primary output key '{output_key}' found.")
            logger.debug(f"Gradio: Workflow '{app_name}' final state for UI: {final_state}")
            return primary_output, json.dumps(final_state, indent=2, default=str)
        
        primary_output = f"Workflow for '{app_name}' completed but no primary output was generated or output key mismatch."
        logger.warning(f"Gradio: {primary_output} Final state: {final_state}")
        if final_state:
             return primary_output, json.dumps(final_state, indent=2, default=str)
        else:
            primary_output = f"Gradio: Workflow for '{app_name}' did not produce a final state."
            logger.error(primary_output) # This would be unusual
            return primary_output, "{'error': 'No final state from workflow after execution attempt.'}"

    except Exception as e:
        err_msg = f"Gradio: Critical error during workflow '{app_name}' execution: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg, json.dumps({"critical_error": str(e), "app_name": app_name, "initial_state": initial_state}, indent=2, default=str)

async def handle_health_information(query: str, claim_to_vet: Optional[str]):
    logger.info(f"Gradio: 'handle_health_information' triggered. Query: '{query[:70]}...', Claim: '{str(claim_to_vet)[:70]}...'")
    if not query or not query.strip():
        logger.warning("Gradio: Health query is empty in handler.")
        return "Health query is empty. Please ask a question.", "{'error': 'Empty query from Gradio handler'}"

    is_misinfo = bool(claim_to_vet and claim_to_vet.strip())
    initial_state: HealthInfoWorkflowState = {
        "user_query": query,
        "is_misinfo_check": is_misinfo,
        "claim_to_check": claim_to_vet if is_misinfo else None
    } # type: ignore
    config = {"configurable": {"thread_id": f"gradio-healthinfo-{asyncio.get_running_loop().time()}"}}
    return await run_workflow_gradio("healthinfo", health_info_app, initial_state, config)


async def handle_post_discharge_info(condition: Optional[str], medication: Optional[str], question: str):
    logger.info(f"Gradio: 'handle_post_discharge_info' triggered. Condition: '{condition}', Med: '{medication}', Q: '{question[:70]}...'")
    if not question or not question.strip():
        logger.warning("Gradio: Post-discharge question is empty in handler.")
        return "Your specific question is empty. Please provide a question.", "{'error': 'Empty specific question from Gradio handler'}"
    
    initial_state: PostDischargeWorkflowState = {
        "condition_context": condition if condition and condition.strip() else None,
        "medication_context": medication if medication and medication.strip() else None,
        "user_specific_question": question
    } # type: ignore
    config = {"configurable": {"thread_id": f"gradio-postdischarge-{asyncio.get_running_loop().time()}"}}
    return await run_workflow_gradio("postdischarge", post_discharge_info_app, initial_state, config)


# --- Gradio Interface Definition ---
def build_gradio_app():
    logger.info("Building Gradio application UI...")
    with gr.Blocks(theme=gr.themes.Soft(primary_hue=gr.themes.colors.blue, secondary_hue=gr.themes.colors.sky), title="HealthMate Assistant") as healthmate_gradio_app:
        gr.Markdown(
            # ... (Markdown content)
            """
            # ⚕️ HealthMate: Your AI Health Information Assistant & MCP Server
            Welcome to HealthMate! This application provides several AI-powered tools for health-related information and also functions as an MCP Server.
            *Disclaimer: HealthMate is a technology demonstrator using publicly available data and AI. It is **NOT** a substitute for professional medical advice, diagnosis, or treatment. Always consult with qualified healthcare providers for any medical concerns.*
            """
        )

        with gr.Tab("💡 Health Info & Misinfo Check"):
            # ... (Tab content)
            gr.Markdown("### Ask Health Questions & Vet Information")
            gr.Markdown("Get information on health topics, conditions, or medications. You can also (optionally) provide a specific claim to be vetted against the retrieved information.")
            with gr.Row():
                with gr.Column(scale=2):
                    health_query_input = gr.Textbox(lines=3, label="Your Health Question", placeholder="e.g., 'What are the symptoms of Type 2 Diabetes?', 'Tell me about Metformin.'")
                    health_claim_input = gr.Textbox(lines=3, label="Claim to Vet (Optional)", placeholder="e.g., 'Does drinking lemon water daily cure high blood pressure?'")
                    health_run_button = gr.Button("💬 Get Info & Vet Claim", variant="primary")
                with gr.Column(scale=3):
                    health_output_answer = gr.Textbox(label="ℹ️ Information & Vetting Result", lines=15, interactive=False)
            
            health_run_button.click(
                fn=handle_health_information,
                inputs=[health_query_input, health_claim_input],
                outputs=[health_output_answer, gr.Textbox(visible=False)]
            )


        with gr.Tab("🏠 Post-Discharge Support"):
            # ... (Tab content)
            gr.Markdown("### General Information for Post-Discharge Care")
            gr.Markdown("Specify a condition and/or medication along with your question to get relevant (general) post-discharge information. This is not personalized medical advice.")
            with gr.Row():
                with gr.Column(scale=2):
                    discharge_condition_input = gr.Textbox(label="Relevant Condition (Optional)", placeholder="e.g., 'Recovery after minor surgery', 'Managing a new asthma diagnosis'")
                    discharge_medication_input = gr.Textbox(label="Relevant Medication (Optional)", placeholder="e.g., 'Lisinopril', 'Pain reliever X'")
                    discharge_question_input = gr.Textbox(lines=3, label="Your Specific Question", placeholder="e.g., 'What are common recovery milestones?', 'What foods should I avoid with this medication?'")
                    discharge_run_button = gr.Button("📖 Get Post-Discharge Information", variant="primary")
                with gr.Column(scale=3):
                    discharge_output_response = gr.Textbox(label="📖 Information Response", lines=15, interactive=False)

            discharge_run_button.click(
                fn=handle_post_discharge_info,
                inputs=[discharge_condition_input, discharge_medication_input, discharge_question_input],
                outputs=[discharge_output_response, gr.Textbox(visible=False)]
            )

        gr.Markdown(
            """
            ---
            **MCP Server Information**
            This HealthMate application also serves as an MCP (Model Context Protocol) Server.
            - **Endpoint**: Send `POST` requests to `/mcp` on this Space's URL.
            - **Request Body Format**: `{"tool_name": "your_tool_name", "tool_input": {"param1": "value1", ...}}`
            - **Available Tools**: `search_pubmed`, `get_fda_drug_info`. 
            *(Refer to `README.md` or `app.py` for more details on tools and parameters.)*
            """
        )
    logger.info("Gradio application UI built successfully.")
    return healthmate_gradio_app

if __name__ == '__main__':
    # This block is for running this Gradio file standalone for UI testing
    logger.info("Running Gradio interface standalone for testing...")
    ui = build_gradio_app()
    ui.launch(debug=True) # debug=True for Gradio's own debug features