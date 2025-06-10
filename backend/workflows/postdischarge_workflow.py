# healthmate_app/backend/workflows/postdischarge_workflow.py
from typing import TypedDict, Optional, Dict, Any, List
import json # Ensure json is imported
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import AzureChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient 
import os 
from dotenv import load_dotenv 

from logger_config import logger

load_dotenv() 

llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
    openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2023-12-01-preview"),
    openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    temperature=0,
)

client = MultiServerMCPClient( 
    {
        "gradio": {
            "url": "http://127.0.0.1:7890/gradio_api/mcp/sse", 
            "transport": "sse",
        }
    }
)

tools: Optional[List[Any]] = None 

async def initialize_tools(): 
    global tools
    
    if tools is None:
        logger.debug("Tools not initialized for PostDischargeWorkflow. Calling client.get_tools().")
        fetched_tools_from_client = [] 
        try:
            fetched_tools_from_client = await client.get_tools() 
            
            if not isinstance(fetched_tools_from_client, list):
                logger.error(f"client.get_tools() did not return a list, but: {type(fetched_tools_from_client)}. Setting tools to empty list.")
                valid_tools = []
            else:
                valid_tools = []
                for t in fetched_tools_from_client:
                    if hasattr(t, 'name') and isinstance(t.name, str) and \
                       hasattr(t, 'description') and isinstance(t.description, str) and \
                       (hasattr(t, 'ainvoke') and callable(getattr(t, 'ainvoke'))):
                        valid_tools.append(t)
                    else:
                        logger.warning(f"Item from client.get_tools() is not a valid Langchain tool object: {t}. Type: {type(t)}. Skipping.")
            
            tools = valid_tools

            if tools: 
                tool_names = [t.name for t in tools if hasattr(t, 'name')]
                logger.info(f"Successfully initialized tools for PostDischargeWorkflow from client: {tool_names}")
            elif not fetched_tools_from_client:
                logger.warning("client.get_tools() returned no tools or an invalid format. Global tools list is empty.")
            else: 
                logger.warning("client.get_tools() returned items, but none were valid Langchain tools. Global tools list is empty.")
        except Exception as e:
            logger.error(f"Failed to fetch or process tools for PostDischargeWorkflow from client: {e}", exc_info=True)
            tools = [] 
    else: 
        if tools:
            logger.debug(f"Tools for PostDischargeWorkflow already initialized: {[tool.name for tool in tools if hasattr(tool, 'name')]}")
        else:
            logger.debug("Global tools variable for PostDischargeWorkflow was not None, but is empty. Consider re-initialization if this is unexpected.")
    tools = await client.get_tools() 
    return tools

class PostDischargeWorkflowState(TypedDict):
    condition_context: Optional[str]
    medication_context: Optional[str]
    user_specific_question: str
    medication_info_result: Optional[Dict[str, Any]]
    synthesized_response: Optional[str]
    error_message: Optional[str]

async def w3_initialize_state(initial_input: Dict[str, Any]) -> PostDischargeWorkflowState:
    logger.info("W3 (PostDischarge): Initializing state.")
    await initialize_tools() 
    return {
        "condition_context": initial_input.get("condition_context"),
        "medication_context": initial_input.get("medication_context"),
        "user_specific_question": initial_input.get("user_specific_question", ""),
        "medication_info_result": None,
        "synthesized_response": None,
        "error_message": None, 
    }

async def w3_fetch_contextual_info_node(state: PostDischargeWorkflowState) -> PostDischargeWorkflowState:
    logger.info("W3 (PostDischarge): Entering fetch_contextual_info_node.")
    current_error = state.get('error_message') or "" 

    global tools 
    if not tools:
        logger.error("W3: Tools are not initialized. Cannot fetch FDA info.")
        state['error_message'] = (current_error + " Internal error: Tool for fetching medication info not available.").strip()
        return state

    fda_tool = next((t for t in tools if hasattr(t, 'name') and t.name == "tool_get_fda_drug_info"), None)

    if not fda_tool:
        logger.error("W3: 'tool_get_fda_drug_info' not found in initialized tools.")
        state['error_message'] = (current_error + " Internal error: FDA information tool is missing.").strip()
        return state

    if not state.get("user_specific_question", "").strip(): 
        state['error_message'] = (current_error + " User question is empty for post-discharge support.").strip()
        logger.warning(f"W3: {state['error_message']}")
        return state
        
    medication_name_from_context = state.get("medication_context")
    if medication_name_from_context and medication_name_from_context.strip():
        logger.info(f"W3: Fetching FDA info for medication: '{medication_name_from_context}' using '{fda_tool.name}'")
        try:
            tool_response_raw = await fda_tool.ainvoke({"drug_name": medication_name_from_context})
            processed_tool_response = None

            if isinstance(tool_response_raw, dict):
                processed_tool_response = tool_response_raw
            elif isinstance(tool_response_raw, str):
                logger.warning(f"W3: FDA tool returned a string for '{medication_name_from_context}'. Attempting to parse as JSON. Raw string: '{tool_response_raw[:200]}...'")
                try:
                    processed_tool_response = json.loads(tool_response_raw)
                    if not isinstance(processed_tool_response, dict):
                        logger.error(f"W3: Parsed JSON from tool string is not a dict for '{medication_name_from_context}'. Type: {type(processed_tool_response)}")
                        processed_tool_response = {"drug_name_queried": medication_name_from_context, "error": "Tool returned string that parsed to non-dict.", "details": tool_response_raw}
                except json.JSONDecodeError as json_e:
                    logger.error(f"W3: Failed to parse string from FDA tool as JSON for '{medication_name_from_context}': {json_e}. Raw string: '{tool_response_raw[:200]}...'")
                    processed_tool_response = {"drug_name_queried": medication_name_from_context, "error": "Tool returned unparsable string.", "details": tool_response_raw}
            else: # Tool returned something else (None, list, etc.)
                logger.warning(f"W3: FDA tool returned unexpected type for '{medication_name_from_context}'. Type: {type(tool_response_raw)}, Response: {str(tool_response_raw)[:200]}")
                processed_tool_response = {"drug_name_queried": medication_name_from_context, "error": "Unexpected tool output type.", "details": str(tool_response_raw)}

            state["medication_info_result"] = processed_tool_response # Assign the processed response

            # Now check the processed_tool_response (which should always be a dict or None)
            if processed_tool_response and not processed_tool_response.get("error"):
                logger.info(f"W3: FDA info successfully processed for '{medication_name_from_context}'.")
            elif processed_tool_response and processed_tool_response.get("error"):
                # Error already logged or is part of processed_tool_response
                logger.warning(f"W3: FDA info retrieval/processing for '{medication_name_from_context}' resulted in an error: {processed_tool_response.get('details') or processed_tool_response.get('error')}")
                if "Tool returned unexpected output" in processed_tool_response.get("error", "") or \
                   "Tool returned unparsable string" in processed_tool_response.get("error", ""):
                     state['error_message'] = (current_error + f" FDA tool returned problematic output for '{medication_name_from_context}'. ").strip()

            else: # Should ideally not be reached if processed_tool_response is always a dict with error or data
                logger.info(f"W3: No specific FDA info found or unexpected state for '{medication_name_from_context}' after processing. Result: {processed_tool_response}")


        except Exception as e:
            logger.error(f"W3: Exception invoking or processing FDA tool ('{fda_tool.name}') for '{medication_name_from_context}': {e}", exc_info=True)
            state["medication_info_result"] = {"drug_name_queried": medication_name_from_context, "error": f"Exception during tool call/processing: {str(e)}"}
            state['error_message'] = (current_error + f" Error fetching/processing FDA info: {str(e)}").strip() 
    else:
        logger.info("W3: No medication context provided by user for FDA lookup.")
            
    logger.debug(f"W3 State after fetching contextual info: {state}")
    return state

# ... (The rest of the file: W3_DISCLAIMER, w3_generate_response_node, build_postdischarge_workflow, if __name__ == '__main__')
# remains the same as your last provided version.
# Make sure to re-paste it here if you need the full file.

W3_DISCLAIMER = "\n\n*Disclaimer: This information is for general guidance and not a substitute for professional medical advice. Always contact your healthcare provider for any specific medical concerns or before making any decisions related to your health or treatment.*"

async def w3_generate_response_node(state: PostDischargeWorkflowState) -> PostDischargeWorkflowState:
    logger.info("W3 (PostDischarge): Entering generate_response_node (Agent Enhanced).")
    current_error = state.get('error_message') or "" 

    user_q = state.get("user_specific_question", "")
    if not user_q.strip(): 
        if not current_error: 
            current_error = "User question is empty, cannot generate response."
            state['error_message'] = current_error
            logger.warning(f"W3: {current_error}")
        
        if current_error: 
            state["synthesized_response"] = f"Could not generate a response. Reason: {current_error}" + W3_DISCLAIMER
        else:
            state["synthesized_response"] = "I received an empty question. Please provide your specific question for post-discharge support." + W3_DISCLAIMER
        return state

    condition_ctx_from_user = state.get("condition_context")
    medication_ctx_from_user = state.get("medication_context")
    med_info_retrieved = state.get("medication_info_result")

    context_parts = []
    context_parts.append(f"User's Stated Context: Condition='{condition_ctx_from_user or 'Not specified'}' Medication='{medication_ctx_from_user or 'Not specified'}'")
    
    if medication_ctx_from_user: 
        if med_info_retrieved and isinstance(med_info_retrieved, dict) and not med_info_retrieved.get("error"): 
            fda_context = {
                "drug_name_queried": med_info_retrieved.get("drug_name_queried"),
                "brand_name": med_info_retrieved.get("brand_name"),
                "generic_name": med_info_retrieved.get("generic_name"),
                "indications_and_usage": (med_info_retrieved.get("indications_and_usage", ["N/A"])[0] if isinstance(med_info_retrieved.get("indications_and_usage"), list) and med_info_retrieved.get("indications_and_usage") else "N/A")[:300],
                "dosage_and_administration": (med_info_retrieved.get("dosage_and_administration", ["N/A"])[0] if isinstance(med_info_retrieved.get("dosage_and_administration"), list) and med_info_retrieved.get("dosage_and_administration") else "N/A")[:300],
                "adverse_reactions": (med_info_retrieved.get("adverse_reactions", ["N/A"])[0] if isinstance(med_info_retrieved.get("adverse_reactions"), list) and med_info_retrieved.get("adverse_reactions") else "N/A")[:300],
                "warnings_and_precautions": (med_info_retrieved.get("warnings_and_precautions", ["N/A"])[0] if isinstance(med_info_retrieved.get("warnings_and_precautions"), list) and med_info_retrieved.get("warnings_and_precautions") else "N/A")[:300]
            }
            context_parts.append(f"Retrieved OpenFDA Information for '{med_info_retrieved.get('drug_name_queried', medication_ctx_from_user)}':\n{json.dumps(fda_context, indent=2)}")
        elif med_info_retrieved and isinstance(med_info_retrieved, dict) and med_info_retrieved.get("error"): 
            context_parts.append(f"Note on OpenFDA Information for '{medication_ctx_from_user}': An error occurred during retrieval - {med_info_retrieved.get('details', med_info_retrieved.get('error'))}")
        else: 
            context_parts.append(f"Note on OpenFDA Information for '{medication_ctx_from_user}': No specific drug information was found or an issue occurred with retrieval. Retrieved data: {str(med_info_retrieved)[:200]}")
    
    context_data_str = "\n\n---\n\n".join(context_parts)
    logger.debug(f"W3: Context prepared for Post-Discharge LLM (first 200 chars): {context_data_str[:200]}...")
    
    system_prompt_content = (
        "You are HealthMate, an AI assistant. Your role is to provide helpful, general post-discharge information based **EXCLUSIVELY AND SOLELY** on the user's original question, their stated context (condition/medication), and any 'Retrieved OpenFDA Information' provided. "
        "**CRITICALLY IMPORTANT INSTRUCTIONS:** "
        "1. **Assess Relevance First:** Evaluate if 'Retrieved OpenFDA Information' (if any) is DIRECTLY relevant to the user's specific question about their mentioned medication and condition. "
        "2. **If FDA Context is Irrelevant, Missing, or Insufficient:** If no FDA data was retrieved, or an error occurred, or the retrieved FDA data does not address the specific aspect of the user's question: "
        "   - Your response MUST clearly state that specific information for that aspect of the medication could not be found in the retrieved FDA documents. "
        "   - **DO NOT summarize unrelated details from the FDA data if they don't answer the user's specific question.** "
        "3. **If User Asks Beyond Medication (General Recovery):** If the user's question also includes aspects of general recovery AND these are not covered by specific FDA data: "
        "   - You MAY provide very general, safe, non-personalized advice. Clearly label this as 'general advice'. "
        "4. **If Context IS Relevant and Sufficient for Medication Details:** Answer medication-specific parts using ONLY the provided relevant FDA information. "
        "5. **No External Knowledge.** "
        "6. **No Medical Advice:** If the question requires specific medical advice, diagnosis, or a personalized treatment plan, state you cannot provide medical advice and recommend consulting their healthcare provider. "
        "7. **Always Conclude:** End by reminding the user to consult their healthcare provider for personal medical concerns. "
        "Maintain an empathetic, professional, and informative tone. Structure for readability. DO NOT use tools."
    )

    human_input_content = f"User's post-discharge question: \"{user_q}\"\n\nContext Provided to you (includes user's statements and retrieved FDA data):\n{context_data_str}"
    
    logger.debug(f"W3: Post-Discharge Agent System Prompt: {system_prompt_content[:100]}...")
    logger.debug(f"W3: Post-Discharge Agent Human Input: {human_input_content[:100]}...")

    try:
        response_agent = create_react_agent(model=llm, tools=tools) 
    except Exception as e:
        logger.error(f"W3: Error creating response_agent: {e}", exc_info=True)
        state['error_message'] = (current_error + f" Error creating response agent: {str(e)}").strip()
        state["synthesized_response"] = "HealthMate encountered an internal error and could not generate a response." + W3_DISCLAIMER
        return state

    llm_agent_response_str = ""
    try:
        agent_messages = [
            SystemMessage(content=system_prompt_content),
            HumanMessage(content=human_input_content)
        ]
        agent_output = await response_agent.ainvoke({"messages": agent_messages})

        if isinstance(agent_output, dict):
            if "output" in agent_output:
                llm_agent_response_str = agent_output["output"]
            elif "messages" in agent_output and agent_output["messages"]:
                for msg in reversed(agent_output["messages"]):
                    if msg.type == "ai": 
                        llm_agent_response_str = msg.content
                        break
            if not llm_agent_response_str: 
                 logger.warning(f"W3: Response agent output dict lacks 'output' or AI message: {agent_output}")
        else:
            logger.warning(f"W3: Unexpected response agent output type: {type(agent_output)}")
        
        if not llm_agent_response_str: 
            state['error_message'] = (current_error + " Response agent returned an empty string.").strip() 
            logger.error(state['error_message'])

    except Exception as e:
        logger.error(f"W3: Error invoking response_agent: {e}", exc_info=True)
        state['error_message'] = (current_error + f" Error during agent response generation: {str(e)}").strip() 
    

    if llm_agent_response_str:
        logger.info("W3: Agent response generation successful for post-discharge.")
        state["synthesized_response"] = llm_agent_response_str + W3_DISCLAIMER
    else:
        final_error_message = state.get('error_message') or "Agent failed to generate a response."
        if not state.get('error_message'): 
            state['error_message'] = final_error_message

        logger.error(f"W3: Agent returned no response string. Error(s): {final_error_message}")
        state["synthesized_response"] = (
            f"HealthMate was unable to generate a response at this time due to: {final_error_message}. "
            "For urgent matters, please contact your healthcare provider." + W3_DISCLAIMER
        )

    logger.debug(f"W3 State after response generation: {state}")
    return state

def build_postdischarge_workflow():
    workflow = StateGraph(PostDischargeWorkflowState)
    workflow.add_node("initialize_state", w3_initialize_state)
    workflow.add_node("fetch_contextual_info", w3_fetch_contextual_info_node)
    workflow.add_node("generate_response", w3_generate_response_node)
    
    workflow.set_entry_point("initialize_state")
    workflow.add_edge("initialize_state", "fetch_contextual_info")
    workflow.add_edge("fetch_contextual_info", "generate_response")
    workflow.add_edge("generate_response", END)
    
    compiled_workflow = workflow.compile()
    logger.info("PostDischarge workflow compiled successfully.")
    return compiled_workflow

post_discharge_info_app = build_postdischarge_workflow()

if __name__ == '__main__':
    import asyncio
    from langchain_core.tools import tool as langchain_tool_decorator # For mock tool

    @langchain_tool_decorator
    async def mock_tool_get_fda_drug_info(drug_name: str) -> Dict[str, Any]:
        """ Mocks fetching FDA drug info. """
        logger.info(f"SELF-TEST MOCK FDA TOOL: Called for drug: {drug_name}")
        if drug_name.lower() == "lisinopril":
            # Simulate returning a JSON string for Lisinopril to test parsing
            return json.dumps({ 
                "drug_name_queried": drug_name, "brand_name": ["Zestril"], "generic_name": ["Lisinopril"],
                "indications_and_usage": ["Treats hypertension."], "adverse_reactions": ["Cough, dizziness."]
            })
        elif drug_name.lower() == "superrarebiotic123":
            return {"drug_name_queried": drug_name, "error": "No information found for SuperRareBiotic123."}
        elif drug_name.lower() == "stringerrordrug":
            return "This is a string error from the mock tool that is not JSON." 
        return {"drug_name_queried": drug_name, "error": f"Mock data not available for {drug_name}."}

    async def run_test():
        logger.info("--- Running PostDischarge Workflow Self-Test (MCP Tools & Agent Based Response with JSON String Parse Test) ---")
        
        global tools
        
        logger.warning("Using MOCK FDA tool for self-test to control tool output.")
        tools = [mock_tool_get_fda_drug_info] 



        test_cases = [
            {
                "name": "Medication Question with FDA Data (Lisinopril - as JSON String)",
                "input_dict": {
                    "condition_context": "hypertension", "medication_context": "Lisinopril", 
                    "user_specific_question": "What are common side effects of Lisinopril, and any tips for managing them?"
                }
            },
            {
                "name": "Fictional Medication Question (SuperRareBiotic123 - as Dict)",
                "input_dict": {
                    "condition_context": "minor infection", "medication_context": "SuperRareBiotic123", 
                    "user_specific_question": "How should I take SuperRareBiotic123 and what if I miss a dose?"
                }
            },
            {
                "name": "Medication that returns non-JSON string error (StringErrorDrug)",
                 "input_dict": {
                    "condition_context": "pain", "medication_context": "StringErrorDrug", 
                    "user_specific_question": "What about StringErrorDrug?"
                }
            },
            {
                "name": "General Recovery Question (No Medication)",
                "input_dict": {
                    "condition_context": "recovery from flu", "medication_context": None, 
                    "user_specific_question": "What general warning signs should I look for?"
                }
            },
            {
                "name": "Empty User Question",
                 "input_dict": {
                    "condition_context": "post-op knee surgery", "medication_context": "Oxycodone", 
                    "user_specific_question": "  " 
                }
            }
        ]
        
        for i, tc in enumerate(test_cases):
            logger.info(f"\n--- Test Case {i+1}: {tc['name']} ---")
            logger.info(f"Input Dict: {tc['input_dict']}")
            final_state = None
            try:
                current_config = {"configurable": {"thread_id": f"test-postdischarge-mcp-agent-thread-{i+1}"}}
                async for event_chunk in post_discharge_info_app.astream(tc['input_dict'], config=current_config, stream_mode="values"): 
                    final_state = event_chunk 
                
                if final_state:
                    logger.info(f"Medication Info Result (Test Case {tc['name']}):\n{json.dumps(final_state.get('medication_info_result'), indent=2)}")
                    logger.info(f"Final Synthesized Response (Test Case {tc['name']}):\n{final_state.get('synthesized_response', 'No synthesized answer found.')}")
                    if final_state.get('error_message'):
                         logger.error(f"Error in workflow for '{tc['name']}': {final_state.get('error_message')}")
                else:
                    logger.error(f"No final state received from workflow for '{tc['name']}'.")
            except Exception as e:
                logger.error(f"Error running test case {tc['name']}: {e}", exc_info=True)
            
            logger.debug(f"Final State (Test Case {tc['name']} - full): {final_state}")
        
        logger.info("\n--- PostDischarge Workflow Self-Test Complete ---")

    asyncio.run(run_test())