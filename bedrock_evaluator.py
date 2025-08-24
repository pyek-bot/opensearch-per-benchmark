#!/usr/bin/env python3
"""
Bedrock Evaluator for OpenSearch PER Benchmark
Evaluates the similarity between agent responses and expected outputs using Amazon Bedrock
"""

import boto3
import json
import logging
import os
import yaml

def load_config():
    """Load configuration from config.yaml"""
    try:
        with open('config.yaml', 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        return {}

def evaluate_with_bedrock(actual_output, expected_output, model_id=None):
    """
    Evaluate agent output against expected output using Amazon Bedrock
    
    Args:
        actual_output (str): The actual output from the agent
        expected_output (str): The expected output to compare against
        model_id (str, optional): The Bedrock model ID to use for evaluation
        
    Returns:
        dict: Evaluation results with ratings and reasoning
    """
    # Load configuration
    config = load_config()
    
    # Use model ID from parameters, config file, or default
    if model_id is None:
        model_id = config.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0')
    
    # Use region from config or default
    region_name = config.get('AWS_REGION', 'us-east-1')
    
    # Log the model and region being used
    logging.info(f"Using Bedrock model: {model_id} in region: {region_name}")
    
    # Initialize Bedrock client
    try:
        bedrock_client = boto3.client('bedrock-runtime', region_name=region_name)
        logging.info(f"Initialized Bedrock client in {region_name} region")
    except Exception as e:
        logging.error(f"Error initializing Bedrock client: {e}")
        return {
            "error": f"Failed to initialize Bedrock client: {str(e)}",
            "rating": 0,
            "reasoning": "Evaluation failed due to Bedrock client initialization error"
        }
    
    # Prepare the evaluation prompt
    prompt = f"""
You are an expert evaluator comparing an AI agent's response against the expected output.

## Actual AI Agent Response:
{actual_output}

## Expected Output:
{expected_output}

## Your Task:
1. Evaluate how well the actual response matches the expected output in terms of:
   - Accuracy: Does the response contain correct information aligned with the expected output?
   - Completeness: Does it cover all the key points from the expected output?
   - Relevance: How relevant is the response to the expected output?

2. Provide a rating on a scale of 1-5:
   - 1: Poor match - significant discrepancies or missing information
   - 2: Below average match - major gaps or inaccuracies 
   - 3: Average match - contains core information but with some gaps
   - 4: Good match - covers most points accurately
   - 5: Excellent match - fully captures the essence of the expected output

3. Explain your rating with specific examples from both texts.

Format your response as a valid JSON with the following structure:
{{
  "rating": [1-5 as a number],
  "reasoning": [your detailed explanation],
  "accuracy": [brief assessment of accuracy],
  "completeness": [brief assessment of completeness],
  "relevance": [brief assessment of relevance]
}}

The JSON must be valid and properly formatted.
"""

    # Create the request payload
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt}]
            }
        ],
        "inferenceConfig": {
            "maxTokens": 2000,
            "temperature": 0,
            "topP": 0.9
        }
    }

    try:
        # Call Bedrock API
        logging.info(f"Calling Bedrock with model: {model_id}")
        response = bedrock_client.converse(
            modelId=model_id,
            messages=payload["messages"],
            inferenceConfig=payload["inferenceConfig"]
        )
        
        # Extract the response
        if "output" in response and "message" in response["output"]:
            message = response["output"]["message"]
            
            if "content" in message:
                # Extract the text content
                response_text = ""
                for content_block in message["content"]:
                    if "text" in content_block:
                        response_text += content_block["text"]
                
                # Parse the JSON response
                try:
                    # Find JSON in the response
                    import re
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    
                    if json_match:
                        json_str = json_match.group()
                        evaluation = json.loads(json_str)
                        
                        # Ensure the rating is an integer
                        if "rating" in evaluation:
                            evaluation["rating"] = int(evaluation["rating"])
                            
                        # Add the raw response for debugging
                        evaluation["bedrock_raw_response"] = response_text
                        
                        return evaluation
                    else:
                        logging.error("No JSON found in Bedrock response")
                        return {
                            "error": "No JSON found in Bedrock response",
                            "rating": 0,
                            "reasoning": "The Bedrock model did not return a properly formatted JSON response",
                            "bedrock_raw_response": response_text
                        }
                        
                except json.JSONDecodeError as e:
                    logging.error(f"Error parsing Bedrock response as JSON: {e}")
                    return {
                        "error": f"Invalid JSON in Bedrock response: {str(e)}",
                        "rating": 0,
                        "reasoning": "The Bedrock model returned invalid JSON",
                        "bedrock_raw_response": response_text
                    }
            else:
                logging.error("No content in Bedrock message")
                return {
                    "error": "No content in Bedrock message",
                    "rating": 0,
                    "reasoning": "The Bedrock model response was missing content"
                }
        else:
            logging.error("Invalid response structure from Bedrock")
            return {
                "error": "Invalid response structure from Bedrock",
                "rating": 0,
                "reasoning": "The Bedrock API response did not contain expected fields"
            }
            
    except Exception as e:
        logging.error(f"Error calling Bedrock: {e}")
        return {
            "error": f"Error calling Bedrock API: {str(e)}",
            "rating": 0,
            "reasoning": "Evaluation failed due to Bedrock API error"
        }


if __name__ == "__main__":
    # Example usage
    actual = "The cluster contains multiple system indices related to OpenSearch ML functionality. All indices are healthy with green status."
    expected = "The cluster analysis shows multiple system indices related to OpenSearch's machine learning functionality. All indices have green health status and are properly configured."
    
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Call the evaluation function
    result = evaluate_with_bedrock(actual, expected)
    print(json.dumps(result, indent=2))