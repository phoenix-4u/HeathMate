# healthcare_mcp_app/backend/api_clients/openfda_client.py
import httpx
import asyncio
from typing import Dict, Any, Optional

OPENFDA_API_URL = "https://api.fda.gov/"

async def fetch_fda_drug_info(drug_name: str) -> Optional[Dict[str, Any]]:
    """
    Fetches drug information from OpenFDA.
    This example focuses on drug label information.
    """
    print(f"API_CLIENT: Getting FDA info for '{drug_name}'")
    if not drug_name:
        return None

    # Search for drug label information containing the brand or generic name
    # Note: OpenFDA search can be tricky; exact matches are preferred.
    # Using `openfda.brand_name` or `openfda.generic_name` is more precise.
    # We'll try searching in a few common fields.
    search_query = (
        f'(openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}")'
        f' OR (description:"{drug_name}" OR purpose:"{drug_name}")' # Broader search in text
    )
    params = {
        "search": search_query,
        "limit": 1 # Get the most relevant result
    }

    # Simulate for now, as live API can be complex to get right demo data consistently
    await asyncio.sleep(0.3)
    drug_name_lower = drug_name.lower()

    if drug_name_lower == "metformin":
        return {
            "drug_name_queried": drug_name,
            "brand_name": ["Glucophage (example)"],
            "generic_name": ["Metformin Hydrochloride"],
            "indications_and_usage": ["Metformin is a biguanide antihyperglycemic agent used for treating non-insulin-dependent diabetes mellitus (NIDDM). It improves glycemic control by decreasing hepatic glucose production, decreasing intestinal absorption of glucose and improving insulin sensitivity by increasing peripheral glucose uptake and utilization."],
            "adverse_reactions": ["Common adverse reactions include diarrhea, nausea/vomiting, flatulence, asthenia, indigestion, abdominal discomfort, headache. Lactic acidosis is a rare but serious metabolic complication that can occur due to metformin accumulation."],
            "warnings_and_precautions": ["Lactic acidosis: Postmarketing cases of metformin-associated lactic acidosis have resulted in death, hypothermia, hypotension, and resistant bradyarrhythmias. Risk factors include renal impairment, concomitant use of certain drugs (e.g., carbonic anhydrase inhibitors such as topiramate), age 65 years old or greater, having a radiological study with contrast, surgery and other procedures, hypoxic states (e.g., acute congestive heart failure), excessive alcohol intake, and hepatic impairment."],
            "source": "OpenFDA (Simulated based on typical Metformin label)"
        }
    elif drug_name_lower == "ibuprofen":
         return {
            "drug_name_queried": drug_name,
            "brand_name": ["Advil (example)", "Motrin (example)"],
            "generic_name": ["Ibuprofen"],
            "indications_and_usage": ["Ibuprofen is a nonsteroidal anti-inflammatory drug (NSAID) that is used to relieve pain from various conditions such as headache, dental pain, menstrual cramps, muscle aches, or arthritis. It is also used to reduce fever and to relieve minor aches and pain due to the common cold or flu."],
            "adverse_reactions": ["Common side effects may include upset stomach, mild heartburn, nausea, vomiting; bloating, gas, diarrhea, constipation; dizziness, headache, nervousness; mild itching or rash; ringing in your ears."],
            "warnings_and_precautions": ["Cardiovascular Thrombotic Events: NSAIDs cause an increased risk of serious cardiovascular thrombotic events, including myocardial infarction and stroke, which can be fatal. Gastrointestinal Bleeding, Ulceration, and Perforation: NSAIDs cause an increased risk of serious gastrointestinal (GI) adverse events including bleeding, ulceration, and perforation of the stomach or intestines, which can be fatal."],
            "source": "OpenFDA (Simulated based on typical Ibuprofen label)"
        }
    
    # Fallback for unmocked drugs
    # async with httpx.AsyncClient() as client:
    #     try:
    #         print(f"API_CLIENT: Querying OpenFDA with: {search_query}")
    #         response = await client.get(f"{OPENFDA_API_URL}drug/label.json", params=params)
    #         response.raise_for_status() # Raise an exception for HTTP errors
    #         data = response.json()
            
    #         if data.get("results") and len(data["results"]) > 0:
    #             # Extract relevant fields from the first result
    #             # The structure of OpenFDA label data can be complex and nested
    #             # This is a simplified extraction
    #             label_info = data["results"][0]
    #             return {
    #                 "drug_name_queried": drug_name,
    #                 "brand_name": label_info.get("openfda", {}).get("brand_name", ["N/A"]),
    #                 "generic_name": label_info.get("openfda", {}).get("generic_name", ["N/A"]),
    #                 "indications_and_usage": label_info.get("indications_and_usage", ["N/A"])[0] if label_info.get("indications_and_usage") else "N/A",
    #                 "adverse_reactions": label_info.get("adverse_reactions", ["N/A"])[0] if label_info.get("adverse_reactions") else "N/A",
    #                 "warnings_and_precautions": label_info.get("warnings_and_precautions", ["N/A"])[0] if label_info.get("warnings_and_precautions") else "N/A",
    #                 "source": "OpenFDA (Live API)"
    #             }
    #         else:
    #             print(f"API_CLIENT: No results found on OpenFDA for '{drug_name}'.")
    #             return None # Or an error dictionary
    #     except httpx.HTTPStatusError as e:
    #         print(f"API_CLIENT_ERROR: HTTP error fetching OpenFDA data for '{drug_name}': {e}")
    #         return {"error": str(e), "details": f"Failed to fetch from OpenFDA for {drug_name}"}
    #     except Exception as e:
    #         print(f"API_CLIENT_ERROR: General error fetching OpenFDA data for '{drug_name}': {e}")
    #         return {"error": str(e), "details": f"An unexpected error occurred with OpenFDA for {drug_name}"}
            
    print(f"API_CLIENT: No simulated data found for '{drug_name}' on OpenFDA.")
    return None

if __name__ == '__main__':
    async def main():
        metformin_info = await fetch_fda_drug_info("Metformin")
        if metformin_info:
            print(f"\n--- {metformin_info.get('drug_name_queried')} ---")
            print(f"Indications: {str(metformin_info.get('indications_and_usage'))[:100]}...")
            print(f"Warnings: {str(metformin_info.get('warnings_and_precautions'))[:100]}...")

        ibuprofen_info = await fetch_fda_drug_info("Ibuprofen")
        if ibuprofen_info:
            print(f"\n--- {ibuprofen_info.get('drug_name_queried')} ---")
            print(f"Indications: {str(ibuprofen_info.get('indications_and_usage'))[:100]}...")

        unknown_drug_info = await fetch_fda_drug_info("UnknownDrugXYZ")
        if unknown_drug_info:
            print(unknown_drug_info)
        else:
            print("\n--- UnknownDrugXYZ ---")
            print("No information found as expected.")
        
        empty_query = await fetch_fda_drug_info("")
        if not empty_query:
            print("\n--- Empty Query ---")
            print("No information for empty query as expected.")

    asyncio.run(main())