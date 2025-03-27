import os
import requests
import json
import re
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv


class MistralLLMService:
    """
    A client for interacting with the Mistral AI API.
    """
    def __init__(self, model: str = "mistral-large-latest"):
        load_dotenv()
        self.model = model
        self.api_key = os.getenv("MISTRAL_API_KEY")
        self.api_endpoint = os.getenv("MISTRAL_API_ENDPOINT", "https://api.mistral.ai/v1/chat/completions")
        
        # Add logging
        self.logger = logging.getLogger(__name__)
        
        # Print API setup (without the actual key)
        print(f"Mistral API Endpoint: {self.api_endpoint}")
        print(f"Mistral API Key: {'Configured' if self.api_key else 'Not Configured'}")
        
        if not self.api_key:
            self.logger.warning("Mistral API key not set. Set the MISTRAL_API_KEY environment variable.")
        
        # Request timeout in seconds
        self.timeout = 30

    def generate(self, prompt: str, max_tokens: int = 3000, temperature: float = 0.3) -> Optional[str]:
        """
        Generate text using the Mistral AI API.
        
        Args:
            prompt: The text prompt to send to the API.
            
        Returns:
            The generated text response.
        """
        if not self.api_key:
            mock_response = '{"error": "API key not configured", "status": "error"}'
            self.logger.warning("Using mock response due to missing API key")
            return mock_response
            
        # Check if prompt is empty
        if not prompt or not isinstance(prompt, str):
            self.logger.error(f"Invalid prompt: {type(prompt)}")
            return '{"error": "Invalid prompt", "status": "error"}'
            
        # Keep track of retries
        max_retries = 2
        retries = 0
        
        while retries <= max_retries:
            try:
                self.logger.info(f"Sending request to Mistral API (attempt {retries + 1}/{max_retries + 1})")
                
                # Prepare the payload
                payload = {
                    "model": self.model,
                    "messages": [{
                        "role": "user",
                        "content": prompt
                    }],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "text"}
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                # Make the API call with timeout
                response = requests.post(
                    self.api_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                # Check response status
                if response.status_code != 200:
                    self.logger.error(f"API request failed with status code {response.status_code}: {response.text}")
                    
                    # If we've hit the retry limit, return error
                    if retries >= max_retries:
                        return f'{{"error": "Request failed with status code {response.status_code}", "status": "error"}}'
                    
                    # Otherwise retry
                    retries += 1
                    continue
                
                # Parse response
                try:
                    response_data = response.json()
                    self.logger.debug(f"API response structure: {json.dumps(response_data, indent=2)}")
                    
                    # Extract content from response
                    content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    # Clean content (remove whitespace, tabs, etc.)
                    content = content.strip()
                    
                    if not content:
                        self.logger.warning("Empty content returned from API, using mock response")
                        content = '{"error": "Empty response", "status": "error"}'
                    
                    return content
                    
                except (json.JSONDecodeError, KeyError, IndexError) as e:
                    self.logger.error(f"Error parsing API response: {str(e)}")
                    self.logger.debug(f"Raw response: {response.text}")
                    
                    # If we've hit the retry limit, return error
                    if retries >= max_retries:
                        return f'{{"error": "Error parsing response: {str(e)}", "status": "error"}}'
                    
                    # Otherwise retry
                    retries += 1
            
            except requests.exceptions.Timeout:
                self.logger.error(f"API request timed out after {self.timeout} seconds")
                
                # If we've hit the retry limit, return error
                if retries >= max_retries:
                    return f'{{"error": "Request timed out after {self.timeout} seconds", "status": "error"}}'
                
                # Otherwise retry
                retries += 1
            
            except requests.exceptions.RequestException as e:
                self.logger.error(f"API request error: {str(e)}")
                
                # If we've hit the retry limit, return error
                if retries >= max_retries:
                    return f'{{"error": "Request error: {str(e)}", "status": "error"}}'
                
                # Otherwise retry
                retries += 1
            
            except Exception as e:
                self.logger.error(f"Unexpected error: {str(e)}")
                return f'{{"error": "Unexpected error: {str(e)}", "status": "error"}}'
            
    def _generate_mock_response(self, prompt: str) -> str:
        """Generate mock responses for testing when API is unavailable"""
        print("USING MOCK RESPONSE - NO ACTUAL API CALL MADE")
        
        if "Carrefour" in prompt and "Coca-Cola" in prompt:
            return json.dumps({
                "vendor": "Carrefour",
                "date": "2023-10-25",
                "total": 17.40,
                "line_items": [
                    {"description": "Coca-Cola", "quantity": 2, "price": 1.50},
                    {"description": "Coca-Coco", "quantity": 2, "price": 12.20}
                ]
            })
        
        # Default mock for testing connection
        if "status" in prompt and "ok" in prompt:
            return '{"status": "ok"}'
        
        # Default fallback response
        return json.dumps({
            "vendor": "Unknown Store",
            "date": "2023-01-01",
            "total": 0.0,
            "line_items": []
        }) 