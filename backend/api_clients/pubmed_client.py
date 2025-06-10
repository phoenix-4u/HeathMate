# healthmate_app/backend/api_clients/pubmed_client.py
import httpx
import asyncio
from typing import List, Dict, Any
import xml.etree.ElementTree as ET

# Import the configured logger
from logger_config import logger

PUBMED_API_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TOOL_EMAIL = "phoenix.cocextreme@gmail.com" 

async def fetch_pubmed_articles_real(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """
    Searches PubMed for articles related to the query and fetches their summaries using real API calls.
    """
    logger.info(f"Attempting to fetch PubMed articles for query: '{query}', max_results: {max_results}")
    if not query:
        logger.warning("Empty query provided to fetch_pubmed_articles. Returning empty list.")
        return []

    article_ids = []
    articles_data = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # 1. Use esearch to get article IDs
            esearch_params = {
                "db": "pubmed",
                "term": query,
                "retmax": str(max_results),
                "sort": "relevance",
                "tool": "healthmate_app",
                "email": TOOL_EMAIL
            }
            logger.debug(f"PubMed esearch request params: {esearch_params}")
            response_search = await client.get(f"{PUBMED_API_URL}esearch.fcgi", params=esearch_params)
            response_search.raise_for_status()

            # Parse XML response from esearch
            logger.debug(f"PubMed esearch response content (first 500 chars): {response_search.content[:500]}")
            root_search = ET.fromstring(response_search.content)
            id_list_element = root_search.find("IdList")
            if id_list_element is not None:
                for id_element in id_list_element.findall("Id"):
                    if id_element.text:
                        article_ids.append(id_element.text)
            
            if not article_ids:
                logger.info(f"No PubMed article IDs found by esearch for query: '{query}'.")
                return []
            
            logger.info(f"PubMed esearch found IDs: {article_ids} for query: '{query}'.")

            # 2. Use efetch to get summaries for these IDs
            ids_str = ",".join(article_ids)
            efetch_params = {
                "db": "pubmed",
                "id": ids_str,
                "retmode": "xml",
                "rettype": "abstract",
                "tool": "healthmate_app",
                "email": TOOL_EMAIL
            }
            logger.debug(f"PubMed efetch request params: {efetch_params}")
            response_fetch = await client.get(f"{PUBMED_API_URL}efetch.fcgi", params=efetch_params)
            response_fetch.raise_for_status()
            
            logger.debug(f"PubMed efetch response content (first 500 chars): {response_fetch.content[:500]}")
            root_fetch = ET.fromstring(response_fetch.content)
            for pubmed_article_element in root_fetch.findall(".//PubmedArticle"):
                article = {}
                medline_citation = pubmed_article_element.find("MedlineCitation")
                if medline_citation is not None:
                    article["id"] = medline_citation.findtext("PMID")
                    article_element = medline_citation.find("Article")
                    if article_element is not None:
                        article["title"] = article_element.findtext("ArticleTitle", "N/A")
                        
                        abstract_element = article_element.find("Abstract/AbstractText")
                        if abstract_element is not None and abstract_element.text:
                            article["summary"] = abstract_element.text
                        else:
                            abstract_texts = []
                            for ab_text_el in article_element.findall("Abstract/AbstractText"):
                                if ab_text_el.text:
                                    label = ab_text_el.get("Label")
                                    text_content = ab_text_el.text.strip()
                                    # Ensure text_content is not just whitespace
                                    if text_content:
                                        if label:
                                            abstract_texts.append(f"{label}: {text_content}")
                                        else:
                                            abstract_texts.append(text_content)
                            if abstract_texts:
                                article["summary"] = " ".join(abstract_texts)
                            else:
                                article["summary"] = "No abstract available or abstract is structured."
                
                if article.get("id") and article.get("title"):
                    articles_data.append(article)
                    logger.debug(f"Parsed PubMed article: ID={article.get('id')}, Title='{article.get('title', '')[:50]}...'")
            
            logger.info(f"Successfully fetched and parsed {len(articles_data)} PubMed articles for query: '{query}'.")
            return articles_data

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching PubMed data for query '{query}': {e.response.status_code} - {e.response.text}", exc_info=True)
            return [{"error": str(e), "details": f"Failed to fetch from PubMed (HTTP {e.response.status_code})."}]
        except ET.ParseError as e:
            logger.error(f"XML parsing error for PubMed query '{query}': {e}", exc_info=True)
            return [{"error": str(e), "details": "Failed to parse PubMed XML response."}]
        except httpx.RequestError as e:
            logger.error(f"Request error for PubMed query '{query}': {e}", exc_info=True)
            return [{"error": str(e), "details": "Network or request error connecting to PubMed."}]
        except Exception as e:
            logger.error(f"General error fetching PubMed data for query '{query}': {e}", exc_info=True)
            return [{"error": str(e), "details": "An unexpected error occurred with PubMed API."}]

# Renaming the simulated function for clarity, or it could be removed
async def fetch_pubmed_articles_simulated(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    logger.info(f"SIMULATED: Fetching PubMed articles for query: '{query}', max_results: {max_results}")
    # ... (rest of simulated logic)
    await asyncio.sleep(0.1)
    if not query: return []
    results = []
    if "covid" in query.lower():
        results.extend([
            {"id": "sim_pmid32000001", "title": "SIM: Understanding COVID-19 Pathogenesis", "summary": "SIM: A comprehensive review of how SARS-CoV-2 affects the human body..."},
            {"id": "sim_pmid32000002", "title": "SIM: Vaccine Development for SARS-CoV-2", "summary": "SIM: Overview of different vaccine platforms..."},
        ])
    # ... (other simulated cases)
    if not results and query:
        results.append(
            {"id": "sim_pmid00000001", "title": f"SIM: General Medical Research on '{query.split()[0]}'", "summary": f"SIM: Exploratory research findings related to {query.split()[0]}."}
        )
    return results[:max_results]


fetch_pubmed_articles = fetch_pubmed_articles_real


if __name__ == '__main__':
    async def main():
        logger.info("--- Running PubMed Client Self-Test ---")
        
        test_query_1 = "covid vaccine efficacy"
        logger.info(f"Test 1: Query '{test_query_1}'")
        articles1 = await fetch_pubmed_articles(test_query_1, 2)
        if articles1 and not any("error" in art for art in articles1):
            for art_idx, art in enumerate(articles1):
                logger.info(f"  Article {art_idx+1}: ID={art.get('id')}, Title='{art.get('title')}', Summary='{art.get('summary', 'N/A')[:70]}...'")
        else:
            logger.warning(f"  Test 1 Result for '{test_query_1}': {articles1}")

        test_query_2 = "nonexistentmedicaltermxyz123"
        logger.info(f"Test 2: Query '{test_query_2}' (expecting no results or empty list)")
        articles2 = await fetch_pubmed_articles(test_query_2, 1)
        if not articles2: # handles empty list from "No article IDs found"
            logger.info(f"  Test 2 for '{test_query_2}' yielded no results, as expected.")
        elif articles2 and not any("error" in art for art in articles2) and not articles2[0].get("id"): # handles empty dicts if any
            logger.info(f"  Test 2 for '{test_query_2}' yielded empty article data, as expected.")
        elif articles2 and any("error" in art for art in articles2):
            logger.warning(f"  Test 2 for '{test_query_2}' resulted in error: {articles2}")
        else:
            logger.warning(f"  Test 2 for '{test_query_2}' yielded unexpected results: {articles2}")
        
        logger.info("--- PubMed Client Self-Test Complete ---")

    asyncio.run(main())