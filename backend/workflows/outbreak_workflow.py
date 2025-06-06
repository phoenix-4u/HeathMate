# healthmate_app/backend/workflows/outbreak_workflow.py
from typing import TypedDict, List, Optional, Dict, Any
from langgraph.graph import StateGraph, END

# Import tools directly for use within nodes (though they are also MCP-registered)
# For internal workflow use, we can call them as Python functions.
from backend.tools.mcp_tools_registry import (
    tool_analyze_text_for_symptoms,
    tool_search_pubmed,
    tool_get_health_gov_topic
)
from backend.workflows.common_states import BaseWorkflowState # Optional base

class OutbreakWorkflowState(TypedDict):
    """
    State for the Public Health Outbreak Early Warning workflow.
    """
    raw_input_text: Optional[str]
    detected_symptoms_result: Optional[Dict[str, Any]] # Output from analyze_text_for_symptoms
    pubmed_research_results: Optional[List[Dict[str, Any]]]
    health_gov_info_result: Optional[Dict[str, Any]]
    potential_alert_level: str
    synthesis_prompt: Optional[str] # If we use an LLM for synthesis later
    synthesized_report: Optional[str]
    error_message: Optional[str]
    debug_log: List[str] # For tracking steps

# --- Node Functions ---

async def w1_initialize_state(state: OutbreakWorkflowState) -> OutbreakWorkflowState:
    """Initializes or resets parts of the state for a new run."""
    state['debug_log'] = ["W1: Initializing state."]
    state['detected_symptoms_result'] = None
    state['pubmed_research_results'] = []
    state['health_gov_info_result'] = None
    state['potential_alert_level'] = "None"
    state['synthesized_report'] = None
    state['error_message'] = None
    return state

async def w1_analyze_input_node(state: OutbreakWorkflowState) -> OutbreakWorkflowState:
    state['debug_log'].append("W1: Analyzing Input Node")
    raw_text = state.get("raw_input_text")
    if not raw_text or not raw_text.strip():
        state["error_message"] = "No input text provided for outbreak analysis."
        state['debug_log'].append("W1: Error - No input text.")
        return state

    try:
        symptoms_analysis = await tool_analyze_text_for_symptoms(text=raw_text)
        state["detected_symptoms_result"] = symptoms_analysis
        state['debug_log'].append(f"W1: Symptoms analysis result: {symptoms_analysis.get('symptoms_detected')}")
    except Exception as e:
        state["error_message"] = f"Error during symptom analysis: {str(e)}"
        state['debug_log'].append(f"W1: Exception in symptom analysis: {str(e)}")
    return state

async def w1_research_symptoms_node(state: OutbreakWorkflowState) -> OutbreakWorkflowState:
    state['debug_log'].append("W1: Researching Symptoms Node")
    if state.get("error_message"): # Skip if previous error
        return state
    
    symptoms_data = state.get("detected_symptoms_result")
    detected_symptoms_list = symptoms_data.get("symptoms_detected", []) if symptoms_data else []

    if not detected_symptoms_list or "general concern signal" in detected_symptoms_list[0] and len(detected_symptoms_list) == 1 :
        state['debug_log'].append("W1: No specific symptoms or only general signal, limited research.")
        # Optionally, perform a broader search if only general signal
        if "general concern signal" in detected_symptoms_list[0]:
             pubmed_query = "public health emerging concerns OR unusual illness patterns"
             state["pubmed_research_results"] = await tool_search_pubmed(query=pubmed_query, max_results=1)
             state['debug_log'].append(f"W1: PubMed (general concern): {len(state['pubmed_research_results'] or [])} results.")
        return state

    # Construct PubMed query from detected symptoms
    symptom_query_terms = [s for s in detected_symptoms_list if "general concern" not in s]
    if not symptom_query_terms: # Only general concern was found
        pubmed_query = "public health emerging concerns OR unusual illness patterns"
    else:
        pubmed_query = " AND ".join(symptom_query_terms) + " (emerging OR unusual OR outbreak OR epidemic)"
    
    state['debug_log'].append(f"W1: PubMed query: {pubmed_query}")
    state["pubmed_research_results"] = await tool_search_pubmed(query=pubmed_query, max_results=2)
    state['debug_log'].append(f"W1: PubMed results: {len(state['pubmed_research_results'] or [])} articles found.")

    # Try to get general info on the first relevant detected symptom or a general "outbreak" topic
    health_topic_query = symptom_query_terms[0] if symptom_query_terms else "public health alerts"
    state['debug_log'].append(f"W1: Health.gov query: {health_topic_query}")
    state["health_gov_info_result"] = await tool_get_health_gov_topic(topic_query=health_topic_query)
    if state["health_gov_info_result"] and not state["health_gov_info_result"].get("error"):
         state['debug_log'].append(f"W1: Health.gov topic found: {state['health_gov_info_result'].get('topic')}")
    else:
         state['debug_log'].append(f"W1: No specific Health.gov topic found for '{health_topic_query}'.")
    return state

async def w1_assess_alert_level_node(state: OutbreakWorkflowState) -> OutbreakWorkflowState:
    state['debug_log'].append("W1: Assessing Alert Level Node")
    if state.get("error_message"):
        return state

    symptoms_data = state.get("detected_symptoms_result")
    detected_symptoms_list = symptoms_data.get("symptoms_detected", []) if symptoms_data else []
    pubmed_results = state.get("pubmed_research_results", [])
    health_gov_data = state.get("health_gov_info_result")

    # Simplified logic for alert level
    alert_level = "Low (Monitoring)"
    significant_symptoms = [s for s in detected_symptoms_list if "general concern" not in s]

    if len(significant_symptoms) >= 2 and pubmed_results:
        alert_level = "Medium (Multiple symptoms with related literature)"
        # Check if any pubmed result seems highly relevant (e.g. mentions outbreak, epidemic, or the symptoms)
        for res in pubmed_results:
            title_summary = (res.get("title", "") + res.get("summary", "")).lower()
            if any(kw in title_summary for kw in ["outbreak", "epidemic", "unusual surge"]) or \
               all(sym in title_summary for sym in significant_symptoms[:2]): # Check first 2 symptoms
                alert_level = "High (Multiple symptoms with highly relevant/concerning literature)"
                break
    elif significant_symptoms and pubmed_results:
        alert_level = "Low-Medium (Symptoms detected with some literature)"
    elif significant_symptoms:
        alert_level = "Low (Symptoms detected, no corroborating literature found via basic search)"
    elif "general concern signal" in detected_symptoms_list:
        alert_level = "Low (General concern signal, monitoring advised)"
    
    if health_gov_data and not health_gov_data.get("error") and "alert" in health_gov_data.get("topic","").lower():
        if alert_level.startswith("Low"):
            alert_level = "Medium (Existing health alert may be relevant)"
        elif alert_level.startswith("Medium"):
            alert_level = "High (Existing health alert likely relevant to findings)"


    state["potential_alert_level"] = alert_level
    state['debug_log'].append(f"W1: Assessed Alert Level: {alert_level}")
    return state

async def w1_synthesize_report_node(state: OutbreakWorkflowState) -> OutbreakWorkflowState:
    state['debug_log'].append("W1: Synthesizing Report Node")
    if state.get("error_message"):
        state["synthesized_report"] = f"Report generation failed due to error: {state['error_message']}"
        return state

    report_parts = [
        "--- HealthMate Outbreak Monitoring Report ---",
        f"Input Analyzed: \"{state.get('raw_input_text', 'N/A')[:150]}...\"",
        f"Potential Alert Level: {state.get('potential_alert_level', 'Not Assessed')}",
    ]
    
    symptoms_data = state.get("detected_symptoms_result")
    if symptoms_data and symptoms_data.get("symptoms_detected"):
        report_parts.append(f"Detected Symptoms/Signals: {', '.join(symptoms_data['symptoms_detected'])}")
    else:
        report_parts.append("Detected Symptoms/Signals: None or not specific.")

    pubmed_results = state.get("pubmed_research_results")
    if pubmed_results and not any("error" in res for res in pubmed_results): # Check for error objects
        report_parts.append("\nPubMed Research Highlights:")
        for i, res in enumerate(pubmed_results):
            report_parts.append(f"  [{i+1}] Title: {res.get('title', 'N/A')}")
            report_parts.append(f"      Summary: {res.get('summary', 'N/A')[:200]}...") # Brief summary
    else:
        report_parts.append("\nPubMed Research Highlights: No significant articles found or error in retrieval.")

    health_gov_data = state.get("health_gov_info_result")
    if health_gov_data and not health_gov_data.get("error"):
        report_parts.append(f"\nHealth.gov Topic Information ({health_gov_data.get('source', 'Health.gov')}):")
        report_parts.append(f"  Topic: {health_gov_data.get('topic', 'N/A')}")
        report_parts.append(f"  Summary: {health_gov_data.get('summary', 'N/A')}")
    else:
        report_parts.append("\nHealth.gov Topic Information: No specific topic found or error in retrieval.")
    
    report_parts.append("\n--- End of Report ---")
    state["synthesized_report"] = "\n".join(report_parts)
    state['debug_log'].append("W1: Report synthesis complete.")
    return state

# --- Graph Definition ---
def build_outbreak_workflow():
    workflow = StateGraph(OutbreakWorkflowState)

    workflow.add_node("initialize_state", w1_initialize_state)
    workflow.add_node("analyze_input", w1_analyze_input_node)
    workflow.add_node("research_symptoms", w1_research_symptoms_node)
    workflow.add_node("assess_alert_level", w1_assess_alert_level_node)
    workflow.add_node("synthesize_report", w1_synthesize_report_node)

    workflow.set_entry_point("initialize_state")
    workflow.add_edge("initialize_state", "analyze_input")
    workflow.add_edge("analyze_input", "research_symptoms")
    workflow.add_edge("research_symptoms", "assess_alert_level")
    workflow.add_edge("assess_alert_level", "synthesize_report")
    workflow.add_edge("synthesize_report", END)
    
    # Could add conditional edges here based on error_message to go to an error handling node or END.
    # For simplicity, errors are currently propagated and checked at the start of nodes.

    return workflow.compile()

# Singleton instance of the compiled graph
outbreak_detection_app = build_outbreak_workflow()

if __name__ == '__main__':
    import asyncio
    import json

    async def run_test():
        print("--- Testing Outbreak Workflow ---")
        config = {"configurable": {"thread_id": "test-outbreak-thread-1"}}
        
        # Test Case 1: Clear symptoms
        inputs_1 = {"raw_input_text": "Multiple reports of sudden high fever, persistent dry cough, and extreme fatigue in the City Center area over the past 48 hours. Schools are reporting increased absenteeism."}
        final_state_1 = None
        print(f"\nRunning with input: {inputs_1['raw_input_text'][:50]}...")
        async for event in outbreak_detection_app.astream(inputs_1, config=config, stream_mode="values"):
            # print(f"State update: {event.keys()}")
            final_state_1 = event
        
        print("\nFinal State (Test 1):")
        # print(json.dumps(final_state_1, indent=2, default=str))
        print(f"Report:\n{final_state_1.get('synthesized_report')}")
        print(f"Debug Log:\n" + "\n".join(final_state_1.get('debug_log', [])))

        # Test Case 2: Vague input
        inputs_2 = {"raw_input_text": "Hearing some people are not feeling well lately in the north."}
        final_state_2 = None
        print(f"\nRunning with input: {inputs_2['raw_input_text'][:50]}...")
        async for event in outbreak_detection_app.astream(inputs_2, config=config, stream_mode="values"):
            final_state_2 = event
        print("\nFinal State (Test 2):")
        print(f"Report:\n{final_state_2.get('synthesized_report')}")
        print(f"Debug Log:\n" + "\n".join(final_state_2.get('debug_log', [])))

        # Test Case 3: No input
        inputs_3 = {"raw_input_text": " "}
        final_state_3 = None
        print(f"\nRunning with input: (empty)")
        async for event in outbreak_detection_app.astream(inputs_3, config=config, stream_mode="values"):
            final_state_3 = event
        print("\nFinal State (Test 3):")
        print(f"Report:\n{final_state_3.get('synthesized_report')}")
        print(f"Error Message: {final_state_3.get('error_message')}")
        print(f"Debug Log:\n" + "\n".join(final_state_3.get('debug_log', [])))


    asyncio.run(run_test())