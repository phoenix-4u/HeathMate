# healthmate_app/backend/workflows/healthinfo_workflow.py
from typing import TypedDict, List, Optional, Dict, Any
import json
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, END
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage # Ensure SystemMessage is imported
from langchain import hub 

import os
from dotenv import load_dotenv

from logger_config import logger 

from backend.tools.mcp_tools_registry import (
    tool_get_fda_drug_info,
    tool_search_pubmed
)

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
# We will let create_react_agent use its default prompt, so react_prompt_template is not strictly needed here
# but can be kept if used elsewhere or as a reference.
# try:
#     react_prompt_template = hub.pull("hwchase17/react-json")
# except Exception as e:
#     logger.error(f"Failed to pull ReAct prompt from hub. Error: {e}")
#     react_prompt_template = None # Fallback


async def initialize_tools():
    global tools
    if tools is None:
        logger.debug("Tools not initialized. Calling client.get_tools().")
        try:
            fetched_tools = await client.get_tools()
            if not isinstance(fetched_tools, list):
                logger.error(f"client.get_tools() did not return a list, but: {type(fetched_tools)}. Setting tools to empty list.")
                tools = []
            else:
                valid_tools = []
                for t in fetched_tools:
                    if hasattr(t, 'name') and isinstance(t.name, str) and \
                       hasattr(t, 'description') and isinstance(t.description, str) and \
                       (hasattr(t, 'ainvoke') and callable(getattr(t, 'ainvoke'))) :
                        valid_tools.append(t)
                    else:
                        logger.warning(f"Item from client.get_tools() is not a valid Langchain tool object: {t}. Type: {type(t)}. Skipping.")
                tools = valid_tools
            
            if tools:
                tool_names = [t.name for t in tools if hasattr(t, 'name')]
                logger.info(f"Successfully initialized tools from client: {tool_names}")
            elif not fetched_tools:
                 logger.warning("client.get_tools() returned no tools or an invalid format. No tools initialized.")
            else: 
                 logger.warning("client.get_tools() returned items, but none were valid Langchain tools. No tools initialized.")
        except Exception as e:
            logger.error(f"Failed to fetch or process tools from client: {e}", exc_info=True)
            tools = [] 
    else:
        if tools:
             logger.debug(f"Tools already initialized: {[tool.name for tool in tools if hasattr(tool, 'name')]}")
        else:
            logger.debug("Tools variable exists but is None or empty.")
    tools = fetched_tools
    return tools

class HealthInfoWorkflowState(TypedDict):

    messages: List[Any] 
    user_query: str 
    is_misinfo_check: bool
    claim_to_check: Optional[str]
    search_query_for_tools: Optional[str] 
    fda_info_result: Optional[Dict[str, Any]]
    pubmed_research_results: Optional[List[Dict[str, Any]]]
    extracted_drug_name: Optional[str] 
    synthesized_answer: Optional[str]
    vetting_conclusion: Optional[str]
    error_message: Optional[str]


async def w2_initialize_state(initial_input: Dict[str, Any]) -> HealthInfoWorkflowState:
    logger.info("W2 (HealthInfo): Initializing state.")
    await initialize_tools()

    return {
        "user_query": initial_input.get("user_query", ""),
        "is_misinfo_check": initial_input.get("is_misinfo_check", False),
        "claim_to_check": initial_input.get("claim_to_check"),
        "messages": [], 
        "search_query_for_tools": None,
        "fda_info_result": None,
        "pubmed_research_results": [],
        "extracted_drug_name": None,
        "synthesized_answer": None,
        "vetting_conclusion": None,
        "error_message": None,
    }


async def w2_preprocess_query_node(state: HealthInfoWorkflowState) -> HealthInfoWorkflowState:
    logger.info(f"W2 (HealthInfo): Entering preprocess_query_node. Query: '{state.get('user_query', '')[:70]}...'")
    # ... (rest of the function is the same)
    query = state.get("user_query", "").lower()

    if not query:
        state['error_message'] = "User query is empty."
        logger.warning("W2: User query is empty.")
        return state
    
    drug_keywords = ["side effects of", "what is", "tell me about", "information on", "info on", "about", "drug", "medication"]
    extracted_drug = None
    for kw in drug_keywords:
        if kw in query:
            potential_drug_parts = query.split(kw, 1)[-1].strip().split(" ")
            potential_drug = " ".join(potential_drug_parts[:2]).strip("?.!")
            if 3 < len(potential_drug) < 30 : 
                extracted_drug = potential_drug
                break
    if not extracted_drug and len(query.split()) <= 2:
        possible_drug_query = query.strip("?.!")
        if possible_drug_query.isalnum() and possible_drug_query not in ["flu", "cold", "covid", "pain", "stress", "sleep"]:
            extracted_drug = possible_drug_query
            
    if extracted_drug:
        state['extracted_drug_name'] = extracted_drug
        logger.info(f"W2 (preprocess): Extracted potential drug name: '{extracted_drug}'")
    else:
        logger.info("W2 (preprocess): No specific drug name extracted by simple preprocessing.")
    logger.debug(f"W2 State after preprocessing: {state}")
    return state


async def w2_llm_query_refinement_node(state: HealthInfoWorkflowState) -> HealthInfoWorkflowState:
    logger.info("W2 (HealthInfo): Entering LLM query refinement node.")
    current_error = state.get('error_message', "") 
    if current_error: # Check if already an error
        logger.warning(f"W2: Skipping LLM query refinement due to previous error: {current_error}")
        return state
    
    global tools 
    if not tools: 
        logger.error("W2: Tools not available for LLM query refinement. Aborting node.")
        state['error_message'] = (current_error + " Critical error: Tools not loaded for query refinement.").strip()
        state['search_query_for_tools'] = state.get("user_query", "") 
        return state

    user_q = state.get("user_query", "")
    initial_drug_guess = state.get("extracted_drug_name")

    refinement_system_prompt_content = ( 
        "You are an expert medical librarian assistant. Your task is to analyze a user's health query. "
        "1. Identify the primary medical subject, key symptoms, conditions, or specific drug names mentioned. "
        "2. Formulate a concise and effective search query suitable for academic databases like PubMed. "
        "3. If a specific drug name is clearly identifiable, extract it. "
        "Output your response AS A VALID JSON OBJECT with two keys: 'search_query_for_pubmed' (string) and 'extracted_drug_name' (string, or null if no specific drug is identified or query is not about a drug). "
        "Example for 'side effects of Lipitor': { \"search_query_for_pubmed\": \"Lipitor OR atorvastatin side effects OR adverse events\", \"extracted_drug_name\": \"Lipitor\" }"
    )
    
    human_input_content = f"User health query: \"{user_q}\""
    if initial_drug_guess:
        human_input_content += f"\n(Initial pre-processing suggested a potential drug: \"{initial_drug_guess}\". Please confirm or refine.)"

    logger.debug(f"W2: LLM Query Refinement - System Prompt: {refinement_system_prompt_content[:100]}...")
    logger.debug(f"W2: LLM Query Refinement - Human Input: {human_input_content}")
    
    try:
       
        query_refinement_agent = create_react_agent(model=llm, tools=tools)
    except Exception as e: 
        logger.error(f"W2: Unexpected error creating react_agent for query refinement: {e}", exc_info=True)
        state['error_message'] = (current_error + f" Error creating agent: {e}").strip()
        state['search_query_for_tools'] = user_q 
        return state

    llm_response_str = ""
    try:
        
        agent_messages = [
            SystemMessage(content=refinement_system_prompt_content),
            HumanMessage(content=human_input_content)
        ]
        
        agent_response = await query_refinement_agent.ainvoke({"messages": agent_messages})
        
       
        if isinstance(agent_response, dict):
            if "output" in agent_response: 
                llm_response_str = agent_response["output"]
            elif "messages" in agent_response and agent_response["messages"]: 
                
                for msg in reversed(agent_response["messages"]):
                    if msg.type == "ai": 
                        llm_response_str = msg.content
                        break
            else:
                logger.warning(f"W2: Agent response for query refinement lacks 'output' or suitable 'messages': {agent_response}")
        else:
            logger.warning(f"W2: Unexpected agent response type for query refinement: {type(agent_response)}")

        if not llm_response_str:
            state['error_message'] = (current_error + " Agent returned an empty response string for query refinement.").strip()
            logger.error(state['error_message'])

    except Exception as e:
        logger.error(f"W2: Error during agent-based query refinement invocation: {e}", exc_info=True)
        state['search_query_for_tools'] = user_q 
        state['error_message'] = (current_error + f" Error in agent query refinement invocation: {str(e)}").strip()
        return state 

    if llm_response_str:
        try:
            logger.debug(f"W2: Raw LLM (Agent) response for query refinement: {llm_response_str}")
            json_start = llm_response_str.find('{')
            json_end = llm_response_str.rfind('}') + 1
            if json_start != -1 and json_end != -1 and json_end > json_start:
                json_str = llm_response_str[json_start:json_end]
                refined_data = json.loads(json_str)
                state['search_query_for_tools'] = refined_data.get('search_query_for_pubmed')
                llm_drug = refined_data.get('extracted_drug_name')
                if llm_drug: 
                    state['extracted_drug_name'] = llm_drug
                elif initial_drug_guess and not state['search_query_for_tools']: 
                    state['extracted_drug_name'] = initial_drug_guess 
                    logger.info(f"W2: LLM query refinement did not identify a drug or search query; keeping initial drug guess: '{initial_drug_guess}'")
                else: 
                    state['extracted_drug_name'] = None
                logger.info(f"W2: LLM refined search query: '{state['search_query_for_tools']}', Extracted drug: '{state['extracted_drug_name']}'")
            else:
                logger.warning(f"W2: Agent response for query refinement did not contain valid JSON: {llm_response_str}")
                state['search_query_for_tools'] = user_q 
                state['error_message'] = (current_error + " Agent failed to provide a structured search query (no JSON found).").strip()
        except json.JSONDecodeError as e:
            logger.error(f"W2: Failed to parse JSON from agent query refinement response: {llm_response_str}. Error: {e}", exc_info=True)
            state['search_query_for_tools'] = user_q 
            state['error_message'] = (current_error + " Error parsing agent response for query refinement.").strip()
        except Exception as e:
            logger.error(f"W2: Unexpected error during agent query refinement processing: {e}", exc_info=True)
            state['search_query_for_tools'] = user_q 
            state['error_message'] = (current_error + " Unexpected error in agent query refinement.").strip()
    
        
    if not state.get('search_query_for_tools') and not state.get('error_message'): 
        state['search_query_for_tools'] = user_q 
        logger.warning("W2: search_query_for_tools was None after refinement without explicit error, defaulting to original user query.")
    elif not state.get('search_query_for_tools') and state.get('error_message'):
        logger.warning("W2: search_query_for_tools is None due to prior error, will use original user query if needed.")
        state['search_query_for_tools'] = user_q 

    logger.debug(f"W2 State after LLM query refinement: {state}")
    return state

async def w2_fetch_information_node(state: HealthInfoWorkflowState) -> HealthInfoWorkflowState:
    logger.info("W2 (HealthInfo): Entering fetch_information_node.")
    current_error = state.get('error_message', "")
    if current_error and "agent query refinement" not in current_error and "Tools not loaded" not in current_error : 
         if not state.get('search_query_for_tools') and not state.get('extracted_drug_name'):
            logger.warning(f"W2: Skipping fetch_information_node due to critical previous error: {current_error} and no query.")
            return state
         else:
            logger.warning(f"W2: Proceeding with fetch despite refinement error, using query: {state.get('search_query_for_tools')}")
    
    global tools 
    if not tools:
        logger.error("W2: Tools not available for fetching information. Aborting node.")
        state['error_message'] = (current_error + " Critical error: Tools not loaded for fetching.").strip()
        return state
        
    fda_tool = next((t for t in tools if hasattr(t, 'name') and t.name == "tool_get_fda_drug_info"), None)
    pubmed_tool = next((t for t in tools if hasattr(t, 'name') and t.name == "tool_search_pubmed"), None)

    query_for_pubmed = state.get("search_query_for_tools") or state.get("user_query", "") 
    drug_name_for_fda = state.get("extracted_drug_name") 

    if not query_for_pubmed and not drug_name_for_fda:
        logger.warning("W2: No search query or drug name available for fetching information.")
        state['error_message'] = (current_error + " No usable query for information retrieval.").strip()
        return state

    if drug_name_for_fda:
        if fda_tool:
            
            logger.info(f"W2: Fetching FDA info for extracted drug: '{drug_name_for_fda}' using tool: {fda_tool.name}")
            try:
                fda_result = await fda_tool.ainvoke({"drug_name": drug_name_for_fda})
                state["fda_info_result"] = fda_result if isinstance(fda_result, dict) else {"error": "Tool returned non-dict", "details": str(fda_result), "drug_name_queried": drug_name_for_fda}
                if state["fda_info_result"] and not state["fda_info_result"].get("error"):
                    logger.info(f"W2: FDA info successfully retrieved for '{drug_name_for_fda}'.")
                elif state["fda_info_result"] and state["fda_info_result"].get("error"):
                    logger.warning(f"W2: FDA info retrieval for '{drug_name_for_fda}' resulted in an error: {state['fda_info_result'].get('details') or state['fda_info_result'].get('error')}")
                else: 
                    logger.info(f"W2: No FDA info found or unexpected result for '{drug_name_for_fda}'. Result: {state['fda_info_result']}")
            except Exception as e:
                logger.error(f"W2: Error invoking FDA tool for '{drug_name_for_fda}': {e}", exc_info=True)
                state["fda_info_result"] = {"error": f"Failed to invoke FDA tool: {e}", "drug_name_queried": drug_name_for_fda}
        else:
            logger.error("W2: FDA tool (tool_get_fda_drug_info) not found.")
            state["fda_info_result"] = {"error": "FDA tool not available", "drug_name_queried": drug_name_for_fda}
    else:
        logger.info("W2: No specific drug name identified for FDA lookup.")

    if query_for_pubmed: 
        if pubmed_tool:
           
            logger.info(f"W2: Fetching PubMed info using query: '{query_for_pubmed}' with tool: {pubmed_tool.name}")
            try:
                
                tool_input = {"query": query_for_pubmed}
                
                pubmed_results = await pubmed_tool.ainvoke(tool_input)
                state["pubmed_research_results"] = pubmed_results if isinstance(pubmed_results, list) else [{"error": "Tool returned non-list", "details": str(pubmed_results), "query_used": query_for_pubmed}]
                logger.info(f"W2: PubMed research found {len(state['pubmed_research_results'] or [])} articles for query: '{query_for_pubmed}'.")
            except Exception as e:
                logger.error(f"W2: Error invoking PubMed tool for query '{query_for_pubmed}': {e}", exc_info=True)
                state["pubmed_research_results"] = [{"error": f"Failed to invoke PubMed tool: {e}", "query_used": query_for_pubmed}]
        else:
            logger.error("W2: PubMed tool (tool_search_pubmed) not found.")
            state["pubmed_research_results"] = [{"error": "PubMed tool not available", "query_used": query_for_pubmed}]
    else:
        logger.info("W2: No query available for PubMed search.")
        state["pubmed_research_results"] = [] 
        
    logger.debug(f"W2 State after fetching information: {state}")
    return state

async def w2_synthesize_and_vet_node(state: HealthInfoWorkflowState) -> HealthInfoWorkflowState:
    logger.info("W2 (HealthInfo): Entering synthesize_and_vet_node (Agent Enhanced).")
    current_error = state.get('error_message', "")

    user_q_original = state.get("user_query", "")
    claim = state.get("claim_to_check")
    is_vetting = state.get("is_misinfo_check", False)

    context_parts = []
    
    fda_info = state.get("fda_info_result")
    if fda_info and not fda_info.get("error"):
        fda_context = {
            "drug_name_queried": fda_info.get("drug_name_queried"),
            "brand_name": fda_info.get("brand_name"),
            "generic_name": fda_info.get("generic_name"),
            "indications_and_usage": (fda_info.get("indications_and_usage", ["N/A"])[0] if isinstance(fda_info.get("indications_and_usage"), list) and fda_info.get("indications_and_usage") else "N/A")[:500],
            "warnings_and_precautions": (fda_info.get("warnings_and_precautions", ["N/A"])[0] if isinstance(fda_info.get("warnings_and_precautions"), list) and fda_info.get("warnings_and_precautions") else "N/A")[:500],
        }
        context_parts.append(f"OpenFDA Information:\n{json.dumps(fda_context, indent=2)}")
    elif state.get("extracted_drug_name"): 
        context_parts.append(f"Note: Attempted to find OpenFDA information for '{state.get('extracted_drug_name')}'. Result: {json.dumps(fda_info, indent=2) if fda_info else 'No information retrieved.'}")

    pubmed_results = state.get("pubmed_research_results", [])
    if pubmed_results and not any(isinstance(res, dict) and res.get("error", False) for res in pubmed_results):
        pubmed_context_list = []
        for i, res in enumerate(pubmed_results):
            if isinstance(res, dict): 
                 pubmed_context_list.append(f"PubMed Article {i+1}:\nTitle: {res.get('title', 'N/A')}\nSummary: {res.get('summary', 'N/A')[:500]}")
        if pubmed_context_list:
            context_parts.append(f"PubMed Research Highlights:\n" + "\n".join(pubmed_context_list))
    elif not pubmed_results: 
        context_parts.append("PubMed Research Highlights: No relevant articles were found for the query.")
    else: 
        context_parts.append(f"PubMed Research Highlights: There was an issue retrieving or processing PubMed articles, or no articles found. Data: {json.dumps(pubmed_results, indent=2)}")
    context_data_str = "\n\n---\n\n".join(context_parts) if context_parts else "No specific information was retrieved from OpenFDA or PubMed for your query."
    logger.debug(f"W2: Context prepared for Synthesis Agent (length {len(context_data_str)}): {context_data_str[:300]}...")

    synthesis_system_prompt_content = ( 
        "You are HealthMate, an AI assistant. Your primary function is to provide health information based **EXCLUSIVELY AND SOLELY** on the user's original question and the context data provided below from OpenFDA and PubMed. "
        "**CRITICALLY IMPORTANT INSTRUCTIONS:** "
        "1. **Assess Relevance First:** Critically evaluate if the provided context data is DIRECTLY relevant. "
        "2. **If Context is Irrelevant or Insufficient:** State this clearly. DO NOT summarize irrelevant context. "
        "3. **If Context IS Relevant and Sufficient:** Answer factually using ONLY the provided information. "
        "4. **No External Knowledge.** "
        "5. **No Medical Advice.** Always end by reminding to consult a healthcare professional. "
        "6. **Clarity and Conciseness.** "
        "7. **Tool Usage Prohibited:** For this final synthesis step, DO NOT use any tools. Base your answer ONLY on the provided context data and the user's question."
    )

    human_input_for_synthesis = f"User's original question: \"{user_q_original}\"\n\n"
    if is_vetting and claim:
        human_input_for_synthesis += f"User also wants to vet this claim: \"{claim}\"\n\n"
    human_input_for_synthesis += f"Provided Context Data:\n{context_data_str}\n\n"
    if is_vetting and claim:
         human_input_for_synthesis += "Please analyze the claim based *only* on the provided context. State whether the context supports, contradicts, or is insufficient. Then, provide a synthesized answer to the original question using the context. Remember, do not use any tools for this task."
    else:
        human_input_for_synthesis += "Please provide a synthesized answer to the question using the context. Remember, do not use any tools for this task."
        
    logger.debug(f"W2: Synthesis Agent System Prompt: {synthesis_system_prompt_content[:150]}...")
    logger.debug(f"W2: Synthesis Agent Human Input Preview: {human_input_for_synthesis[:200]}...")
    
    try:
        
        synthesis_agent = create_react_agent(model=llm, tools=tools) 
    except Exception as e:
        logger.error(f"W2: Unexpected error creating react_agent for synthesis: {e}", exc_info=True)
        state['error_message'] = (current_error + f" Error creating synthesis agent: {e}").strip()
        state["synthesized_answer"] = "HealthMate was unable to process your request due to an internal error (synthesis agent creation)."
        return state

    llm_response = ""
    try:
        agent_messages_for_synthesis = [
            SystemMessage(content=synthesis_system_prompt_content),
            HumanMessage(content=human_input_for_synthesis)
        ]
        agent_response = await synthesis_agent.ainvoke({"messages": agent_messages_for_synthesis})

        if isinstance(agent_response, dict):
            if "output" in agent_response:
                llm_response = agent_response["output"]
            elif "messages" in agent_response and agent_response["messages"]:
                for msg in reversed(agent_response["messages"]):
                    if msg.type == "ai":
                        llm_response = msg.content
                        break
            if not llm_response: 
                 logger.warning(f"W2: Synthesis agent response dict lacks 'output' or AI message content: {agent_response}")
        else:
            logger.warning(f"W2: Unexpected synthesis agent response type: {type(agent_response)}")
        
        if not llm_response:
            state['error_message'] = (current_error + " Synthesis agent returned an empty response string.").strip()
            logger.error(state['error_message'])

    except Exception as e:
        logger.error(f"W2: Error during agent-based synthesis invocation: {e}", exc_info=True)
        state['error_message'] = (current_error + f" LLM Service Error during synthesis: {str(e)}").strip()

    disclaimer = "\n\n*Disclaimer: HealthMate provides AI-generated information based on data from public APIs and is not a substitute for professional medical advice. Always consult a healthcare provider for any medical concerns.*"

    if llm_response: 
        logger.info("W2: Agent synthesis successful (got a response string).")
        
        if "could not find information directly addressing your question" in llm_response.lower() or \
           "insufficient information to address your specific concern" in llm_response.lower() or \
           "retrieved documents are not relevant" in llm_response.lower():
            logger.warning(f"W2: Agent correctly stated insufficient or irrelevant context: '{llm_response[:150]}...'")
        state["synthesized_answer"] = llm_response + disclaimer
        if is_vetting:
            state["vetting_conclusion"] = "Vetting analysis is incorporated into the LLM response."

    else: 
        logger.error(f"W2: Agent synthesis resulted in an empty response. Error(s) encountered: {state.get('error_message')}")
        fallback_detail = state.get('error_message', "Synthesis agent returned no usable output.")
        state["synthesized_answer"] = (
            f"HealthMate encountered an issue and could not generate a detailed response at this time. "
            f"Details: {fallback_detail}"
            "\nPlease try rephrasing your query or try again later." + disclaimer
        )
        
    logger.debug(f"W2 State after synthesis: {state}")
    return state

def build_healthinfo_workflow():
    workflow = StateGraph(HealthInfoWorkflowState)

    
    workflow.add_node("initialize_state", w2_initialize_state)
    workflow.add_node("preprocess_query", w2_preprocess_query_node)
    workflow.add_node("llm_query_refinement", w2_llm_query_refinement_node)
    workflow.add_node("fetch_information", w2_fetch_information_node)
    workflow.add_node("synthesize_and_vet", w2_synthesize_and_vet_node)

    workflow.set_entry_point("initialize_state")
    workflow.add_edge("initialize_state", "preprocess_query")
    workflow.add_edge("preprocess_query", "llm_query_refinement")
    workflow.add_edge("llm_query_refinement", "fetch_information")
    workflow.add_edge("fetch_information", "synthesize_and_vet")
    workflow.add_edge("synthesize_and_vet", END)
    
    compiled_workflow = workflow.compile()
    logger.info("HealthInfo workflow compiled successfully.")
    return compiled_workflow

health_info_app = build_healthinfo_workflow()

if __name__ == '__main__':
    import asyncio
    async def run_test():
        logger.info("--- Running HealthInfo Workflow Self-Test (Agent Query Refinement & Synthesis with Default Prompt) ---")
        
        
        test_cases = [
            {
                "name": "Vague Query",
                "input_dict": { 
                    "user_query": "I am feeling restless and at night I am not getting much sleep, what could this be related to?",
                    "is_misinfo_check": False, "claim_to_check": None
                }
            },
            {
                "name": "Specific Drug Query",
                "input_dict": {
                    "user_query": "Tell me about the side effects of amlodipine.",
                    "is_misinfo_check": False, "claim_to_check": None
                }
            },
        ]

        for i, tc in enumerate(test_cases):
            logger.info(f"\n--- Test Case {i+1}: {tc['name']} ---")
            logger.info(f"Input: {tc['input_dict']['user_query']}")
            final_state = None
            try:
                current_config = {"configurable": {"thread_id": f"test-healthinfo-default-prompt-thread-{i+1}"}}
                
                async for event_chunk in health_info_app.astream(tc['input_dict'], config=current_config, stream_mode="values"): 
                    final_state = event_chunk 
                
                if final_state:
                    logger.info(f"Refined Search Query: {final_state.get('search_query_for_tools', 'N/A')}")
                    logger.info(f"Extracted Drug: {final_state.get('extracted_drug_name', 'N/A')}")
                    logger.info(f"Synthesized Answer:\n{final_state.get('synthesized_answer', 'No synthesized answer found.')}")
                    if final_state.get('error_message'):
                         logger.error(f"Error in workflow for '{tc['name']}': {final_state.get('error_message')}")
                else:
                    logger.error(f"No final state received from workflow for '{tc['name']}'.")
            except Exception as e:
                logger.error(f"Error running test case {tc['name']}: {e}", exc_info=True)
            logger.debug(f"Final State (Test Case {tc['name']} - full): {final_state}")
        
        logger.info("\n--- HealthInfo Workflow Self-Test Complete ---")

    asyncio.run(run_test())