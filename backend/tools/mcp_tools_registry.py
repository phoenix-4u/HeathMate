# healthmate_app/backend/tools/mcp_tools_registry.py
import asyncio
from typing import List, Dict, Any, Callable, Coroutine

# Import the actual API client functions
from backend.api_clients.pubmed_client import fetch_pubmed_articles # fetch_pubmed_articles_detailed
from backend.api_clients.openfda_client import fetch_fda_drug_info
from backend.api_clients.healthgov_client import fetch_health_gov_topic

# --- Tool Definitions ---
# These functions are wrappers that will be exposed via the MCP server.
# They call the underlying API client functions.

async def tool_search_pubmed(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """
    MCP Tool: Searches PubMed for articles related to the query.
    Input: {"query": "string", "max_results": "int (optional, default 3)"}
    Output: List of article dictionaries (id, title, summary) or error dict.
    """
    print(f"MCP_TOOL: tool_search_pubmed called with query='{query}', max_results={max_results}")
    if not isinstance(query, str) or not query.strip():
        return [{"error": "Invalid input: 'query' must be a non-empty string."}]
    if not isinstance(max_results, int) or max_results <= 0:
        max_results = 3 # Default or correction
    
    # Using the simplified fetch_pubmed_articles for this example
    # For more detail, switch to fetch_pubmed_articles_detailed if fully implemented
    return await fetch_pubmed_articles(query=query, max_results=max_results)

async def tool_get_fda_drug_info(drug_name: str) -> Dict[str, Any]:
    """
    MCP Tool: Fetches drug information from OpenFDA.
    Input: {"drug_name": "string"}
    Output: Drug information dictionary or error dict.
    """
    print(f"MCP_TOOL: tool_get_fda_drug_info called with drug_name='{drug_name}'")
    if not isinstance(drug_name, str) or not drug_name.strip():
        return {"error": "Invalid input: 'drug_name' must be a non-empty string."}
        
    result = await fetch_fda_drug_info(drug_name=drug_name)
    if result is None:
        return {"drug_name_queried": drug_name, "error": "No information found or API unavailable."}
    return result

async def tool_get_health_gov_topic(topic_query: str) -> Dict[str, Any]:
    """
    MCP Tool: Retrieves health topic information (simulated from Health.gov).
    Input: {"topic_query": "string"}
    Output: Health topic dictionary or error dict.
    """
    print(f"MCP_TOOL: tool_get_health_gov_topic called with topic_query='{topic_query}'")
    if not isinstance(topic_query, str) or not topic_query.strip():
        return {"error": "Invalid input: 'topic_query' must be a non-empty string."}

    result = await fetch_health_gov_topic(topic_query=topic_query)
    if result is None:
        return {"topic_queried": topic_query, "error": "Topic not found or information unavailable."}
    return result

async def tool_analyze_text_for_symptoms(text: str) -> Dict[str, Any]:
    """
    MCP Tool: (Simplified) Analyzes text to extract potential symptom keywords.
    Input: {"text": "string"}
    Output: {"symptoms_detected": ["symptom1", "symptom2"], "original_text_preview": "string"}
    """
    print(f"MCP_TOOL: tool_analyze_text_for_symptoms called with text='{text[:50]}...'")
    if not isinstance(text, str): # Allow empty string, might indicate no symptoms
        return {"error": "Invalid input: 'text' must be a string."}

    # This would ideally be a more sophisticated NLP model.
    # For now, simple keyword spotting.
    await asyncio.sleep(0.05) # Simulate processing time
    symptoms_found = []
    text_lower = text.lower()

    # Define a simple list of keywords. In a real system, this would be more extensive.
    symptom_keywords = [
        "fever", "cough", "sore throat", "headache", "fatigue", "rash", "nausea",
        "vomiting", "diarrhea", "shortness of breath", "body ache", "chills",
        "congestion", "runny nose", "loss of taste", "loss of smell", "dizziness",
        "unusual bleeding", "swelling"
    ]

    for keyword in symptom_keywords:
        if keyword in text_lower:
            symptoms_found.append(keyword)
    
    # Generic trigger if specific keywords aren't found but text seems like a report
    if not symptoms_found and ("report" in text_lower or "outbreak" in text_lower or "unusual illness" in text_lower):
        symptoms_found.append("general concern signal (non-specific)")
        
    return {
        "symptoms_detected": list(set(symptoms_found)), # Use set to remove duplicates
        "original_text_preview": text[:100] + "..." if len(text) > 100 else text
    }

# --- MCP Tools Registry ---
# A dictionary to map tool names to their callable functions.
# The MCP server logic will use this to dispatch requests.
# Values can be `Callable[..., Coroutine[Any, Any, Dict[str, Any]]]` for async functions
# or `Callable[..., Dict[str, Any]]]` for sync functions.

ToolsRegistry = Dict[str, Callable[..., Coroutine[Any, Any, Dict[str, Any]]]]

MCP_TOOLS_REGISTRY: ToolsRegistry = {
    "search_pubmed": tool_search_pubmed,
    "get_fda_drug_info": tool_get_fda_drug_info,
    "get_health_gov_topic": tool_get_health_gov_topic,
    "analyze_text_for_symptoms": tool_analyze_text_for_symptoms,
    # Add more tools here as they are developed
}

if __name__ == '__main__':
    async def main():
        print("--- Testing MCP Tool Wrappers ---")

        # Test PubMed tool
        pubmed_res = await tool_search_pubmed(query="influenza treatment", max_results=1)
        print(f"\nPubMed Result: {pubmed_res}")
        pubmed_err = await tool_search_pubmed(query="", max_results=1)
        print(f"PubMed Error (empty query): {pubmed_err}")


        # Test FDA tool
        fda_res = await tool_get_fda_drug_info(drug_name="Metformin")
        print(f"\nFDA Result (Metformin): {fda_res['drug_name_queried'] if fda_res and 'drug_name_queried' in fda_res else 'Error or not found'}")
        # print(fda_res)
        fda_err = await tool_get_fda_drug_info(drug_name="  ")
        print(f"FDA Error (empty drug_name): {fda_err}")
        fda_unknown = await tool_get_fda_drug_info(drug_name="UnknownDrugXYZ999")
        print(f"FDA Result (UnknownDrug): {fda_unknown}")


        # Test Health.gov tool
        hg_res = await tool_get_health_gov_topic(topic_query="healthy diet")
        print(f"\nHealth.gov Result (Healthy Diet): {hg_res.get('topic') if hg_res else 'Error or not found'}")
        # print(hg_res)
        hg_err = await tool_get_health_gov_topic(topic_query=None) # type: ignore
        print(f"Health.gov Error (None query): {hg_err}")


        # Test Symptom Analyzer tool
        symptom_res = await tool_analyze_text_for_symptoms(text="Patient reports high fever, persistent cough, and severe headache for three days.")
        print(f"\nSymptom Analysis Result: {symptom_res.get('symptoms_detected')}")
        # print(symptom_res)
        symptom_res_general = await tool_analyze_text_for_symptoms(text="There's an unusual illness reported in the northern district.")
        print(f"Symptom Analysis (General): {symptom_res_general.get('symptoms_detected')}")
        symptom_err = await tool_analyze_text_for_symptoms(text=123) # type: ignore
        print(f"Symptom Analysis Error (bad input): {symptom_err}")

    asyncio.run(main())