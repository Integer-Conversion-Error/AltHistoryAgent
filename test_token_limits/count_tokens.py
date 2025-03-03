import sys
import json
import tiktoken
import os

def count_tokens_in_file(file_path: str, model_name: str = "gemini-2.0-flash-exp"):
    """
    Counts the number of tokens used when passing a given JSON file into a model.

    :param file_path: Path to the JSON schema file.
    :param model_name: The name of the model (default: 'gemini-2.0-flash-exp').
    :return: The number of tokens.
    """
    try:
        # 1) Attempt to load the encoding for the given model name:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        # 2) If model name is unrecognized, fall back to a known model or a guess:
        print(f"Model '{model_name}' not recognized by tiktoken. Falling back to 'gpt-4'.")
        encoding = tiktoken.encoding_for_model("gpt-4")

    # 3) Load the file content:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        file_content = f.read()

    # 4) Encode and count tokens:
    token_ids = encoding.encode(file_content)
    num_tokens = len(token_ids)
    return num_tokens

if __name__ == "__main__":
    # Example usage:
    # if len(sys.argv) < 2:
    #     print("Usage: python count_tokens.py <path_to_json_schema> [model_name]")
    #     sys.exit(1)

    schema_file = "test_token_limits/test.json"
    model = "gpt-4"
    
    try:
        tokens = count_tokens_in_file(schema_file, model)
        print(f"File: {schema_file}")
        print(f"Model: {model}")
        print(f"Token Count: {tokens}")
    except Exception as e:
        print(f"Error: {e}")
