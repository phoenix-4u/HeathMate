# healthmate_app/backend/tools/mcp_tools_registry.py
import asyncio
import os
import sys
from typing import List, Dict, Any, Callable, Coroutine
import gradio as gr
# from ...logger_config import logger
from backend.api_clients.pubmed_client import fetch_pubmed_articles
from backend.api_clients.openfda_client import fetch_fda_drug_info

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from logger_config import logger


# --- Tool Definitions ---

async def tool_search_pubmed(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """Searches PubMed for medical research articles based on a query.

    This tool interacts with the NCBI E-utils API (PubMed) to find relevant
    articles. It's designed to take a natural language query or specific
    search terms and return a list of article summaries.

    Args:
        query (str): The search term, question, or keywords to search for on PubMed.
                     This should be a non-empty string.
        max_results (int, optional): The maximum number of article summaries to return.
                                     Defaults to 3. Must be a positive integer.
                                     Invalid values will also default to 3.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary represents
                              a found PubMed article. Each article dictionary typically
                              contains keys such as 'id' (PMID), 'title', and 'summary'.
                              If no articles are found, an empty list is returned.
                              In case of an input validation error (e.g., empty query),
                              it returns a list containing a single dictionary with an
                              'error' key (e.g., [{"error": "Invalid input..."}]).
                              If the underlying API call fails, the error structure from
                              `fetch_pubmed_articles` (which also includes an 'error' key)
                              will be propagated.
    """
    logger.info(f"MCP Tool 'tool_search_pubmed' called. Query='{query}', MaxResults={max_results}")
    
    if not isinstance(query, str) or not query.strip():
        logger.warning(f"Invalid input for 'tool_search_pubmed': 'query' must be a non-empty string. Received: '{query}'")
        return [{"error": "Invalid input: 'query' must be a non-empty string."}]
    
    if not isinstance(max_results, int) or max_results <= 0:
        logger.warning(f"Invalid 'max_results' for 'tool_search_pubmed': {max_results}. Defaulting to 3.")
        max_results = 3
    
    # The API client (fetch_pubmed_articles) will perform its own detailed logging
    result = await fetch_pubmed_articles(query=query, max_results=max_results)
    
    logger.debug(f"'tool_search_pubmed' result for query '{query}': {str(result)[:500]}...") # Log snippet of result
    return result

async def tool_get_fda_drug_info(drug_name: str) -> Dict[str, Any]:
    """Fetches detailed information for a specific drug from OpenFDA.

    This tool queries the OpenFDA API (drug label endpoint) to retrieve
    information such as brand names, generic names, indications, warnings,
    adverse reactions, and dosage for a given drug name.

    Args:
        drug_name (str): The brand or generic name of the drug to search for.
                         This should be a non-empty string.

    Returns:
        Dict[str, Any]: A dictionary containing drug information if found.
                        The structure includes keys like 'drug_name_queried',
                        'brand_name' (list), 'generic_name' (list),
                        'indications_and_usage' (list of strings),
                        'warnings_and_precautions' (list of strings), etc.
                        If the drug is not found or the API is unavailable,
                        it returns a dictionary with an 'error' key and a
                        'drug_name_queried' key (e.g., 
                        {"drug_name_queried": "drug_xyz", "error": "No information found..."}).
                        If there's an input validation error (e.g., empty drug_name),
                        it returns {"error": "Invalid input..."}.
                        If the underlying API call fails, the error structure from
                        `fetch_fda_drug_info` (which also includes an 'error' key)
                        will be propagated.
    """
    logger.info(f"MCP Tool 'tool_get_fda_drug_info' called. DrugName='{drug_name}'")
    
    if not isinstance(drug_name, str) or not drug_name.strip():
        logger.warning(f"Invalid input for 'tool_get_fda_drug_info': 'drug_name' must be a non-empty string. Received: '{drug_name}'")
        return {"error": "Invalid input: 'drug_name' must be a non-empty string."}
        
    # The API client (fetch_fda_drug_info) will perform its own detailed logging
    result = await fetch_fda_drug_info(drug_name=drug_name)
    
    if result is None: # API client returns None if drug not found and no other error
        logger.info(f"'tool_get_fda_drug_info' found no information for drug '{drug_name}'.")
        return {"drug_name_queried": drug_name, "error": "No information found or API unavailable."}
    elif result.get("error"): # API client might return a dict with an error key for other issues
        logger.warning(f"'tool_get_fda_drug_info' encountered an error for drug '{drug_name}': {result.get('details') or result.get('error')}")
        # Pass through the error dictionary from the client
    
    logger.debug(f"'tool_get_fda_drug_info' result for drug '{drug_name}': {str(result)[:500]}...") # Log snippet of result
    return result

# --- MCP Tools Registry ---
ToolsRegistry = Dict[str, Callable[..., Coroutine[Any, Any, Dict[str, Any]]]]

MCP_TOOLS_REGISTRY: ToolsRegistry = {
    "search_pubmed": tool_search_pubmed,
    "get_fda_drug_info": tool_get_fda_drug_info,
}

registry = gr.TabbedInterface(
    [
        gr.Interface(tool_search_pubmed, [gr.Textbox(), gr.Textbox()], gr.Textbox(), api_name="tool_search_pubmed"),
        gr.Interface(tool_get_fda_drug_info, gr.Textbox(), gr.Textbox(), api_name="tool_get_fda_drug_info"),
    ],
    [
        "search pubmed",
        "get fda drug info",
    ]
)

if __name__ == '__main__':
    async def main():
        logger.info("--- Running MCP Tools Registry Self-Test (Detailed Docstrings Added) ---")

        registry.launch(mcp_server=True,share=False, debug=True,prevent_thread_lock=True,server_port=7890)
        
        logger.info("--- MCP Tools Registry Self-Test Complete ---")

    asyncio.run(main())