# OpenSearch ML and AWS Bedrock Reference

This document provides reference information for working with the OpenSearch ML client and AWS Bedrock APIs based on analysis of the repositories.

## Module Structure and Imports

The correct import path for MLCommonClient is:

```python
from opensearch_py_ml.ml_commons import MLCommonClient
```

NOT:
```python
from opensearch_py_ml import MLCommonClient  # Incorrect!
```

## Client Initialization

### OpenSearch Client Initialization

```python
from opensearchpy import OpenSearch

# Create OpenSearch client
os_client = OpenSearch(
    hosts=[{'host': host, 'port': port}],
    use_ssl=use_ssl,
    verify_certs=verify_certs
)

# Add authentication if needed
os_client = OpenSearch(
    hosts=[{'host': host, 'port': port}],
    http_auth=(username, password),
    use_ssl=use_ssl,
    verify_certs=verify_certs
)
```

### ML Client Initialization

```python
from opensearch_py_ml.ml_commons import MLCommonClient

# Create ML client using an existing OpenSearch client
ml_client = MLCommonClient(os_client=os_client)
```

## Working with ML Agents

### Executing an Agent

```python
# Executing an agent synchronously
response = ml_client.execute_agent(
    agent_id="your-agent-id",
    parameters={"question": "your question here"}
)

# Executing an agent asynchronously
response = ml_client.execute_agent(
    agent_id="your-agent-id",
    parameters={"question": "your question here"},
    async_execution=True
)

# The async response will contain a task_id
task_id = response.get('task_id')
```

### Getting Task Status

```python
# Get status of an asynchronous task
task_data = ml_client.get_task(task_id)

# Check task state
state = task_data.get('state')  # 'CREATED', 'RUNNING', 'COMPLETED', 'FAILED'
```

## AWS Bedrock API Integration

The AWS Bedrock API is used for evaluating agent responses by comparing them with expected outputs. 
This section provides details on how to integrate with the AWS Bedrock API based on analysis of the `aws-bedrock-testing` repository.

### Client Setup

```python
import boto3

# Initialize Bedrock client
bedrock_client = boto3.client(
    'bedrock-runtime',
    region_name='us-east-1'  # or use environment variables: os.getenv('AWS_REGION', 'us-east-1')
)
```

### Making API Calls with the Converse API

The AWS Bedrock Converse API is a unified API for interacting with various foundation models:

```python
# Basic structure for a Bedrock Converse API call
response = bedrock_client.converse(
    modelId="us.anthropic.claude-3-5-sonnet-20241022-v2:0",  # Model ID
    messages=[
        {
            "role": "user",
            "content": [{"text": "Your prompt text here"}]
        }
    ],
    inferenceConfig={
        "maxTokens": 2000,
        "temperature": 0,
        "topP": 0.9
    }
)
```

### Common Model IDs

```python
# Claude 3.7 Sonnet
"us.anthropic.claude-3-7-sonnet-20250219-v1:0"

# Claude 3.5 Sonnet
"us.anthropic.claude-3-5-sonnet-20241022-v2:0"

# Claude 3.5 Haiku
"us.anthropic.claude-3-5-haiku-20241022-v1:0"

# Claude 3 Opus
"us.anthropic.claude-3-opus-20240229-v1:0"

# Claude 3 Sonnet
"us.anthropic.claude-3-sonnet-20240229-v1:0"

# Claude 3 Haiku
"us.anthropic.claude-3-haiku-20240307-v1:0"
```

### Processing Responses

```python
# Extract text from the response
if "output" in response and "message" in response["output"]:
    message = response["output"]["message"]
    
    if "content" in message:
        for content_block in message["content"]:
            if "text" in content_block:
                response_text = content_block["text"]
                # Process the text...
            elif "toolUse" in content_block:
                # Handle tool calls...
                tool_use = content_block["toolUse"]
                tool_name = tool_use.get('name')
                tool_input = tool_use.get('input')
```

### Extracting JSON from Responses

When asking the model to return JSON formatted data:

```python
import re
import json

# Find JSON in the response text
json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
if json_match:
    json_str = json_match.group()
    try:
        parsed_data = json.loads(json_str)
        # Now use the parsed JSON data
    except json.JSONDecodeError as e:
        # Handle JSON parsing errors
        print(f"Error parsing JSON: {e}")
```

### Tracking Token Usage

```python
# Get usage statistics from the response
usage = response.get('usage', {})
input_tokens = usage.get('inputTokens', 0)
output_tokens = usage.get('outputTokens', 0)
total_tokens = usage.get('totalTokens', 0)
```

### Error Handling

```python
try:
    response = bedrock_client.converse(**api_params)
    # Process successful response...
    
except Exception as e:
    error_str = str(e).lower()
    
    # Handle model validation errors
    if "validationexception" in error_str and "model" in error_str:
        print("Model ID may be incorrect or unavailable in your region")
    
    # Handle access denied errors
    elif "accessdenied" in error_str:
        print("Check your AWS credentials and permissions")
    
    # Handle other errors
    else:
        print(f"Error calling Bedrock API: {e}")
```

### Response Evaluation Format

When using Bedrock to evaluate agent responses, the evaluation prompt should request a structured response:

```
Format your response as a valid JSON with the following structure:
{
  "rating": [1-5 as a number],
  "reasoning": [your detailed explanation],
  "accuracy": [brief assessment of accuracy],
  "completeness": [brief assessment of completeness],
  "relevance": [brief assessment of relevance]
}
```

## Client Wrapper Pattern

The `opensearch-ml-quickstart` repository uses a wrapper pattern to encapsulate client functionality:

```python
class OsMlClientWrapper:
    def __init__(self, os_client: OpenSearch) -> None:
        self.os_client = os_client
        self.ml_commons_client = MLCommonClient(os_client=self.os_client)
        # Additional initialization
```

## ML Model Management

```python
# Register a model
model_id = ml_client.register_model(
    model_name="your-model-name",
    function_name="REMOTE",
    model_group_id="your-model-group-id", 
    description="Model description",
    connector_id="connector-id"
)

# Deploy a model
ml_client.deploy_model(model_id=model_id)

# Delete a model
ml_client.delete_model(model_id=model_id)
```

## Response Processing

For agent responses, the structure will depend on whether the execution was synchronous or asynchronous.

### Asynchronous Task Response Structure

Initial execution response:
```json
{
    "task_id": "task-id-string",
    "status": "RUNNING",
    "response": {
        "memory_id": "memory-id-string",
        "parent_interaction_id": "interaction-id-string"
    }
}
```

Task status response (in-progress):
```json
{
    "task_type": "AGENT_EXECUTION",
    "function_name": "AGENT",
    "state": "RUNNING",
    "worker_node": ["node-id"],
    "create_time": 1756072670711,
    "last_update_time": 1756072684863,
    "is_async": true,
    "response": {
        "memory_id": "memory-id-string",
        "executor_agent_memory_id": "executor-memory-id",
        "parent_interaction_id": "parent-interaction-id",
        "executor_agent_parent_interaction_id": "executor-interaction-id"
    }
}
```

Task status response (completed):
```json
{
    "task_type": "AGENT_EXECUTION",
    "function_name": "AGENT",
    "state": "COMPLETED",
    "worker_node": ["node-id"],
    "create_time": 1756072670711,
    "last_update_time": 1756072744198,
    "is_async": true,
    "response": {
        "memory_id": "memory-id-string",
        "executor_agent_memory_id": "executor-memory-id",
        "inference_results": [
            {
                "output": [
                    {
                        "result": "memory-id",
                        "name": "memory_id"
                    },
                    {
                        "result": "parent-id",
                        "name": "parent_interaction_id"
                    },
                    {
                        "name": "response",
                        "dataAsMap": {
                            "response": "Actual agent response text..."
                        }
                    }
                ]
            }
        ],
        "parent_interaction_id": "parent-id",
        "executor_agent_parent_interaction_id": "executor-id"
    }
}
```

Task status response (failed):
```json
{
    "task_type": "AGENT_EXECUTION",
    "function_name": "AGENT",
    "state": "FAILED",
    "worker_node": ["node-id"],
    "create_time": 1756072437866,
    "last_update_time": 1756072438828,
    "is_async": true,
    "response": {
        "error_message": "Error message here",
        "memory_id": "memory-id",
        "parent_interaction_id": "parent-id"
    }
}
```

## Error Handling

```python
try:
    response = ml_client.execute_agent(
        agent_id="your-agent-id",
        parameters={"question": "your question"}
    )
except Exception as e:
    print(f"Error executing agent: {e}")
```

For asynchronous tasks, check the task state to determine if it was successful:

```python
task_data = ml_client.get_task(task_id)
state = task_data.get('state')

if state == 'COMPLETED':
    # Process completed task
    print("Task completed successfully")
elif state == 'FAILED':
    # Handle failed task
    error_msg = task_data.get('response', {}).get('error_message', 'Unknown error')
    print(f"Task failed: {error_msg}")
```