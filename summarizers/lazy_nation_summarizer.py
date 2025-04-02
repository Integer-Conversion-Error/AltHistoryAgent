import os
import json
import re # For parsing retry delay
import time # For sleep
from typing import List
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
from summarizers.initializer_util import *



def gather_json_files(root_folder: str) -> List[str]:
    """
    Recursively gather all .json files from the given root folder.
    """
    json_files = []
    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.endswith(".json"):
                full_path = os.path.join(dirpath, filename)
                json_files.append(full_path)
    return json_files

def load_json_content(file_paths: List[str]) -> dict:
    """
    Load and return the content of each JSON file as a dict keyed by filename.
    """
    all_content = {}
    for path in file_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_content[path] = json.load(f)
        except Exception as e:
            print(f"Error reading {path}: {e}")
    return all_content

def summarize_content(model, all_content: dict) -> str:
    """
    Summarize the combined content of all JSON files using the Gemini model.
    You can customize the prompt as needed for your use-case.
    """
    # Convert all loaded JSON to a text representation
    # For an "exhaustive" summary, you might want to chunk the data if it's large.
    # For simplicity, let's combine everything into one string:
    combined_text = ""
    for filename, content in all_content.items():
        combined_text += f"\n---\nFile: {filename}\n{json.dumps(content, indent=2)}\n"

    prompt = (
        "You are given JSON schemas and data describing nations at different points in history. "
        "Summarize the data *exhaustively*, highlighting key elements, structures, and historical context.\n\n"
        "Here is the data:\n"
        f"{combined_text}\n\n"
        "Now, please provide a comprehensive, structured summary of this information."
    )

    max_retries = 3
    base_retry_delay = 5

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            # Check if response is valid and has text
            if response and hasattr(response, 'text') and len(response.text) > 0:
                 return response.text
            else:
                 # Handle cases where response might be empty or malformed (though less likely for summarization)
                 print(f"Warning: Received empty or invalid response from AI (Attempt {attempt + 1}/{max_retries}).")
                 # Decide if retry is appropriate or return empty string
                 if attempt == max_retries - 1:
                     print("Max retries reached after empty/invalid response.")
                     return "" # Return empty on final failure
                 # print(f"Waiting {base_retry_delay} seconds before retrying...")
                 # time.sleep(base_retry_delay)
                 continue # Go to next attempt

        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' during summarization (Attempt {attempt + 1}/{max_retries}): {rate_limit_error}")
            if attempt == max_retries - 1:
                print(f"Max retries reached for model '{model_name}' after rate limit error.")
                break
            # Try to parse retry delay
            retry_delay = 60 # Default delay
            error_message = str(rate_limit_error)
            match = re.search(r'retry_delay.*?seconds:\s*(\d+)', error_message, re.IGNORECASE)
            if hasattr(rate_limit_error, 'metadata'):
                 metadata = getattr(rate_limit_error, 'metadata', {})
                 if isinstance(metadata, dict) and 'retryInfo' in metadata and 'retryDelay' in metadata['retryInfo']:
                     delay_str = metadata['retryInfo']['retryDelay'].get('seconds', '0')
                     if delay_str.isdigit():
                         retry_delay = int(delay_str)
            elif match:
                 retry_delay = int(match.group(1))
            # print(f"Waiting for {retry_delay} seconds due to rate limit...")
            # time.sleep(retry_delay)
        except Exception as e:
            print(f"Unexpected error during summarization (Attempt {attempt + 1}/{max_retries}): {type(e).__name__} - {e}")
            if attempt == max_retries - 1: break
            # print(f"Waiting {base_retry_delay} seconds before retrying...")
            # time.sleep(base_retry_delay)

    # If loop finishes without returning
    print("Failed to generate summary after all retries.")
    return ""

def main():
    # 1. Configure the generative model
    model = configure_genai(temp=0.1)

    # 2. Gather all JSON files (adjust 'nation_subschemas' to your actual directory)
    directory_to_scan = "simulation_data/generated_timelines/generated_nations_1965/Soviet Union"
    json_files = gather_json_files(directory_to_scan)

    if not json_files:
        print(f"No .json files were found in {directory_to_scan}")
        return

    # 3. Load JSON content
    all_content = load_json_content(json_files)

    # 4. Summarize the loaded content
    summary = summarize_content(model, all_content)

    # 5. Print or save the summary
    print("\n=== EXHAUSTIVE SUMMARY ===\n")
    print(summary)

def load_and_summarize_nation(nation = "Soviet Union",timeline = "1965"):
    directory_to_scan = f"simulation_data/generated_timelines_{timeline}/generated_nations/{nation}"
    model = configure_genai(temp=0.1)
    json_files = gather_json_files(directory_to_scan)

    if not json_files:
        print(f"No .json files were found in {directory_to_scan}")
        return

    # 3. Load JSON content
    all_content = load_json_content(json_files)

    # 4. Summarize the loaded content
    summary = summarize_content(model, all_content)

    # 5. Print or save the summary
    print("\n=== EXHAUSTIVE SUMMARY ===\n")
    print(summary)
    return summary

if __name__ == "__main__":
    main()
