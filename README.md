# OpenSearch PER Benchmark

A Python tool for benchmarking an OpenSearch Plan-Execute-Reflect (PER) Agent. This tool sends test cases to an OpenSearch agent and evaluates the responses against expected outputs.

## Overview

The OpenSearch PER Benchmark tool:

1. Connects to an OpenSearch server
2. Sends test questions to a PER agent
3. Waits for and retrieves the agent's responses
4. Evaluates the responses against expected outputs
5. Generates detailed performance metrics and results

## Installation

### Prerequisites

- Python 3.8+
- Access to an OpenSearch cluster with PER agent(s) configured
- Required Python packages:

```bash
pip install opensearchpy opensearch_py_ml PyYAML boto3
```

## Configuration

Edit the `config.yaml` file to configure the benchmark:

```yaml
OPENSEARCH_HOST: localhost
OPENSEARCH_PASSWORD: admin
OPENSEARCH_USER: admin
OPENSEARCH_PORT: 9200
AGENT_ID: mTYS3pgBCSP1TPM505Jt
TEST_CASES: data/test_cases.json
OUTPUT_FILE: data/benchmark_results.json
```

- `OPENSEARCH_HOST`: Your OpenSearch host (default: localhost)
- `OPENSEARCH_PORT`: Your OpenSearch port (default: 9200)
- `OPENSEARCH_USER`: Username for OpenSearch
- `OPENSEARCH_PASSWORD`: Password for OpenSearch
- `AGENT_ID`: The ID of the PER agent to test
- `TEST_CASES`: Path to the test cases JSON file
- `OUTPUT_FILE`: Path where benchmark results should be saved

## Test Cases

Create test cases in a JSON file (default: `data/test_cases.json`, as specified in `TEST_CASES`):

```json
[
  {
    "input": "analyze my cluster",
    "expected_output": "The cluster analysis shows multiple system indices..."
  },
  {
    "input": "show me the status of all indices",
    "expected_output": "All indices in the cluster are healthy with green status..."
  }
]
```

Each test case consists of:
- `input`: The question to send to the PER agent
- `expected_output`: The expected response (used for evaluation)

## Running the Benchmark

Execute the benchmark with:

```bash
python main.py
```

The script will:
1. Load the configuration and test cases
2. Execute each test case against the PER agent
3. Record and evaluate the responses
4. Save the results to the specified output file
5. Display summary statistics upon completion

## Output

The benchmark generates a detailed JSON result file containing:

- Timestamp and configuration information
- Individual test results with:
  - Input and expected output
  - Actual agent response
  - Execution time
  - Success/failure status
  - Evaluation metrics
- Summary statistics with:
  - Total tests executed
  - Success/failure counts
  - Match rate
  - Total execution time

## Logging

The benchmark logs its progress to the console with detailed information about:
- Test execution
- Agent responses
- Evaluation results
- Error messages

## Customization

You can modify the evaluation criteria in the `evaluate_result()` function to implement more sophisticated comparison methods, including integration with Amazon Bedrock for advanced text comparison.

## AWS Bedrock Configuration

The benchmark uses Amazon Bedrock to evaluate agent responses against expected outputs. The configuration is split between:

### 1. Credentials (via environment variables)

```bash
# Set AWS credentials in your environment
export AWS_ACCESS_KEY_ID=your_access_key_id
export AWS_SECRET_ACCESS_KEY=your_secret_access_key
export AWS_SESSION_TOKEN=your_session_token  # if using temporary credentials
```

### 2. Region and Model (via config.yaml)

```yaml
# AWS Bedrock configuration in config.yaml
AWS_REGION: us-east-1
BEDROCK_MODEL_ID: us.anthropic.claude-3-5-sonnet-20241022-v2:0
```

The AWS credentials must have permission to invoke the Bedrock API. You can run the export commands before executing the benchmark script, or add them to your shell profile.

## Security Note

For production use, consider:
- Using AWS credential providers like IAM roles for EC2 or ECS tasks
- Implementing proper error handling and retry logic for production environments
- Enabling SSL certificate verification for secure connections
