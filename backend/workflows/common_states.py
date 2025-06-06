# healthmate_app/backend/workflows/common_states.py
from typing import TypedDict, List, Optional, Any, Dict

class BaseWorkflowState(TypedDict, total=False):
    """
    A base state for workflows, including common fields.
    `total=False` means not all keys need to be present.
    """
    user_input: Optional[Any]               # Generic user input
    intermediate_steps: Optional[List[Any]] # For LangGraph to store tool call history
    final_output: Optional[str]             # A common field for the final string output
    error_message: Optional[str]            # For capturing errors within the workflow
    debug_log: Optional[List[str]]          # For appending debug messages during flow


# Example of a more specific shared structure if many workflows deal with similar data types
class HealthDataRetrievalState(BaseWorkflowState, total=False):
    """
    State for workflows that retrieve and synthesize health data.
    """
    query: str
    pubmed_results: Optional[List[Dict[str, Any]]]
    openfda_results: Optional[Dict[str, Any]] # Assuming one main drug result
    healthgov_results: Optional[Dict[str, Any]]
    synthesized_information: Optional[str]