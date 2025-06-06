# healthcare_mcp_app/backend/api_clients/healthgov_client.py
import asyncio
from typing import Dict, Any, Optional

# Health.gov does not have a simple, general-purpose query API like OpenFDA or PubMed.
# Information is often spread across various pages, datasets, or specific tools.
# For this reason, we will simulate responses based on keywords.
# A real-world application might use a curated database, a search index built
# from Health.gov content, or a more sophisticated RAG system.

SIMULATED_HEALTHGOV_DATA = {
    "flu prevention": {
        "topic": "Flu Prevention",
        "summary": "Key strategies to prevent influenza include getting your annual flu vaccine, practicing good hand hygiene (washing hands often with soap and water), covering coughs and sneezes, avoiding close contact with people who are sick, and staying home when you are sick.",
        "details_url": "https://www.cdc.gov/flu/prevent/index.html", # Example link
        "source": "Health.gov / CDC (Simulated)"
    },
    "healthy diet": {
        "topic": "Healthy Eating",
        "summary": "A healthy eating plan emphasizes fruits, vegetables, whole grains, and fat-free or low-fat dairy products. It includes lean meats, poultry, fish, beans, eggs, and nuts, and is low in saturated fats, trans fats, cholesterol, salt (sodium), and added sugars.",
        "details_url": "https://www.myplate.gov/", # Example link
        "source": "Health.gov / MyPlate (Simulated)"
    },
    "diabetes management": {
        "topic": "Diabetes Management",
        "summary": "Managing diabetes involves healthy eating, regular physical activity, monitoring your blood sugar, taking medication as prescribed, and learning how to prevent or treat complications. Work with your health care team to create a diabetes self-management plan.",
        "details_url": "https://www.niddk.nih.gov/health-information/diabetes/overview/managing-diabetes", # Example link
        "source": "Health.gov / NIDDK (Simulated)"
    },
    "common cold": {
        "topic": "Common Cold",
        "summary": "The common cold is a viral infection of your nose and throat (upper respiratory tract). Symptoms usually include a runny nose, sore throat, cough, congestion, and mild body aches or a mild headache. Most people recover in about 7 to 10 days. Get plenty of rest and drink fluids.",
        "details_url": "https://www.cdc.gov/antibiotic-use/colds.html", # Example
        "source": "Health.gov / CDC (Simulated)"
    },
     "public health alerts": {
        "topic": "Public Health Alerts",
        "summary": "Stay informed about current public health alerts and advisories by checking official sources like the CDC and your local health department. These alerts provide crucial information on outbreaks, health risks, and preventive measures.",
        "details_url": "https://www.cdc.gov/outbreaks/",
        "source": "Health.gov / CDC (Simulated)"
    }
}

async def fetch_health_gov_topic(topic_query: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves health topic information (simulated from Health.gov content).
    """
    print(f"API_CLIENT: Getting Health.gov (simulated) info for '{topic_query}'")
    if not topic_query:
        return None
        
    await asyncio.sleep(0.2) # Simulate network latency
    
    query_lower = topic_query.lower()
    
    # Direct match
    if query_lower in SIMULATED_HEALTHGOV_DATA:
        return SIMULATED_HEALTHGOV_DATA[query_lower]
    
    # Partial match (simple keyword search)
    for key, data in SIMULATED_HEALTHGOV_DATA.items():
        if query_lower in key or key in query_lower:
            return data
        # Check if any word from query is in key
        for word in query_lower.split():
            if len(word) > 3 and word in key: # avoid very short words
                return data

    print(f"API_CLIENT: No simulated Health.gov data found for '{topic_query}'.")
    return None

if __name__ == '__main__':
    async def main():
        flu_info = await fetch_health_gov_topic("flu prevention")
        if flu_info:
            print(f"\n--- {flu_info.get('topic')} ---")
            print(f"Summary: {flu_info.get('summary')}")

        diet_info = await fetch_health_gov_topic("healthy diet tips") # Partial match
        if diet_info:
            print(f"\n--- {diet_info.get('topic')} ---")
            print(f"Summary: {diet_info.get('summary')}")

        unknown_info = await fetch_health_gov_topic("rare tropical disease")
        if not unknown_info:
            print("\n--- rare tropical disease ---")
            print("No information found as expected.")
        
        empty_query = await fetch_health_gov_topic("")
        if not empty_query:
            print("\n--- Empty Query ---")
            print("No information for empty query as expected.")

    asyncio.run(main())