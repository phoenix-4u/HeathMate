# healthmate_app/backend/workflows/postdischarge_workflow.py
from typing import TypedDict, Optional, Dict, Any, List
from langgraph.graph import StateGraph, END

from backend.tools.mcp_tools_registry import (
    tool_get_fda_drug_info,
    tool_get_health_gov_topic
)
# from backend.workflows.common_states import HealthDataRetrievalState (could be used)

class PostDischargeWorkflowState(TypedDict):
    condition_context: Optional[str] # e.g., "Minor Sprain", "Common Cold recovery"
    medication_context: Optional[str] # e.g., "Ibuprofen", "Amoxicillin"
    user_specific_question: str
    
    # Tool outputs
    condition_info_result: Optional[Dict[str, Any]]
    medication_info_result: Optional[Dict[str, Any]]
    
    # Final output
    synthesized_response: Optional[str]
    
    error_message: Optional[str]
    debug_log: List[str]

# --- Node Functions ---

async def w3_initialize_state(state: PostDischargeWorkflowState) -> PostDischargeWorkflowState:
    state['debug_log'] = ["W3: Initializing state."]
    state['condition_info_result'] = None
    state['medication_info_result'] = None
    state['synthesized_response'] = None
    state['error_message'] = None
    return state

async def w3_fetch_contextual_info_node(state: PostDischargeWorkflowState) -> PostDischargeWorkflowState:
    state['debug_log'].append("W3: Fetching Contextual Info Node")
    if not state.get("user_specific_question", "").strip(): # Basic check
        state['error_message'] = "User question is empty for post-discharge support."
        state['debug_log'].append("W3: Error - Empty user question.")
        return state
        
    condition = state.get("condition_context")
    medication = state.get("medication_context")

    if condition and condition.strip():
        state['debug_log'].append(f"W3: Fetching Health.gov info for condition: {condition}")
        # Append "management" or "recovery" to get more relevant topics
        query = f"{condition} management" if "recovery" not in condition.lower() and "management" not in condition.lower() else condition
        state["condition_info_result"] = await tool_get_health_gov_topic(topic_query=query)
        if state["condition_info_result"] and not state["condition_info_result"].get("error"):
             state['debug_log'].append(f"W3: Health.gov info retrieved for {condition}.")
        else:
             state['debug_log'].append(f"W3: No/Error Health.gov info for {condition}: {state['condition_info_result']}")


    if medication and medication.strip():
        state['debug_log'].append(f"W3: Fetching FDA info for medication: {medication}")
        state["medication_info_result"] = await tool_get_fda_drug_info(drug_name=medication)
        if state["medication_info_result"] and not state["medication_info_result"].get("error"):
             state['debug_log'].append(f"W3: FDA info retrieved for {medication}.")
        else:
             state['debug_log'].append(f"W3: No/Error FDA info for {medication}: {state['medication_info_result']}")
             
    return state

async def w3_generate_response_node(state: PostDischargeWorkflowState) -> PostDischargeWorkflowState:
    state['debug_log'].append("W3: Generating Response Node")
    if state.get("error_message"):
        state['synthesized_response'] = f"Could not process your request: {state['error_message']}"
        return state

    parts = [f"HealthMate Post-Discharge Information for your question: \"{state.get('user_specific_question')}\""]
    
    condition = state.get("condition_context")
    medication = state.get("medication_context")
    user_question_lower = state.get("user_specific_question", "").lower()

    if condition:
        parts.append(f"\n--- Regarding your condition: {condition} ---")
        condition_info = state.get("condition_info_result")
        if condition_info and not condition_info.get("error"):
            parts.append(f"  Topic ({condition_info.get('source','Health.gov')}): {condition_info.get('topic', 'N/A')}")
            parts.append(f"  Summary: {condition_info.get('summary', 'No specific summary found.')}")
        else:
            parts.append("  No specific information found for this condition via Health.gov topics.")

    if medication:
        parts.append(f"\n--- Regarding your medication: {medication} ---")
        med_info = state.get("medication_info_result")
        if med_info and not med_info.get("error"):
            parts.append(f"  Brand Name(s): {', '.join(med_info.get('brand_name', ['N/A']))}")
            parts.append(f"  Generic Name(s): {', '.join(med_info.get('generic_name', ['N/A']))}")
            # Only show relevant snippets based on common post-discharge questions
            if "side effect" in user_question_lower:
                se = med_info.get('adverse_reactions', ["N/A"])
                parts.append(f"  Common Adverse Reactions: {se[0][:250]+'...' if isinstance(se,list) and se and len(se[0]) > 250 else se }")
            elif "how to take" in user_question_lower or "dosage" in user_question_lower:
                 # OpenFDA labels have "dosage_and_administration"
                 da = med_info.get('dosage_and_administration', med_info.get('indications_and_usage', ["Refer to prescribing information."]))
                 parts.append(f"  Usage/Administration Info: {da[0][:250]+'...' if isinstance(da,list) and da and len(da[0]) > 250 else da }")
            else: # Generic
                inds = med_info.get('indications_and_usage', ["N/A"])
                parts.append(f"  Indications: {inds[0][:200]+'...' if isinstance(inds,list) and inds and len(inds[0]) > 200 else inds }")
        else:
            parts.append(f"  No specific FDA information found for {medication} or an error occurred.")

    # Add some general advice based on keywords in the question, if no specific info was found
    if len(parts) <= (2 + (1 if condition else 0) + (1 if medication else 0)): # Heuristic: little info added
        if "exercise" in user_question_lower:
            parts.append("\nGeneral Advice: Regarding exercise after discharge, it's crucial to follow your doctor's specific instructions. Typically, start slowly and gradually increase activity as tolerated and advised. If you experience pain or discomfort, stop and consult your healthcare provider.")
        elif "warning signs" in user_question_lower:
            parts.append("\nGeneral Advice: For any condition or after any procedure, common warning signs that warrant contacting your doctor include: worsening pain, fever, chills, unusual redness or swelling, discharge (e.g., from a wound), shortness of breath, or any new or unexpected symptoms. This list is not exhaustive.")
        elif "diet" in user_question_lower or "food" in user_question_lower:
            parts.append("\nGeneral Advice: Follow any dietary instructions given by your doctor. Generally, a balanced diet rich in fruits, vegetables, and lean protein supports recovery. Stay hydrated by drinking plenty of fluids, especially water, unless advised otherwise.")
        elif not condition and not medication: # No context given at all
             parts.append("\nTo provide more specific information, please mention the condition you are recovering from or any specific medications you have questions about.")


    if len(parts) == 1: # Only the initial query echo
         parts.append("\nHealthMate could not find specific information based on your input. Please provide more details about your condition, medication, or question.")

    parts.append("\n\nDisclaimer: This information is for general guidance and not a substitute for professional medical advice. Contact your healthcare provider for any specific medical concerns or before making any decisions related to your health or treatment.")
    state["synthesized_response"] = "\n".join(parts)
    state['debug_log'].append("W3: Response generation complete.")
    return state

# --- Graph Definition ---
def build_postdischarge_workflow():
    workflow = StateGraph(PostDischargeWorkflowState)

    workflow.add_node("initialize_state", w3_initialize_state)
    workflow.add_node("fetch_contextual_info", w3_fetch_contextual_info_node)
    workflow.add_node("generate_response", w3_generate_response_node)

    workflow.set_entry_point("initialize_state")
    workflow.add_edge("initialize_state", "fetch_contextual_info")
    workflow.add_edge("fetch_contextual_info", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow.compile()

post_discharge_info_app = build_postdischarge_workflow()

if __name__ == '__main__':
    import asyncio
    import json

    async def run_test():
        print("--- Testing Post-Discharge Info Workflow ---")
        config = {"configurable": {"thread_id": "test-postdischarge-thread-1"}}

        # Test Case 1: Question about medication and condition
        inputs_1 = {
            "condition_context": "recovery from flu",
            "medication_context": "Ibuprofen",
            "user_specific_question": "What are common side effects I should watch for with Ibuprofen while getting over the flu?"
        }
        final_state_1 = None
        print(f"\nRunning with context: Condition='{inputs_1['condition_context']}', Med='{inputs_1['medication_context']}', Q='{inputs_1['user_specific_question'][:30]}...'")
        async for event in post_discharge_info_app.astream(inputs_1, config=config, stream_mode="values"):
            final_state_1 = event
        print(f"\nSynthesized Response (Test 1):\n{final_state_1.get('synthesized_response')}")
        # print(f"Debug Log (Test 1):\n" + "\n".join(final_state_1.get('debug_log', [])))

        # Test Case 2: General question about a condition
        inputs_2 = {
            "condition_context": "minor knee sprain",
            "medication_context": None,
            "user_specific_question": "When can I start exercising again?"
        }
        final_state_2 = None
        print(f"\nRunning with context: Condition='{inputs_2['condition_context']}', Q='{inputs_2['user_specific_question'][:30]}...'")
        async for event in post_discharge_info_app.astream(inputs_2, config=config, stream_mode="values"):
            final_state_2 = event
        print(f"\nSynthesized Response (Test 2):\n{final_state_2.get('synthesized_response')}")

        # Test Case 3: Question with no context
        inputs_3 = {
            "condition_context": None,
            "medication_context": None,
            "user_specific_question": "What are the warning signs?"
        }
        final_state_3 = None
        print(f"\nRunning with context: No specific context, Q='{inputs_3['user_specific_question'][:30]}...'")
        async for event in post_discharge_info_app.astream(inputs_3, config=config, stream_mode="values"):
            final_state_3 = event
        print(f"\nSynthesized Response (Test 3):\n{final_state_3.get('synthesized_response')}")
        # print(f"Debug Log (Test 3):\n" + "\n".join(final_state_3.get('debug_log', [])))
        
        # Test Case 4: Empty question
        inputs_4 = {
            "condition_context": "flu",
            "medication_context": None,
            "user_specific_question": ""
        }
        final_state_4 = None
        print(f"\nRunning with context: Condition='{inputs_4['condition_context']}', Q='(empty)'")
        async for event in post_discharge_info_app.astream(inputs_4, config=config, stream_mode="values"):
            final_state_4 = event
        print(f"\nSynthesized Response (Test 4):\n{final_state_4.get('synthesized_response')}")
        print(f"Error: {final_state_4.get('error_message')}")


    asyncio.run(run_test())