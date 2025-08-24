import yaml
import json
import time
import logging
import os
from opensearchpy import OpenSearch
from opensearch_py_ml.ml_commons import MLCommonClient
from bedrock_evaluator import evaluate_with_bedrock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class OpenSearchClient:
    def __init__(self, config):
        self.host = config['OPENSEARCH_HOST']
        self.port = config['OPENSEARCH_PORT']
        self.agent_id = config['AGENT_ID']
        self.base_uri = "/_plugins/_ml"
        
        # Determine if SSL should be used based on the protocol
        protocol = config.get('OPENSEARCH_PROTOCOL', 'https').lower()
        use_ssl = protocol == 'https'
        
        # Prepare connection arguments
        conn_args = {
            'hosts': [{'host': self.host, 'port': self.port}],
            'use_ssl': use_ssl,
            'verify_certs': False
        }
        
        # Add HTTP authentication if credentials are provided
        if 'OPENSEARCH_USER' in config and 'OPENSEARCH_PASSWORD' in config:
            conn_args['http_auth'] = (config['OPENSEARCH_USER'], config['OPENSEARCH_PASSWORD'])
        
        self.client = OpenSearch(**conn_args)
        
        self.ml_client = MLCommonClient(self.client)
    
    def execute_agent_transport(self, agent_id, question):
        """
        Execute an agent using the transport layer with async=true parameter
        
        Args:
            agent_id (str): The ID of the agent to execute
            question (str): The question to ask the agent
            
        Returns:
            dict: Response containing task_id, status, and response data
                  including memory_id and parent_interaction_id
        """
        # Prepare the endpoint with async parameter
        endpoint = f"{self.base_uri}/agents/{agent_id}/_execute?async=true"
            
        # Prepare the request body according to the example format
        body = {
            "parameters": {
                "question": question
            }
        }
        
        logging.info(f"Executing agent {agent_id} with question: {question}")
        
        try:
            response = self.client.transport.perform_request(
                "POST", endpoint, body=body
            )
            logging.info(f"Agent execution initiated successfully with task_id: {response.get('task_id')}")
            
            # Log the full response structure at debug level
            logging.debug(f"Full agent execution response: {json.dumps(response, indent=2)}")
            
            # Expected response format:
            # {
            #     "task_id": "nDYS3pgBCSP1TPM56JL9",
            #     "status": "RUNNING",
            #     "response": {
            #         "memory_id": "mjYS3pgBCSP1TPM56JJq",
            #         "parent_interaction_id": "mzYS3pgBCSP1TPM56JKx"
            #     }
            # }
                
            return response
        except Exception as e:
            logging.error(f"Error executing agent: {e}")
            raise

def run_agent_async(question, client, agent_id=None):
    """Run agent asynchronously and return task_id
    
    Args:
        question (str): The question to ask the agent
        client (OpenSearchClient): The OpenSearch client
        agent_id (str, optional): The agent ID to use. Defaults to the client's agent_id.
        
    Returns:
        str: The task_id for the asynchronous execution
    """
    # Use the agent_id from parameters or fallback to client's default
    agent_id = agent_id or client.agent_id
    
    # Execute the agent using the transport layer with async=true
    response = client.execute_agent_transport(agent_id, question)
    
    # Extract and return the task_id
    task_id = response.get('task_id')
    
    if not task_id:
        raise ValueError(f"Failed to get task_id from response: {response}")
    
    logging.info(f"Agent execution started with task_id: {task_id}")
    return task_id

def fetch_result(task_id, client, poll_interval=5, max_retries=60):
    """Fetch result using task_id with enhanced polling mechanism
    
    Args:
        task_id (str): The task ID to poll for results
        client (OpenSearchClient): The OpenSearch client
        poll_interval (int, optional): Seconds between polling attempts. Defaults to 5.
        max_retries (int, optional): Maximum number of polling attempts. Defaults to 60.
        
    Returns:
        dict: The task response data
        
    Raises:
        Exception: If the task fails or times out
    """
    logging.info(f"Polling for task {task_id} completion")
    
    for attempt in range(max_retries):
        try:
            # Get task status using transport layer for more direct access
            endpoint = f"{client.base_uri}/tasks/{task_id}"
            task_data = client.client.transport.perform_request("GET", endpoint)
            
            # Log the full task data at debug level
            logging.debug(f"Task data (attempt {attempt+1}): {json.dumps(task_data, indent=2)}")
            
            # Get the state from the response based on example format
            state = task_data.get('state')
            logging.info(f"Task {task_id} state: {state} (attempt {attempt+1}/{max_retries})")
            
            if state == 'COMPLETED':
                logging.info(f"Task {task_id} completed successfully")
                return task_data
            elif state == 'FAILED':
                # Extract error message from the response format
                error_msg = "Unknown error"
                if 'response' in task_data and 'error_message' in task_data['response']:
                    error_msg = task_data['response']['error_message']
                logging.error(f"Task {task_id} failed: {error_msg}")
                
                # Still return the task data so caller can extract error details
                return task_data
            elif state == 'RUNNING' or state == 'CREATED':
                # Task still running, wait and try again
                logging.info(f"Task {task_id} is {state}. Waiting {poll_interval} seconds before checking again.")
                time.sleep(poll_interval)
            else:
                # Unknown status
                logging.warning(f"Unknown task state: {state}")
                time.sleep(poll_interval)
        except Exception as e:
            # Log exceptions but continue polling
            logging.error(f"Error polling task {task_id}: {e}")
            time.sleep(poll_interval)
    
    # If we reached here, we've exhausted retries
    raise TimeoutError(f"Task {task_id} did not complete within {max_retries * poll_interval} seconds")

def process_output(task_data):
    """Process the raw output from the task
    
    Args:
        task_data (dict): The complete task data from fetch_result
        
    Returns:
        dict: Processed output with key components extracted
    """
    logging.info("Processing task output data")
    
    if not task_data:
        logging.warning("Empty task data received")
        return {"error": "No task data available"}
    
    # Extract the task state
    state = task_data.get('state')
    
    # Extract the core response
    response = task_data.get('response', {})
    
    # Initialize the processed output
    processed_output = {
        "task_id": task_data.get('task_id', ''),
        "state": state,
        "task_type": task_data.get('task_type', ''),
        "function_name": task_data.get('function_name', ''),
        "create_time": task_data.get('create_time', 0),
        "last_update_time": task_data.get('last_update_time', 0),
        "memory_id": response.get('memory_id', ''),
        "parent_interaction_id": response.get('parent_interaction_id', ''),
        "executor_agent_memory_id": response.get('executor_agent_memory_id', ''),
        "executor_agent_parent_interaction_id": response.get('executor_agent_parent_interaction_id', ''),
    }
    
    # Handle the case when the task is COMPLETED
    if state == 'COMPLETED' and 'inference_results' in response:
        try:
            # Find the response output from inference_results
            inference_results = response.get('inference_results', [{}])[0]
            output_items = inference_results.get('output', [])
            
            # Process each output item
            for item in output_items:
                if item.get('name') == 'response' and 'dataAsMap' in item:
                    response_content = item['dataAsMap'].get('response', '')
                    processed_output['content'] = response_content
                    break
            
            # If no content was found in the expected format, look for alternatives
            if 'content' not in processed_output:
                processed_output['content'] = ''
                logging.warning("Could not find response content in the expected format")
        except Exception as e:
            logging.error(f"Error extracting response content: {e}")
            processed_output['content'] = ''
            processed_output['extraction_error'] = str(e)
    
    # Handle the case when the task is FAILED
    elif state == 'FAILED':
        processed_output['error_message'] = response.get('error_message', 'Unknown error')
        processed_output['content'] = ''
    
    # Handle other states (CREATED, RUNNING)
    else:
        processed_output['content'] = ''
    
    logging.info(f"Processed output: {json.dumps(processed_output, indent=2)}")
    return processed_output

def evaluate_result(actual_output, expected_output):
    """Evaluate actual output against expected output using Amazon Bedrock
    
    Args:
        actual_output (dict): The processed output from the agent
        expected_output (str): The expected output to compare against
        
    Returns:
        dict: Evaluation results with Bedrock ratings
    """
    logging.info("Evaluating agent output using Amazon Bedrock")
    
    # Get the state and check for errors first
    state = actual_output.get('state', '')
    
    # Initialize evaluation result
    evaluation = {
        "expected_output": expected_output,
        "state": state
    }
    
    # Handle failed tasks
    if state == 'FAILED':
        evaluation["error_message"] = actual_output.get('error_message', 'Unknown error')
        evaluation["success"] = False
        evaluation["actual_content"] = ""
        logging.warning(f"Task failed: {evaluation['error_message']}")
        return evaluation
        
    # Extract the actual content for completed tasks
    actual_content = actual_output.get('content', '')
    evaluation["actual_content"] = actual_content
    
    # Determine if the task was successful
    evaluation["success"] = state == 'COMPLETED'
    
    # Use Bedrock for evaluation
    if evaluation["success"]:
        try:
            logging.info("Sending to Bedrock for evaluation")
            bedrock_evaluation = evaluate_with_bedrock(
                actual_content,
                expected_output
            )
            
            # Merge Bedrock evaluation results
            evaluation.update(bedrock_evaluation)
            
            # Log the rating if available
            if "rating" in evaluation:
                logging.info(f"Bedrock evaluation rating: {evaluation['rating']}/5")
            else:
                logging.warning("Bedrock evaluation did not return a rating")
                
        except Exception as e:
            logging.error(f"Error during Bedrock evaluation: {e}")
            evaluation["bedrock_error"] = str(e)
    
    # Log evaluation results
    log_level = logging.INFO if evaluation["success"] else logging.WARNING
    rating_info = f", rating={evaluation.get('rating', 'N/A')}/5" if "rating" in evaluation else ""
    logging.log(log_level, f"Evaluation results: success={evaluation['success']}{rating_info}")
    
    return evaluation

def check_cluster_connectivity(client):
    """Check if OpenSearch cluster is accessible
    
    Args:
        client (OpenSearchClient): The OpenSearch client
        
    Returns:
        bool: True if connected, False otherwise
    """
    try:
        logging.info("Checking OpenSearch cluster connectivity...")
        # Simple ping to check connectivity
        client.client.cat.health(format="json", v=True)
        logging.info("Successfully connected to OpenSearch cluster")
        return True
    except Exception as e:
        logging.error(f"Error connecting to OpenSearch cluster: {e}")
        return False

def write_result(results, output_file):
    """Write benchmark results to output file
    
    Args:
        results (dict): Dictionary containing benchmark results, config, and summary
        output_file (str): Path to the output file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Ensure the directory exists
        import os
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        
        # Write results to file with pretty formatting
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)  # default=str handles any non-serializable objects
            
        logging.info(f"Results written to {output_file}")
        return True
    except Exception as e:
        logging.error(f"Error writing results to {output_file}: {e}")
        return False

def main():
    # Load configuration
    with open('config.yaml', 'r') as file:
        config = yaml.safe_load(file)
    
    # Initialize client
    client = OpenSearchClient(config)
    
    # Log configuration details
    logging.info(f"Host: {config['OPENSEARCH_HOST']}")
    logging.info(f"Port: {config['OPENSEARCH_PORT']}")
    logging.info(f"Agent ID: {config['AGENT_ID']}")
    
    # Output file for results
    output_file = config.get('OUTPUT_FILE', 'benchmark_results.json')
    
    # Log that we're using Amazon Bedrock for evaluation
    logging.info("Using Amazon Bedrock for agent response evaluation")
    
    # Check cluster connectivity before proceeding
    if not check_cluster_connectivity(client):
        logging.error("Cannot connect to OpenSearch cluster. Please check if the server is running and accessible.")
        logging.error(f"Connection details: {config['OPENSEARCH_HOST']}:{config['OPENSEARCH_PORT']}")
        logging.error("Exiting benchmark...")
        results = {
            "timestamp": int(time.time()),
            "config": {
                "host": config['OPENSEARCH_HOST'],
                "port": config['OPENSEARCH_PORT'],
                "agent_id": config['AGENT_ID']
            },
            "error": "Cannot connect to OpenSearch cluster",
            "tests": [],
            "summary": {
                "total_tests": 0,
                "completed_tests": 0,
                "failed_tests": 0,
                "match_rate": 0,
                "total_time_seconds": 0
            }
        }
        write_result(results, output_file)
        return results
    
    # Load test cases
    test_cases_file = config.get('TEST_CASES', 'test_cases.json')
    with open(test_cases_file, 'r') as test_file:
        test_cases = json.load(test_file)
    
    logging.info(f"Loaded {len(test_cases)} test cases from {test_cases_file}")
    
    # Initialize results list with timestamp and configuration info
    results = {
        "timestamp": int(time.time()),
        "config": {
            "host": config['OPENSEARCH_HOST'],
            "port": config['OPENSEARCH_PORT'],
            "agent_id": config['AGENT_ID']
        },
        "tests": []
    }
    
    # Execute test cases
    for i, test_case in enumerate(test_cases):
        test_num = i + 1
        logging.info(f"\n======= Executing Test {test_num}/{len(test_cases)} =======")
        logging.info(f"Question: {test_case['input']}")
        
        try:
            # Run agent asynchronously
            task_id = run_agent_async(test_case['input'], client)
            
            # Fetch result
            task_data = fetch_result(task_id, client)
            
            # Calculate execution time using server-side timestamps
            create_time_ms = task_data.get('create_time', 0)
            last_update_time_ms = task_data.get('last_update_time', 0)
            
            create_time = create_time_ms / 1000  # Convert milliseconds to seconds
            last_update_time = last_update_time_ms / 1000  # Convert milliseconds to seconds
            execution_time = last_update_time - create_time if create_time > 0 else 0
            
            logging.info(f"Task execution time: {execution_time:.2f}s (created: {create_time_ms}, completed: {last_update_time_ms})")
            
            # Process output
            processed_output = process_output(task_data)
            
            # Evaluate result
            evaluation = evaluate_result(processed_output, test_case['expected_output'])
            
            # Store result
            result = {
                'test_id': test_num,
                'input': test_case['input'],
                'expected_output': test_case['expected_output'],
                'task_id': task_id,
                'execution_time_seconds': round(execution_time, 2),
                'processed_output': processed_output,
                'evaluation': evaluation,
                'status': 'completed'
            }
        except Exception as e:
            # Handle errors
            logging.error(f"Error in test {test_num}: {e}")
            result = {
                'test_id': test_num,
                'input': test_case['input'],
                'expected_output': test_case['expected_output'],
                'error': str(e),
                'status': 'failed'
            }
        
        # Add result to results list
        results["tests"].append(result)
        logging.info(f"Test {test_num} status: {result['status']}")
        
        # Write intermediate results to file
        write_result(results, output_file)
    
    # Calculate summary statistics
    completed_tests = sum(1 for r in results["tests"] if r['status'] == 'completed')
    failed_tests = sum(1 for r in results["tests"] if r['status'] == 'failed')
    
    # Calculate average rating for completed tests with ratings
    rated_tests = [r for r in results["tests"] if r.get('status') == 'completed' and 'rating' in r.get('evaluation', {})]
    average_rating = sum(r.get('evaluation', {}).get('rating', 0) for r in rated_tests) / len(rated_tests) if rated_tests else 0
    
    # Add summary to results
    results["summary"] = {
        "total_tests": len(test_cases),
        "completed_tests": completed_tests,
        "failed_tests": failed_tests,
        "average_rating": round(average_rating, 2),
        "total_time_seconds": round(sum(r.get('execution_time_seconds', 0) for r in results["tests"]), 2)
    }
    
    # Write final results to file
    write_result(results, output_file)
    
    logging.info(f"\n======= Benchmark Complete =======")
    logging.info(f"Total tests: {len(test_cases)}")
    logging.info(f"Successful tests: {completed_tests}")
    logging.info(f"Failed tests: {failed_tests}")
    logging.info(f"Average rating: {average_rating:.2f}/5")
    logging.info(f"Results written to {output_file}")
    
    return results

if __name__ == "__main__":
    main()