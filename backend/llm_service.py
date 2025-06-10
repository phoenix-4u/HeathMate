# healthmate_app/backend/llm_service.py
import os
import asyncio
from openai import AsyncAzureOpenAI, APIError, APITimeoutError
from dotenv import load_dotenv
from typing import List, Dict, Optional

# Import the configured logger
from logger_config import logger

# Load environment variables from .env file
# This is still useful here if this module is run standalone for testing,
# though logger_config also loads it.
load_dotenv()

AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT_URL = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-12-01-preview")
AZURE_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

async_client: Optional[AsyncAzureOpenAI] = None

if not all([AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT_URL, AZURE_CHAT_DEPLOYMENT]):
    logger.error("Azure OpenAI environment variables not fully configured. LLM features will be disabled.")
else:
    try:
        async_client = AsyncAzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            azure_endpoint=AZURE_OPENAI_ENDPOINT_URL,
            api_version=AZURE_OPENAI_VERSION
        )
        logger.info("Async Azure OpenAI client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Async Azure OpenAI client: {e}", exc_info=True)
        # async_client remains None

async def get_llm_completion(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1000,
    temperature: float = 0.3,
    context_data: Optional[str] = None
) -> Optional[str]:
    """
    Gets a completion from the Azure OpenAI chat model using the async client.
    """
    if not async_client:
        logger.warning("Async Azure OpenAI client not available. Cannot get completion.")
        return "LLM Service Not Available: Azure OpenAI client is not configured or failed to initialize."

    messages = [{"role": "system", "content": system_prompt}]
    
    full_user_prompt = user_prompt
    if context_data:
        full_user_prompt = f"Relevant Context Data:\n---\n{context_data}\n---\n\nUser Question/Task:\n{user_prompt}"
        logger.debug(f"Context data provided. Length: {len(context_data)}")
        
    messages.append({"role": "user", "content": full_user_prompt})

    logger.info(f"Sending async request to Azure OpenAI. Deployment: {AZURE_CHAT_DEPLOYMENT}, System Prompt Preview: '{system_prompt[:70]}...', User Prompt Preview: '{user_prompt[:70]}...'")
    logger.debug(f"Full user prompt with context (if any) sent to LLM: {full_user_prompt}")


    try:
        response = await async_client.chat.completions.create(
            model=AZURE_CHAT_DEPLOYMENT,
            messages=messages, # type: ignore
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=30.0 
        )
        
        completion_text = response.choices[0].message.content
        # Log usage if available and needed (can be verbose for DEBUG)
        if response.usage:
            logger.debug(f"Azure OpenAI API usage: Prompt Tokens={response.usage.prompt_tokens}, Completion Tokens={response.usage.completion_tokens}, Total Tokens={response.usage.total_tokens}")
        
        logger.info(f"Received async completion from Azure OpenAI. Completion Length: {len(completion_text or '')}")
        logger.debug(f"Raw completion text: {completion_text}")
        return completion_text.strip() if completion_text else None
    
    except APITimeoutError:
        logger.error("Azure OpenAI API request timed out (async).")
        return "LLM Service Error: The request to the AI model timed out. Please try again."
    except APIError as e:
        logger.error(f"Azure OpenAI API error (async): Status {e.status_code} - Type: {e.type} - Message: {e.message} - Code: {e.code} - Param: {e.param}", exc_info=True)
        error_message = f"LLM Service Error: The AI model returned an error (Status {e.status_code})."
        if hasattr(e, 'message') and e.message:
             error_message += f" Details: {e.message[:100]}..."
        elif hasattr(e, 'body') and e.body and 'message' in e.body:
            error_message += f" Details: {e.body['message'][:100]}..."
        return error_message
    except Exception as e:
        logger.error(f"An unexpected error occurred while calling Azure OpenAI (async): {e}", exc_info=True)
        return "LLM Service Error: An unexpected error occurred while communicating with the AI model."

if __name__ == '__main__':
    # This basic test will now also generate logs to console (INFO+) and file (DEBUG+ if LOG_LEVEL=DEBUG)
    async def test_llm():
        logger.info("--- Running LLM Service Self-Test ---")
        if not async_client:
            logger.warning("Skipping LLM self-test as async_client is not initialized.")
            return

        system_p = "You are a helpful assistant that summarizes medical information factually."
        user_p = "What are the common treatments for Type 2 Diabetes?"
        context = """
        PubMed Article 1:
        Title: Advances in Type 2 Diabetes Management
        Summary: Recent breakthroughs in pharmacological and lifestyle interventions for type 2 diabetes include SGLT2 inhibitors and GLP-1 agonists, alongside emphasis on personalized nutrition and exercise.

        FDA Drug Info (Metformin):
        Indications: Used to treat type 2 diabetes.
        Warnings: Risk of lactic acidosis.
        """
        
        logger.info(f"Test 1: Summarization with context. User prompt: '{user_p}'")
        response = await get_llm_completion(system_p, user_p, context_data=context, max_tokens=150)
        logger.info(f"LLM Response (Test 1):\n{response}")

        logger.info("Test 2: Simple question without context")
        response_no_context = await get_llm_completion(
            system_prompt="You are a friendly health chatbot. Do not give medical advice.",
            user_prompt="What are some general tips for staying healthy?",
            max_tokens=100
        )
        logger.info(f"LLM Response (Test 2 - no context):\n{response_no_context}")
        
        logger.info("--- LLM Service Self-Test Complete ---")

    asyncio.run(test_llm())