# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

The opensearch-per-benchmark is a Python tool for benchmarking an OpenSearch Personalized Entity Resolution (PER) Agent. It sends test cases to an OpenSearch agent and evaluates the responses against expected outputs using Amazon Bedrock's converse API for comprehensive comparison analysis.

## Commands

### Running the Benchmark

To run the benchmark:

```bash
python main.py
```

This will read configuration from `config.yaml` and test cases from `test_cases.json`, then execute the benchmark.

### Dependencies

This project requires the following Python packages:
- opensearchpy
- opensearch_py_ml
- PyYAML
- boto3 (for AWS Bedrock API integration)

To install dependencies:

```bash
pip install opensearchpy opensearch_py_ml PyYAML boto3
```

## Code Architecture

### Core Components

1. **OpenSearchClient** (main.py):
   - Handles connection to OpenSearch server
   - Initializes both standard OpenSearch client and ML client

2. **Agent Interaction** (main.py):
   - `run_agent_async`: Sends input to the PER agent and returns task ID
   - `fetch_result`: Polls for task completion and retrieves results

3. **Result Processing** (main.py):
   - `process_output`: Processes raw agent output to extract relevant information
   - `evaluate_result`: Uses Amazon Bedrock's converse API to compare agent output with expected output
   - `write_result`: Saves comparison results and performance metrics

### Configuration Files

1. **config.yaml**:
   - OpenSearch connection settings (host, port, credentials)
   - Agent ID
   - Test case file location
   - AWS credentials and region for Bedrock API access
   - Bedrock model configuration for result comparison

2. **test_cases.json**:
   - Contains test inputs and expected outputs for the benchmark
   - Format: Array of objects with "input" and "expected_output" fields

### Data Flow

1. The benchmark loads connection parameters from config.yaml
2. It establishes a connection to the OpenSearch server
3. It loads test cases from test_cases.json
4. For each test case:
   - It sends the input to the PER agent asynchronously
   - It polls for completion and retrieves the result
   - It processes the agent output to extract the relevant information
   - It sends both the actual output and expected output to Amazon Bedrock's converse API
   - It analyzes the comparison results to evaluate agent performance
   - It saves the evaluation results and metrics

## Notes for Development

- The benchmark framework is designed for asynchronous agent evaluation with comprehensive result comparison using Bedrock
- When implementing the evaluation functions, consider using structured metrics for consistent comparison
- The main.py file has duplicate `if __name__ == "__main__"` blocks that need to be fixed
- For security, consider storing OpenSearch and AWS credentials in environment variables rather than in the config file
- Consider adding support for batch processing and parallel agent evaluation for larger test sets
- Results should be stored in a structured format (JSON/CSV) to enable further analysis and visualization