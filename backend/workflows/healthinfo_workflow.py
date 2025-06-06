# healthmate_app/backend/workflows/healthinfo_workflow.py
from typing import TypedDict, List, Optional, Dict, Any
from langgraph.graph import StateGraph, END

from backend.tools.mcp_tools_registry import (
    tool_get_fda_drug_info,
    tool_search_pubmed,
    tool_get_health_gov_topic
)
# from backend.workflows.common_states import HealthDataRetrievalState (could be used if refactored)

class HealthInfoWorkflowState(TypedDict):
    user_query: str
    is_misinfo_check: bool
    claim_to_check: Optional[str]
    
    # Tool outputs
    fda_info_result: Optional[Dict[str, Any]]
    pubmed_research_results: Optional[List[Dict[str, Any]]]
    health_gov_info_result: Optional[Dict[str, Any]]
    
    # Processed data
    extracted_drug_name: Optional[str] # If a drug is identified in the query
    
    # Final outputs
    synthesized_answer: Optional[str]
    vetting_conclusion: Optional[str] # Specific to misinfo check
    
    error_message: Optional[str]
    debug_log: List[str]

# --- Node Functions ---

async def w2_initialize_state(state: HealthInfoWorkflowState) -> HealthInfoWorkflowState:
    state['debug_log'] = ["W2: Initializing state."]
    state['fda_info_result'] = None
    state['pubmed_research_results'] = []
    state['health_gov_info_result'] = None
    state['extracted_drug_name'] = None
    state['synthesized_answer'] = None
    state['vetting_conclusion'] = None
    state['error_message'] = None
    return state

async def w2_preprocess_query_node(state: HealthInfoWorkflowState) -> HealthInfoWorkflowState:
    state['debug_log'].append("W2: Preprocessing Query Node")
    query = state.get("user_query", "").lower()
    if not query:
        state['error_message'] = "User query is empty."
        state['debug_log'].append("W2: Error - Empty query.")
        return state

    # Very naive drug name extraction - can be improved with NER or regex
    # Looks for patterns like "side effects of [drug]", "what is [drug]", "info on [drug]"
    drug_keywords = ["side effects of", "what is", "tell me about", "information on", "info on", "about", "drug", "medication"]
    extracted_drug = None
    for kw in drug_keywords:
        if kw in query:
            # Simplistic: takes text after keyword, assumes it's short
            potential_drug = query.split(kw, 1)[-1].strip().split(" ")[0].strip("?.!") 
            if 3 < len(potential_drug) < 20 and potential_drug.isalnum(): # basic sanity check
                extracted_drug = potential_drug
                break
    
    # If no keyword match, but query is short (e.g. just "metformin")
    if not extracted_drug and len(query.split()) <= 2 and query.isalnum():
        extracted_drug = query

    if extracted_drug:
        state['extracted_drug_name'] = extracted_drug
        state['debug_log'].append(f"W2: Extracted potential drug name: {extracted_drug}")
    else:
        state['debug_log'].append("W2: No specific drug name extracted from query.")
    return state

async def w2_fetch_information_node(state: HealthInfoWorkflowState) -> HealthInfoWorkflowState:
    state['debug_log'].append("W2: Fetching Information Node")
    if state.get("error_message"): return state

    query = state.get("user_query", "")
    drug_name = state.get("extracted_drug_name")

    # Fetch FDA info if a drug name was extracted
    if drug_name:
        state['debug_log'].append(f"W2: Fetching FDA info for: {drug_name}")
        state["fda_info_result"] = await tool_get_fda_drug_info(drug_name=drug_name)
        if state["fda_info_result"] and not state["fda_info_result"].get("error"):
            state['debug_log'].append(f"W2: FDA info retrieved for {drug_name}.")
        else:
            state['debug_log'].append(f"W2: No/Error FDA info for {drug_name}: {state['fda_info_result']}")


    # Always search PubMed for broader context or if not a clear drug query
    # If misinfo check, query might be the claim itself or related keywords
    pubmed_query = state.get("claim_to_check") if state.get("is_misinfo_check") and state.get("claim_to_check") else query
    state['debug_log'].append(f"W2: Fetching PubMed info for query: '{pubmed_query}'")
    state["pubmed_research_results"] = await tool_search_pubmed(query=pubmed_query, max_results=2) # Get a couple of articles
    state['debug_log'].append(f"W2: PubMed results: {len(state['pubmed_research_results'] or [])} articles.")

    # Fetch Health.gov info based on general query or drug name (less likely to have drug-specific pages)
    health_gov_query = drug_name if drug_name else query.split(' ')[0] # very simple heuristic
    state['debug_log'].append(f"W2: Fetching Health.gov info for topic: '{health_gov_query}'")
    state["health_gov_info_result"] = await tool_get_health_gov_topic(topic_query=health_gov_query)
    if state["health_gov_info_result"] and not state["health_gov_info_result"].get("error"):
        state['debug_log'].append(f"W2: Health.gov info retrieved for {health_gov_query}.")
    else:
        state['debug_log'].append(f"W2: No/Error Health.gov info for {health_gov_query}: {state['health_gov_info_result']}")
        
    return state

async def w2_synthesize_and_vet_node(state: HealthInfoWorkflowState) -> HealthInfoWorkflowState:
    state['debug_log'].append("W2: Synthesizing and Vetting Node")
    if state.get("error_message"):
        state['synthesized_answer'] = f"Could not process your request due to an error: {state['error_message']}"
        return state

    parts = [f"HealthMate Information Regarding: \"{state.get('user_query', '')}\""]
    all_retrieved_text_lower = "" # For misinfo check

    # FDA Info
    fda_info = state.get("fda_info_result")
    if fda_info and not fda_info.get("error"):
        parts.append(f"\n--- FDA Information for {fda_info.get('drug_name_queried', state.get('extracted_drug_name','this drug'))} ({fda_info.get('source', 'OpenFDA')}) ---")
        parts.append(f"  Brand Name(s): {', '.join(fda_info.get('brand_name', ['N/A']))}")
        parts.append(f"  Generic Name(s): {', '.join(fda_info.get('generic_name', ['N/A']))}")
        inds = fda_info.get('indications_and_usage', ["N/A"])
        parts.append(f"  Indications: {inds[0][:250] + '...' if isinstance(inds, list) and inds and len(inds[0]) > 250 else inds}")
        warns = fda_info.get('warnings_and_precautions', ["N/A"])
        parts.append(f"  Key Warnings: {warns[0][:250] + '...' if isinstance(warns, list) and warns and len(warns[0]) > 250 else warns}")
        all_retrieved_text_lower += json.dumps(fda_info).lower()
    elif state.get("extracted_drug_name"):
        parts.append(f"\n--- FDA Information for {state.get('extracted_drug_name')} ---")
        parts.append("  No specific information found or an error occurred while fetching from OpenFDA.")

    # PubMed Info
    pubmed_results = state.get("pubmed_research_results", [])
    if pubmed_results and not any(res.get("error") for res in pubmed_results):
        parts.append("\n--- PubMed Research Highlights ---")
        for i, res in enumerate(pubmed_results):
            parts.append(f"  [{i+1}] Title: {res.get('title', 'N/A')}")
            parts.append(f"      Summary Snippet: {res.get('summary', 'N/A')[:150]}...")
            all_retrieved_text_lower += (res.get("title", "") + res.get("summary", "")).lower()
    else:
        parts.append("\n--- PubMed Research ---")
        parts.append("  No relevant articles found or an error occurred.")
        
    # Health.gov Info
    health_gov_info = state.get("health_gov_info_result")
    if health_gov_info and not health_gov_info.get("error"):
        parts.append(f"\n--- General Information ({health_gov_info.get('source', 'Health.gov')}) ---")
        parts.append(f"  Topic: {health_gov_info.get('topic', 'N/A')}")
        parts.append(f"  Summary: {health_gov_info.get('summary', 'N/A')}")
        all_retrieved_text_lower += json.dumps(health_gov_info).lower()
    else:
        parts.append("\n--- General Information (Health.gov) ---")
        parts.append("  No specific topic information found or an error occurred.")

    # Misinformation Vetting Logic (Simplified)
    if state.get("is_misinfo_check") and state.get("claim_to_check"):
        claim_lower = state["claim_to_check"].lower()
        parts.append(f"\n--- Vetting Claim: \"{state['claim_to_check']}\" ---")
        
        # Basic keyword check: Does any part of the claim appear in reputable sources?
        # This is extremely naive. A real system needs semantic similarity, contradiction detection, etc.
        keywords_from_claim = [word for word in claim_lower.split() if len(word) > 3] # simple tokenization
        found_keywords_in_sources = any(kw in all_retrieved_text_lower for kw in keywords_from_claim)

        vetting_msg = ""
        if "cure" in claim_lower and ("cancer" in claim_lower or "diabetes" in claim_lower or "aids" in claim_lower):
            # Check for specific "cure" claims which are often misinformation for chronic/serious diseases
            if "cure" not in all_retrieved_text_lower or \
               any(x in all_retrieved_text_lower for x in ["treatment", "management", "no cure", "remission"]):
                vetting_msg = "The claim of a 'cure' for this condition should be treated with extreme caution. Reputable sources typically discuss treatment, management, or remission rather than outright cures for many serious conditions. Always consult healthcare professionals."
            else: # "cure" was found in retrieved text, still needs caution
                 vetting_msg = "While some information related to the claim was found, claims of 'cures' for complex diseases require careful scrutiny. Verify with multiple trusted medical sources and professionals."
        elif found_keywords_in_sources:
            vetting_msg = "Some terms from your claim were found in the retrieved information. Please review the provided details carefully to assess the validity of the claim. HealthMate cannot confirm or deny the claim's truthfulness but provides related context."
        else:
            vetting_msg = "The provided claim could not be directly substantiated or refuted with the information retrieved by HealthMate. It's recommended to seek information from trusted medical sources or healthcare professionals regarding this claim."
        
        state["vetting_conclusion"] = vetting_msg
        parts.append(f"  Conclusion: {vetting_msg}")

    if len(parts) == 1: # Only the initial header
        parts.append("\nHealthMate could not retrieve specific information for your query using the available tools. Please try rephrasing or be more specific.")
    
    parts.append("\n\nDisclaimer: HealthMate provides information from public sources and is not a substitute for professional medical advice. Always consult a healthcare provider for medical concerns.")
    state["synthesized_answer"] = "\n".join(parts)
    state['debug_log'].append("W2: Synthesis and vetting complete.")
    return state

# --- Graph Definition ---
def build_healthinfo_workflow():
    workflow = StateGraph(HealthInfoWorkflowState)

    workflow.add_node("initialize_state", w2_initialize_state)
    workflow.add_node("preprocess_query", w2_preprocess_query_node)
    workflow.add_node("fetch_information", w2_fetch_information_node)
    workflow.add_node("synthesize_and_vet", w2_synthesize_and_vet_node)

    workflow.set_entry_point("initialize_state")
    workflow.add_edge("initialize_state", "preprocess_query")
    workflow.add_edge("preprocess_query", "fetch_information")
    workflow.add_edge("fetch_information", "synthesize_and_vet")
    workflow.add_edge("synthesize_and_vet", END)

    return workflow.compile()

health_info_app = build_healthinfo_workflow()


if __name__ == '__main__':
    import asyncio
    import json

    async def run_test():
        print("--- Testing Health Info Workflow ---")
        config = {"configurable": {"thread_id": "test-healthinfo-thread-1"}}

        # Test Case 1: Drug query
        inputs_1 = {
            "user_query": "Tell me about Metformin side effects",
            "is_misinfo_check": False,
            "claim_to_check": None
        }
        final_state_1 = None
        print(f"\nRunning with query: {inputs_1['user_query']}")
        async for event in health_info_app.astream(inputs_1, config=config, stream_mode="values"):
            final_state_1 = event
        print(f"\nSynthesized Answer (Test 1):\n{final_state_1.get('synthesized_answer')}")
        # print(f"Debug Log (Test 1):\n" + "\n".join(final_state_1.get('debug_log', [])))


        # Test Case 2: General health query
        inputs_2 = {
            "user_query": "How to prevent the flu?",
            "is_misinfo_check": False,
            "claim_to_check": None
        }
        final_state_2 = None
        print(f"\nRunning with query: {inputs_2['user_query']}")
        async for event in health_info_app.astream(inputs_2, config=config, stream_mode="values"):
            final_state_2 = event
        print(f"\nSynthesized Answer (Test 2):\n{final_state_2.get('synthesized_answer')}")

        # Test Case 3: Misinformation Vetting
        inputs_3 = {
            "user_query": "Is it true that garlic cures cancer?", # Query context
            "is_misinfo_check": True,
            "claim_to_check": "Garlic cures all types of cancer naturally."
        }
        final_state_3 = None
        print(f"\nRunning with Misinfo Check: Claim: '{inputs_3['claim_to_check']}' Query: '{inputs_3['user_query']}'")
        async for event in health_info_app.astream(inputs_3, config=config, stream_mode="values"):
            final_state_3 = event
        print(f"\nSynthesized Answer (Test 3):\n{final_state_3.get('synthesized_answer')}")
        print(f"Vetting Conclusion: {final_state_3.get('vetting_conclusion')}")
        # print(f"Debug Log (Test 3):\n" + "\n".join(final_state_3.get('debug_log', [])))
        
        # Test Case 4: Empty query
        inputs_4 = {"user_query": "", "is_misinfo_check": False, "claim_to_check": None}
        final_state_4 = None
        print(f"\nRunning with empty query...")
        async for event in health_info_app.astream(inputs_4, config=config, stream_mode="values"):
            final_state_4 = event
        print(f"\nSynthesized Answer (Test 4):\n{final_state_4.get('synthesized_answer')}")
        print(f"Error: {final_state_4.get('error_message')}")


    asyncio.run(run_test())