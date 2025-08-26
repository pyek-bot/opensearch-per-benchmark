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
        
        protocol = config.get('OPENSEARCH_PROTOCOL', 'https').lower()
        use_ssl = protocol == 'https'
        
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
        endpoint = f"{self.base_uri}/agents/{agent_id}/_execute?async=true"
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
            logging.debug(f"Full agent execution response: {json.dumps(response, indent=2)}")
                
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
    agent_id = agent_id or client.agent_id
    response = client.execute_agent_transport(agent_id, question)
    task_id = response.get('task_id')
    
    if not task_id:
        raise ValueError(f"Failed to get task_id from response: {response}")
    
    logging.info(f"Agent execution started with task_id: {task_id}")
    return task_id

def fetch_result(task_id, client, poll_interval=10, max_retries=100):
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
            endpoint = f"{client.base_uri}/tasks/{task_id}"
            task_data = client.client.transport.perform_request("GET", endpoint)
        
            logging.debug(f"Task data (attempt {attempt+1}): {json.dumps(task_data, indent=2)}")

            state = task_data.get('state')
            logging.info(f"Task {task_id} state: {state} (attempt {attempt+1}/{max_retries})")
            
            if state == 'COMPLETED':
                logging.info(f"Task {task_id} completed successfully")
                return task_data
            elif state == 'FAILED':
                error_msg = "Unknown error"
                if 'response' in task_data and 'error_message' in task_data['response']:
                    error_msg = task_data['response']['error_message']
                logging.error(f"Task {task_id} failed: {error_msg}")

                return task_data
            elif state == 'RUNNING' or state == 'CREATED':
                logging.info(f"Task {task_id} is {state}. Waiting {poll_interval} seconds before checking again.")
                time.sleep(poll_interval)
            else:
                logging.warning(f"Unknown task state: {state}")
                time.sleep(poll_interval)
        except Exception as e:
            logging.error(f"Error polling task {task_id}: {e}")
            time.sleep(poll_interval)
    
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

    state = task_data.get('state')
    response = task_data.get('response', {})
    processed_output = {
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
            inference_results = response.get('inference_results', [{}])[0]
            output_items = inference_results.get('output', [])
            
            for item in output_items:
                if item.get('name') == 'response' and 'dataAsMap' in item:
                    response_content = item['dataAsMap'].get('response', '')
                    response_content_value = response_content
                    break
            
            if not response_content_value:
                response_content_value = ''
                logging.warning("Could not find response content in the expected format")
        except Exception as e:
            logging.error(f"Error extracting response content: {e}")
            response_content_value = ''
            processed_output['extraction_error'] = str(e)
    elif state == 'FAILED':
        processed_output['error_message'] = response.get('error_message', 'Unknown error')
        response_content_value = ''
    else:
        response_content_value = ''
    
    logging.info(f"Processed output: {json.dumps(processed_output, indent=2)}")
    # Store the response content in a separate field for evaluation
    processed_output['_response_content'] = response_content_value
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
    state = actual_output.get('state', '')
    evaluation = {
        "expected_output": expected_output,
        "state": state
    }

    if state == 'FAILED':
        evaluation["error_message"] = actual_output.get('error_message', 'Unknown error')
        evaluation["success"] = False
        evaluation["actual_output"] = ""
        logging.warning(f"Task failed: {evaluation['error_message']}")
        return evaluation
        
    actual_output_value = actual_output.get('_response_content', '')
    evaluation["actual_output"] = actual_output_value
    evaluation["success"] = state == 'COMPLETED'
    
    if evaluation["success"]:
        try:
            logging.info("Sending to Bedrock for evaluation")
            bedrock_evaluation = evaluate_with_bedrock(
                actual_output_value,
                expected_output
            )
            evaluation.update(bedrock_evaluation)
            if "rating" in evaluation:
                logging.info(f"Bedrock evaluation rating: {evaluation['rating']}/5")
            else:
                logging.warning("Bedrock evaluation did not return a rating")
                
        except Exception as e:
            logging.error(f"Error during Bedrock evaluation: {e}")
            evaluation["bedrock_error"] = str(e)
    
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
        client.client.cat.health(format="json", v=True)
        logging.info("Successfully connected to OpenSearch cluster")
        return True
    except Exception as e:
        logging.error(f"Error connecting to OpenSearch cluster: {e}")
        return False

def fetch_agent_details(client, agent_id):
    """Fetch agent details from the OpenSearch API
    
    Args:
        client (OpenSearchClient): The OpenSearch client
        agent_id (str): The ID of the agent to fetch details for
        
    Returns:
        dict: Agent details including name, type, tools, parameters, etc.
    """
    try:
        logging.info(f"Fetching details for agent {agent_id}")
        endpoint = f"{client.base_uri}/agents/{agent_id}"
        agent_data = client.client.transport.perform_request("GET", endpoint)
        logging.info(f"Successfully fetched details for agent {agent_id}")
        logging.debug(f"Agent details: {json.dumps(agent_data, indent=2)}")
        return agent_data
    except Exception as e:
        logging.error(f"Error fetching agent details: {e}")
        return None

def write_result(results, output_file):
    """Write benchmark results to output file
    
    Args:
        results (dict): Dictionary containing benchmark results, config, and summary
        output_file (str): Path to the output file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import os
        import json as json_lib
        
        # Process the results to filter out internal fields
        filtered_results = json_lib.loads(json.dumps(results, default=str))
        
        # Remove internal fields from the output
        for test in filtered_results.get("tests", []):
            if "processed_output" in test and "_response_content" in test["processed_output"]:
                del test["processed_output"]["_response_content"]
                
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(filtered_results, f, indent=2, default=str) 
            
        logging.info(f"Results written to {output_file}")
        return True
    except Exception as e:
        logging.error(f"Error writing results to {output_file}: {e}")
        return False

def main():
    with open('config.yaml', 'r') as file:
        config = yaml.safe_load(file)

    client = OpenSearchClient(config)
    
    logging.info(f"Host: {config['OPENSEARCH_HOST']}")
    logging.info(f"Port: {config['OPENSEARCH_PORT']}")
    logging.info(f"Agent ID: {config['AGENT_ID']}")
    
    output_file = config.get('OUTPUT_FILE', 'benchmark_results.json')
    logging.info("Using Amazon Bedrock for agent response evaluation")
    
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
            "agent_info": {},
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
    
    test_cases_file = config.get('TEST_CASES', 'test_cases.json')
    with open(test_cases_file, 'r') as test_file:
        test_cases = json.load(test_file)
    
    logging.info(f"Loaded {len(test_cases)} test cases from {test_cases_file}")
    
    # Fetch agent details
    agent_id = config['AGENT_ID']
    agent_details = fetch_agent_details(client, agent_id)
    
    agent_info = {}
    if agent_details:
        # Extract relevant agent information
        if 'name' in agent_details:
            agent_info['name'] = agent_details.get('name', '')
        if 'type' in agent_details:
            agent_info['type'] = agent_details.get('type', '')
        if 'description' in agent_details:
            agent_info['description'] = agent_details.get('description', '')
        if 'llm' in agent_details:
            agent_info['llm'] = agent_details.get('llm', {})
        if 'tools' in agent_details:
            agent_info['tools'] = agent_details.get('tools', [])
        if 'parameters' in agent_details:
            agent_info['parameters'] = agent_details.get('parameters', {})
        if 'memory' in agent_details:
            agent_info['memory'] = agent_details.get('memory', {})
        if 'created_time' in agent_details:
            agent_info['created_time'] = agent_details.get('created_time', 0)
        if 'last_updated_time' in agent_details:
            agent_info['last_updated_time'] = agent_details.get('last_updated_time', 0)
    
    results = {
        "timestamp": int(time.time()),
        "config": {
            "host": config['OPENSEARCH_HOST'],
            "port": config['OPENSEARCH_PORT'],
            "agent_id": config['AGENT_ID']
        },
        "agent_info": agent_info,
        "tests": []
    }
    
    for i, test_case in enumerate(test_cases):
        test_num = i + 1
        logging.info(f"\n======= Executing Test {test_num}/{len(test_cases)} =======")
        logging.info(f"Question: {test_case['input']}")
        
        try:
            task_id = run_agent_async(test_case['input'], client)
            task_data = fetch_result(task_id, client)
            
            create_time_ms = task_data.get('create_time', 0)
            last_update_time_ms = task_data.get('last_update_time', 0)
            
            create_time = create_time_ms / 1000
            last_update_time = last_update_time_ms / 1000
            execution_time = last_update_time - create_time if create_time > 0 else 0
            
            logging.info(f"Task execution time: {execution_time:.2f}s (created: {create_time_ms}, completed: {last_update_time_ms})")
            
            processed_output = process_output(task_data)
            evaluation = evaluate_result(processed_output, test_case['expected_output'])
            result = {
                'test_id': test_num,
                'input': test_case['input'],
                'task_id': task_id,
                'execution_time_seconds': round(execution_time, 2),
                'processed_output': processed_output,
                'evaluation': evaluation,
                'status': 'completed'
            }
        except Exception as e:
            logging.error(f"Error in test {test_num}: {e}")
            result = {
                'test_id': test_num,
                'input': test_case['input'],
                'error': str(e),
                'status': 'failed'
            }
        
        results["tests"].append(result)
        logging.info(f"Test {test_num} status: {result['status']}")
        write_result(results, output_file)
    
    # summary
    completed_tests = sum(1 for r in results["tests"] if r['status'] == 'completed')
    failed_tests = sum(1 for r in results["tests"] if r['status'] == 'failed')
    rated_tests = [r for r in results["tests"] if r.get('status') == 'completed' and 'rating' in r.get('evaluation', {})]
    average_rating = sum(r.get('evaluation', {}).get('rating', 0) for r in rated_tests) / len(rated_tests) if rated_tests else 0
    results["summary"] = {
        "total_tests": len(test_cases),
        "completed_tests": completed_tests,
        "failed_tests": failed_tests,
        "average_rating": round(average_rating, 2),
        "total_time_seconds": round(sum(r.get('execution_time_seconds', 0) for r in results["tests"]), 2)
    }
    
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