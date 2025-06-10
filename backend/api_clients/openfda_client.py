# healthmate_app/backend/api_clients/openfda_client.py
import httpx
import asyncio
from typing import Dict, Any, Optional, List
import json # For JSONDecodeError

# Import the configured logger
from logger_config import logger

OPENFDA_API_URL = "https://api.fda.gov/"

async def fetch_fda_drug_info_real(drug_name: str) -> Optional[Dict[str, Any]]:
    """
    Fetches drug information from OpenFDA using real API calls.
    Focuses on drug label information.
    """
    logger.info(f"Attempting to fetch OpenFDA drug info for: '{drug_name}'")
    if not drug_name or not drug_name.strip():
        logger.warning("Empty drug_name provided to fetch_fda_drug_info. Returning None.")
        return None

    search_query = f'(openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}")'
    params = {
        "search": search_query,
        "limit": 1
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            logger.debug(f"OpenFDA request: URL={OPENFDA_API_URL}drug/label.json, Params={params}")
            response = await client.get(f"{OPENFDA_API_URL}drug/label.json", params=params)
            logger.debug(f"OpenFDA response status: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"OpenFDA response data (first 500 chars): {str(data)[:500]}")
            
            if data.get("results") and len(data["results"]) > 0:
                label_info = data["results"][0]
                
                def get_array_field(data_dict, field_name, default_val=["N/A"]) -> List[str]:
                    # ... (helper function remains the same)
                    field_data = data_dict.get(field_name)
                    if isinstance(field_data, list) and all(isinstance(item, str) for item in field_data) and field_data:
                        return field_data
                    elif isinstance(field_data, str) and field_data:
                        return [field_data]
                    return default_val

                openfda_section = label_info.get("openfda", {})
                brand_names = openfda_section.get("brand_name", [])
                generic_names = openfda_section.get("generic_name", [])
                
                indications = get_array_field(label_info, "indications_and_usage")
                warnings_precautions = get_array_field(label_info, "warnings_and_precautions")
                adverse_reactions = get_array_field(label_info, "adverse_reactions")
                dosage_admin = get_array_field(label_info, "dosage_and_administration")

                extracted_info = {
                    "drug_name_queried": drug_name,
                    "id": label_info.get("id", "N/A"),
                    "set_id": label_info.get("set_id", "N/A"),
                    "effective_time": label_info.get("effective_time", "N/A"),
                    "brand_name": brand_names if isinstance(brand_names, list) else [str(brand_names)],
                    "generic_name": generic_names if isinstance(generic_names, list) else [str(generic_names)],
                    "manufacturer_name": openfda_section.get("manufacturer_name", ["N/A"]),
                    "indications_and_usage": indications,
                    "warnings_and_precautions": warnings_precautions,
                    "adverse_reactions": adverse_reactions,
                    "dosage_and_administration": dosage_admin,
                    "source_api": "OpenFDA Drug Label API (Live)"
                }
                logger.info(f"Successfully fetched OpenFDA info for '{drug_name}'. ID: {extracted_info.get('id')}")
                logger.debug(f"Extracted OpenFDA info for '{drug_name}': {extracted_info}")
                return extracted_info
            else:
                logger.info(f"No results found on OpenFDA for '{drug_name}'. Search query: '{search_query}'. Response metadata: {data.get('meta')}")
                return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching OpenFDA data for '{drug_name}': {e.response.status_code} - {e.response.text}", exc_info=True)
            return {"error": str(e), "details": f"Failed to fetch from OpenFDA (HTTP {e.response.status_code}). Query: {search_query}"}
        except httpx.RequestError as e:
            logger.error(f"Request error for OpenFDA for '{drug_name}': {e}", exc_info=True)
            return {"error": str(e), "details": f"Network or request error connecting to OpenFDA. Query: {search_query}"}
        except json.JSONDecodeError as e: # Corrected import for json
            logger.error(f"JSON decoding error for OpenFDA response for '{drug_name}': {e.msg}", exc_info=True) # Use e.msg for JSONDecodeError
            return {"error": str(e), "details": f"Failed to parse JSON from OpenFDA. Query: {search_query}"}
        except Exception as e:
            logger.error(f"General error fetching OpenFDA data for '{drug_name}': {e}", exc_info=True)
            return {"error": str(e), "details": f"An unexpected error occurred with OpenFDA API. Query: {search_query}"}

# async def fetch_fda_drug_info_simulated(drug_name: str) -> Optional[Dict[str, Any]]:
#     logger.info(f"SIMULATED: Fetching OpenFDA drug info for: '{drug_name}'")
#     # ... (rest of simulated logic)
#     if not drug_name: return None
#     await asyncio.sleep(0.1)
#     drug_name_lower = drug_name.lower()
#     # ... (simulated cases)
#     if drug_name_lower == "metformin":
#         return {
#             "drug_name_queried": drug_name,
#             # ...
#             "source_api": "OpenFDA (Simulated)"
#         }
#     return None


fetch_fda_drug_info = fetch_fda_drug_info_real

if __name__ == '__main__':
    async def main():
        logger.info("--- Running OpenFDA Client Self-Test ---")
        test_drugs = ["Metformin", "Ibuprofen", "Lisinopril", "NonExistentDrugXYZ123"]

        for drug in test_drugs:
            logger.info(f"Fetching info for: {drug}")
            info = await fetch_fda_drug_info(drug)
            if info and not info.get("error"):
                logger.info(f"  Drug: {info.get('drug_name_queried')}, Brand: {info.get('brand_name')}, Source: {info.get('source_api')}")
                logger.debug(f"  Full info for {drug}: {info}")
            elif info and info.get("error"):
                logger.warning(f"  Error fetching {drug}: {info.get('error')} - {info.get('details')}")
            else:
                logger.info(f"  No information found or API returned no results for {drug}.")
        
        logger.info("Fetching info for empty drug name:")
        empty_info = await fetch_fda_drug_info("")
        if empty_info is None:
            logger.info("  Correctly returned None for empty drug name.")
        else:
            logger.warning(f"  Unexpected result for empty drug name: {empty_info}")
        logger.info("--- OpenFDA Client Self-Test Complete ---")

    asyncio.run(main())