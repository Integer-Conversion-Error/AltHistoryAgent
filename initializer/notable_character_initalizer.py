#!/usr/bin/env python3

import os
import json
import re # For parsing retry delay
import time
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
from collections import defaultdict
import concurrent.futures # Added for parallel processing
from initializer_util import *

###############################################################################
#                      LOADING THE SCHEMA FROM A JSON FILE                    #
###############################################################################

def load_schema_text(schema_file="notable_characters_schema.json"):
    """
    Reads the entire JSON schema from a file as text, so it can be
    embedded directly in the AI prompt.
    """
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file '{schema_file}' not found.")

    with open(schema_file, "r", encoding="utf-8") as f:
        return f.read()  # Return the raw JSON text (not parsed)

###############################################################################
#                ASKING THE AI FOR A SINGLE NOTABLE FIGURE                    #
###############################################################################

def fetch_single_character_from_ai(nation, model, schema_text, used_names, reference_year):
    """
    Prompts the AI model to obtain ONE JSON object representing
    a notable historical figure for `nation`, embedding the full schema text
    in the prompt, ensuring we do NOT reuse any name in `used_names`, and
    making sure the character is relevant to the given `reference_year`.

    The final JSON must meet the required fields from the schema.
    """

    used_names_str = ", ".join(sorted(used_names)) if used_names else "None so far"

    prompt = f"""
You are given the following JSON Schema for "Notable Historical Figures". Make one item of the array described in the schema.

{schema_text}

We are focusing on the year {reference_year}, so the character should be politically relevant around that time
(either alive or significantly influential in that period).

Already-generated characters for {nation} have the following names: {used_names_str}. Do not pick these characters.
Create exactly ONE new notable historical figure (strictly valid JSON) for the nation: {nation},
with a unique 'fullName' that is different from any listed above.

Key requirements:
1. "nationality" must be "{nation}".
2. They must be relevant around the year {reference_year}. 
   (E.g., they could be alive, or recently deceased, or historically significant then.)
3. Must include the required fields:
   "fullName", "birthDate", "nationality", "role",
   "majorContributions", "associatedEvents", "publicPerception", "legacy"
4. Respect the valid enums (e.g., role, publicPerception, legacy).
5. Output ONLY the JSON object, with no extra commentary or Markdown.
6. The events they partake in MUST be before {reference_year}
7. Focus on politically relevant people, like politicians, leaders of movements, major business leaders, figureheads, etc.

Thank you.
    """

    attempt = 0
    max_attempts = 4  # We'll give extra attempts in case the AI duplicates or fails
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
                             print("Warning: AI returned a list with one object, extracting the object.")
                             raw_json = json.dumps(temp_list[0]) # Extract the single object
                         else:
                             raise ValueError("AI returned an array, but not a single-item array of objects.")
                     except json.JSONDecodeError:
                          raise ValueError("AI returned something starting/ending with [], but couldn't parse it.")
                 else:
                    raise ValueError("AI response doesn't appear to be a JSON object.")

            # Attempt to parse the extracted JSON string
            character_obj = json.loads(raw_json)

            # Ensure it's actually a dictionary now
            if not isinstance(character_obj, dict):
                raise ValueError("Parsed JSON is not a dictionary object.")

            print(json.dumps(character_obj,indent=2))
            # Check nationality (Optional, but good practice)
            # if character_obj.get("nationality") != nation:
            #     print(f"Warning: Character nationality mismatch ('{character_obj.get('nationality')}' vs expected '{nation}').")
                # Decide if this is a retryable error or just a warning
                # For now, let's treat as warning and proceed, but could add retry logic:
                # attempt += 1
                # time.sleep(2)
                # continue

            # Check if name was already used
            #     attempt += 1
            #     time.sleep(2)
            #     continue

            # Check if name was already used
            new_name = character_obj["fullName"]
            if new_name in used_names:
                print(f"Duplicate name '{new_name}' encountered. Retrying (attempt {attempt+1})...")
                attempt += 1
                # time.sleep(2)
                continue

            # If all checks pass, return this character
            return character_obj

        except (json.JSONDecodeError, ValueError) as e: # Catch both parsing and validation errors
            print(f"Failed to parse/validate AI output as valid JSON object (Attempt {attempt+1}/{max_attempts}): {e}")
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
            # time.sleep(5)

    # If all attempts fail, return a fallback placeholder
    print("Max attempts reached. Returning fallback character.")
    fallback_name = f"Unknown {nation} Figure {len(used_names)+1}"
    return {
        "fullName": fallback_name,
        "birthDate": "1900-01-01",
        "nationality": nation,
        "role": "Other",
        "majorContributions": ["No data"],
        "associatedEvents": [],
        "publicPerception": "Unknown",
        "legacy": "Forgotten"
    }

###############################################################################
#    BUILDING THE NOTABLE FIGURES FOR EACH NATION (PARALLELIZED)              #
###############################################################################

def generate_characters_for_nation(nation, char_count, model, schema_text, reference_year):
    """
    Worker function to generate `char_count` characters for a single nation.
    Manages its own used names set for that nation.
    """
    nation_characters = []
    used_names_for_nation = set()
    print(f"Starting character generation for {nation}...")
    for i in range(char_count):
        print(f"  Requesting character #{i+1} for {nation} (year {reference_year})...")
        char_data = fetch_single_character_from_ai(
            nation=nation,
            model=model,
            schema_text=schema_text,
            used_names=used_names_for_nation,
            reference_year=reference_year
        )
        if char_data: # Check if fallback wasn't returned or AI failed completely
            nation_characters.append(char_data)
            used_names_for_nation.add(char_data["fullName"])
        else:
            print(f"  Warning: Failed to generate character #{i+1} for {nation}.")
    print(f"Finished character generation for {nation}, generated {len(nation_characters)} characters.")
    return nation_characters


def build_notable_characters(nations, char_count, schema_text, reference_year, max_workers=10):
    """
    Generates notable characters for multiple nations in parallel.

    :param nations: List of nation names.
    :param char_count: Number of characters to generate per nation.
    :param schema_text: The schema text for the AI prompt.
    :param reference_year: The reference year for character relevance.
    :param max_workers: Maximum number of threads for parallel execution.
    :return: A list containing all generated character objects.
    """
    all_characters = []
    futures = []
    # Note: The 'model' needs to be accessible. If it's global, it's fine.
    # If not, it needs to be passed or configured within the worker/main function.
    # Assuming 'model' is configured globally or passed appropriately.

    print(f"\nStarting parallel character generation for {len(nations)} nations using up to {max_workers} workers...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for nation in nations:
            future = executor.submit(
                generate_characters_for_nation,
                nation,
                char_count,
                model, # Assumes model is accessible
                schema_text,
                reference_year
            )
            futures.append(future)

        for future in concurrent.futures.as_completed(futures):
            try:
                nation_results = future.result()
                all_characters.extend(nation_results)
                print(f"  Collected {len(nation_results)} characters from a completed thread.")
            except Exception as exc:
                print(f'!!! Thread for character generation raised an exception: {exc}')

    print(f"\n--- Parallel Character Generation Summary ---")
    print(f"Total characters generated: {len(all_characters)}")
    # Could add more summary details if needed (e.g., failures per nation)

    return all_characters


def save_notable_characters(characters, filename="notable_characters.json"):
    """
    Saves the final array of characters to a single JSON file.
    Ensures the directory structure exists before saving.
    """
    if not characters:
        print("No characters to save.")
        return
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # Save the JSON file
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(characters, f, indent=2)
    print(f"Saved {len(characters)} total characters to {filename}")

###############################################################################
#                                 MAIN SCRIPT                                 #
###############################################################################

# def main():
#     # 1) Configure the generative AI model
#     global model
#     model = configure_genai()

#     # 2) Load the schema text from a file to embed in the prompt
#     schema_text = load_schema_text("global_subschemas/notable_characters_schema.json")

#     # 3) Let the user define how many characters to generate per nation
#     char_count = 10

#     # 4) Nations for which we want to generate characters
#     nations = ["US", "UK", "USSR"]

#     # 5) The reference year (or period) for which characters should be relevant
#     reference_year = 1930  # e.g., 1930, 1950, etc.

#     # 6) Build a list of notable characters (polling one at a time)
#     characters = build_notable_characters(nations, char_count, schema_text, reference_year)

#     # 7) Save them all to a single JSON file
#     save_notable_characters(characters, filename=f"simulation_data/generated_timeline_{reference_year}/notable_characters.json")

def initialize_characters(char_count = 10,reference_year = 1965,nations = ["US", "UK", "USSR"], max_workers=100):
    """
    Initializes notable characters in parallel and saves them.
    """
    global model # Ensure model is configured and accessible globally or passed down
    model = configure_genai(model="gemini-2.0-flash", temp=0.5) # Configure the model used by threads
    schema_text = load_schema_text("global_subschemas/notable_characters_schema.json")

    print(f"Initializing {char_count} characters per nation for {len(nations)} nations (Year: {reference_year})...")
    characters = build_notable_characters(
        nations=nations,
        char_count=char_count,
        schema_text=schema_text,
        reference_year=reference_year,
        max_workers=max_workers
    )

    output_filename = f"simulation_data/generated_timeline_{reference_year}/notable_characters.json"
    save_notable_characters(characters, filename=output_filename)
    return characters

if __name__ == "__main__":
    # Example of calling the parallelized initialization
    example_nations = ["US", "UK", "USSR", "France", "West Germany", "Japan"]
    example_year = 1975
    example_char_count = 5
    example_workers = 100 # Adjust based on system/API limits

    # Call the main initialization function
    initialize_characters(
        char_count=example_char_count,
        reference_year=example_year,
        nations=example_nations,
        max_workers=example_workers
    )

    # Note: The original main() function is kept below but is no longer the primary entry point
    # if this script is run directly due to the __name__ == "__main__": block above.
    # You might want to remove or comment out the old main() if it's redundant.

    # Original main function (potentially redundant now)
    # main()
