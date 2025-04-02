#!/usr/bin/env python3

import os
import json
import re # For parsing retry delay
import time
import google.generativeai as genai # Need this for the exception type
from google.api_core import exceptions as google_exceptions # Import google exceptions

import sys
import os
import concurrent.futures # Added for parallel processing
from itertools import combinations # To generate pairs
from initializer_util import *




###############################################################################
#                          LOAD THE TRADE SCHEMA FILE                         #
###############################################################################

def load_trade_schema(schema_path="global_subschemas/global_trade_schema.json"):
    """
    Loads the trade schema JSON file as a string. 
    This will be embedded directly in the prompt so the AI can see the exact schema.
    """
    if not os.path.exists(schema_path):
        raise FileNotFoundError(
            f"{schema_path} not found. Please make sure the trade schema file is located there."
        )
    with open(schema_path, "r", encoding="utf-8") as file:
        return file.read()

###############################################################################
#                ASK THE AI FOR A SINGLE TRADE RELATION OBJECT               #
###############################################################################

def fetch_trade_relation_from_ai(nationA, nationB, year, relation_id, schema_text, model):
    """
    Polls the AI to obtain a single JSON object matching the trade schema for:
      {
        "relationId": <relation_id>,
        "year": <year>,
        "nationA": <nationA>,
        "nationB": <nationB>,
        ...
      }

    Includes the raw schema in the prompt. Returns a dictionary conforming to that schema.
    Retries if the model output is invalid.
    """

    # Build the prompt, embedding the entire schema JSON directly.
    prompt = f"""
You are given two nations: {nationA} and {nationB}, and the current trade report year {year}.
We have a JSON schema that describes how to structure the trade relationship between these two nations.

Schema (for reference only, do NOT change it):
{schema_text}

Constraints:
- "relationId": must be exactly "{relation_id}".
- "year": must be exactly {year}.
- "nationA": must be exactly "{nationA}".
- "nationB": must be exactly "{nationB}".

Output:
- Produce ONLY a strictly valid JSON object that conforms to the above schema.
- No extra commentary, code fences, or text.

If some fields can be optional in the schema, they can appear if relevant, but
do not remove or rename any required fields or add extra fields not in the schema.
    """.strip()

    attempt = 0
    max_attempts = 15
    while attempt < max_attempts:
        try:
            response = model.generate_content(prompt)
            raw_output = response.text.strip()

            # More robust JSON extraction
            json_start = raw_output.find('{')
            json_end = raw_output.rfind('}')
            if json_start != -1 and json_end != -1:
                raw_json = raw_output[json_start:json_end+1]
            elif raw_output.startswith('{') and raw_output.endswith('}'): # Handle case with no fences
                 raw_json = raw_output
            else:
                 # Handle potential case where AI returns list with one item? Unlikely based on prompt but possible.
                 if raw_output.strip().startswith('[') and raw_output.strip().endswith(']'):
                     try:
                         temp_list = json.loads(raw_output)
                         if isinstance(temp_list, list) and len(temp_list) == 1 and isinstance(temp_list[0], dict):
                             print(f"Warning: AI returned a list with one object for {nationA}-{nationB} trade, extracting the object.")
                             raw_json = json.dumps(temp_list[0]) # Extract the single object
                         else:
                             raise ValueError("AI returned an array, but not a single-item array of objects.")
                     except json.JSONDecodeError:
                          raise ValueError("AI returned something starting/ending with [], but couldn't parse it.")
                 else:
                    raise ValueError("AI response doesn't appear to be a JSON object.")

            # Attempt to parse the extracted JSON string
            trade_obj = json.loads(raw_json)

            # Ensure it's actually a dictionary now
            if not isinstance(trade_obj, dict):
                raise ValueError("Parsed JSON is not a dictionary object.")

            print(json.dumps(trade_obj,indent=2))

            # Optional: Add validation for required trade fields if needed
            # if not all(key in trade_obj for key in ["relationId", "year", "nationA", "nationB", ...]):
            #     raise ValueError("Parsed trade object missing required keys.")

            return trade_obj

        except (json.JSONDecodeError, ValueError) as e: # Catch both parsing and validation errors
            print(f"Failed to parse/validate AI output as valid JSON object for {nationA}-{nationB} trade (Attempt {attempt+1}/{max_attempts}): {e}")
            print(f"Raw AI output was:\n{raw_output}") # Show the problematic output
            attempt += 1
            if attempt == max_attempts: break
            # print("Waiting 2 seconds before retrying...")
            # time.sleep(2)

        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' (Attempt {attempt+1}/{max_attempts}): {rate_limit_error}")
            attempt += 1
            if attempt == max_attempts:
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
            print(f"Encountered unexpected error {type(e).__name__}: {e}. Retrying (attempt {attempt+1}/{max_attempts})...")
            attempt += 1
            if attempt == max_attempts: break
            # print("Waiting 5 seconds before retrying...")
            # time.sleep(5) # Use a longer delay for general errors

    # Fallback if all attempts fail
    print("Max attempts reached. Returning a fallback object.")
    return {
        "relationId": relation_id,
        "year": year,
        "nationA": nationA,
        "nationB": nationB,
        "totalTradeVolume": "No Trade/Embargo ($0)",
        "tradeDifference": {
            "balance": "Perfectly Balanced (0%)",
            "surplusNation": "",
            "deficitNation": ""
        },
        "exportsFromA": [],
        "exportsFromB": []
    }

###############################################################################
#                   BUILD & SAVE TRADE RELATIONS (PARALLELIZED)               #
###############################################################################

def build_trade_relations(nations, year, schema_text, model, max_workers=10):
    """
    Generates trade relations for all unique pairs of nations in parallel.

    :param nations: List of nation names.
    :param year: The reference year.
    :param schema_text: The trade schema text for the AI prompt.
    :param model: The configured AI model instance.
    :param max_workers: Maximum number of threads for parallel execution.
    :return: A list of trade relation dictionaries.
    """
    relations = []
    nation_pairs = list(combinations(nations, 2)) # Generate all unique pairs
    relation_id_counter = 1 # Counter for generating unique relation IDs

    print(f"\nStarting parallel trade relation generation for {len(nation_pairs)} pairs using up to {max_workers} workers...")

    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks for each pair
        for nationA, nationB in nation_pairs:
            relation_id = f"trade-rel-{relation_id_counter}"
            relation_id_counter += 1
            print(f"  Submitting task for trade relation: {nationA} and {nationB} (ID: {relation_id})...")
            future = executor.submit(
                fetch_trade_relation_from_ai,
                nationA,
                nationB,
                year,
                relation_id,
                schema_text,
                model
            )
            futures.append(future)

        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            try:
                trade_data = future.result()
                if trade_data: # Check if fallback wasn't returned or AI failed completely
                    relations.append(trade_data)
                    print(f"  Collected trade data for {trade_data.get('nationA', '?')}-{trade_data.get('nationB', '?')}")
            except Exception as exc:
                # Log exceptions from threads if needed
                print(f'!!! Thread for trade relation generation raised an exception: {exc}')

    print(f"\n--- Parallel Trade Relation Generation Summary ---")
    print(f"Total relations generated: {len(relations)}")
    # Could add more summary details if needed

    return relations

def save_trade_relations(relations, filename="global_trade.json"):
    """
    Saves the final array of trade relations to a JSON file.
    """
    if not relations:
        print("No trade relations to save.")
        return

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(relations, f, indent=2)
    print(f"Saved {len(relations)} trade relations to {filename}")

###############################################################################
#                                   MAIN                                      #
###############################################################################

def main():
    # Example list of nations
    nations = ["US", "UK", "West Germany","France","Saudi Arabia"]
    year = 1965 # Example year

    # 1) Configure the AI model (global so it can be reused)
    global model
    model = configure_genai(model="gemini-2.0-flash",temp=0.5)

    # 2) Load the schema text from file
    schema_text = load_trade_schema("global_subschemas/global_trade_schema.json")

    # 3) Build the trade relations array, one pair at a time
    relations = build_trade_relations(nations, year, schema_text)

    # 4) Save them to a single JSON file
    save_trade_relations(relations, filename="simulation_data/generated_timeline_1965/global_trade.json")
    

def initialize_trade(nations: list, timeline: str, max_workers=10):
    """
    Initializes global trade data in parallel and saves it.
    """
    global model # Ensure model is configured and accessible globally or passed down
    model = configure_genai(model="gemini-2.0-flash", temp=0.5) # Configure the model used by threads
    schema_text = load_trade_schema("global_subschemas/global_trade_schema.json")

    print(f"Initializing global trade for {len(nations)} nations (Year: {timeline})...")
    relations = build_trade_relations(
        nations=nations,
        year=timeline,
        schema_text=schema_text,
        model=model,
        max_workers=max_workers
    )

    output_filename = f"simulation_data/generated_timeline_{timeline}/global_trade.json"
    save_trade_relations(relations, filename=output_filename)
    return relations

if __name__ == "__main__":
    # Example of calling the parallelized initialization
    example_nations = ["US", "UK", "West Germany", "France", "Saudi Arabia", "Japan"]
    example_year = "1975"
    example_workers = 6 # Adjust based on system/API limits
    output_file = f"simulation_data/generated_timeline_{example_year}/global_trade.json"

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Call the main initialization function
    initialize_trade(
        nations=example_nations,
        timeline=example_year,
        max_workers=example_workers
    )

    # Note: The original main() function is kept above but is no longer the primary entry point
    # if this script is run directly due to the __name__ == "__main__": block above.
    # You might want to remove or comment out the old main() if it's redundant.
