#!/usr/bin/env python3

import os
import json
import re # For parsing retry delay
import time
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions

###############################################################################
#                           1) Configuration & Setup                          #
###############################################################################

def load_config():
    """
    Load API keys and other configurations from config.json.
    """
    config_path = "config.json"
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"{config_path} not found. Please create the file with the necessary configurations."
        )
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)

def configure_genai():
    """
    Configure the generative AI model with API key and settings.
    """
    config = load_config()
    genai.configure(api_key=config["GEMINI_API_KEY"])

    generation_config = {
        "temperature": 0.8,  # Balanced randomness
        "top_p": 0.95,
        "top_k": 40
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
    )
    return model

###############################################################################
#                        2) Prompt & JSON Generation                          #
###############################################################################

def generate_global_event_prompt(json_schema: dict, action: str, context: str) -> str:
    """
    Create a structured AI prompt for building a single event array that conforms
    to 'global_event_schema'. The output must be valid JSON with exactly one item
    in the array.
    """
    return f"""
    You are an expert in generating structured JSON data for an alternate history timeline, or a real historical timeline.
    If it is a real historical timeline event, then this will be clarified in the Additional context part below, and you will take real historical information, being careful to get factual information only
    Your task is to produce a **single array** containing exactly **one** event object, 
    strictly following this schema:

    {json.dumps(json_schema, indent=2).replace('{', '{{').replace('}', '}}')}

    Action to perform: {action}

    Additional context:
    {context}

    Output only valid JSON (no extra text). The array must contain exactly one item
    that meets the requirements. 
    Ensure all required fields are present and logically consistent with the scenario.
    """

def generate_global_event_json(model, json_schema, action, context, max_retries=3, retry_delay=5):
    """
    Use AI to generate a single-event array following 'global_event_schema'.
    """
    prompt = generate_global_event_prompt(json_schema, action, context)

    for attempt in range(max_retries):
        try:
            start_time = time.time()
            response = model.generate_content(prompt)
            end_time = time.time() - start_time
            print(f"AI generation took {end_time:.2f}s")

            # Optional: ensure a minimum wait time (if desired) to avoid rate-limit or timing issues
            # if end_time < 6:
                # wait_extra = 7.2 - end_time
                # time.sleep(wait_extra)
                # print(f"Added wait time: {wait_extra:.2f}s")

            # Apply the requested slicing directly
            raw_json_text = response.text.strip()[7:-3]
            event_data = json.loads(raw_json_text)  # Expect an array with one item

            # Basic validation: Must be an array of length 1
            if not isinstance(event_data, list) or len(event_data) != 1:
                raise ValueError("Output must be an array with exactly one object.")

            return event_data  # e.g. [ { "eventType": "...", "eventData": {...} } ]

        except (json.JSONDecodeError, ValueError) as e: # Catch both parsing and validation errors
            print(f"Invalid or incomplete JSON after slicing (Attempt {attempt + 1}/{max_retries}): {e}")
            # Print the sliced text that failed parsing
            print("Sliced text causing error:\n", raw_json_text)
            if attempt == max_retries - 1: break
            # print(f"Waiting {retry_delay} seconds before retrying...")
            # time.sleep(retry_delay)
        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' (Attempt {attempt + 1}/{max_retries}): {rate_limit_error}")
            if attempt == max_retries - 1:
                print(f"Max retries reached for model '{model_name}' after rate limit error.")
                break
            # Try to parse retry delay
            current_retry_delay = 60 # Default delay
            error_message = str(rate_limit_error)
            match = re.search(r'retry_delay.*?seconds:\s*(\d+)', error_message, re.IGNORECASE)
            if hasattr(rate_limit_error, 'metadata'):
                 metadata = getattr(rate_limit_error, 'metadata', {})
                 if isinstance(metadata, dict) and 'retryInfo' in metadata and 'retryDelay' in metadata['retryInfo']:
                     delay_str = metadata['retryInfo']['retryDelay'].get('seconds', '0')
                     if delay_str.isdigit():
                         current_retry_delay = int(delay_str)
            elif match:
                 current_retry_delay = int(match.group(1))
            # print(f"Waiting for {current_retry_delay} seconds due to rate limit...")
            # time.sleep(current_retry_delay)
        except Exception as e:
            print(f"Unexpected error (Attempt {attempt + 1}/{max_retries}): {type(e).__name__} - {e}")
            if attempt == max_retries - 1: break
            # print(f"Waiting {retry_delay} seconds before retrying...") # Use default delay for general errors
            # time.sleep(retry_delay)

    # If loop finishes without returning
    print("Maximum retries reached. Returning None.")
    return None

###############################################################################
#                           3) Main Demo / Usage                               #
###############################################################################

def main():
    # 1) Configure the model
    model = configure_genai()

    # 2) Load the schema from file
    schema_path = "global_subschemas/global_event_schema.json"
    if not os.path.exists(schema_path):
        print(f"Error: {schema_path} not found.")
        return

    with open(schema_path, "r", encoding="utf-8") as f:
        global_event_schema = json.load(f)

    # 3) Provide the user action and context
    action = "Create a single 'Political Event' focusing on a new international treaty in 1980."
    context = (
        "Several nations gathered to sign a groundbreaking treaty on climate cooperation. "
        "They have different stances on carbon emissions but found common ground under political pressures. "
        # "Ensure the 'eventType' is 'Political Event' and 'eventData' references the relevant sub-schema. "
        # "The sub-schema for 'Political Event' typically includes fields such as eventId, date, location, "
        # "keyFigures, causes, and so forth. Provide enough detail to reflect the scenario logically."
    )

    # 4) Generate the event
    event_array = generate_global_event_json(model, global_event_schema, action, context)
    if event_array:
        print("\n--- Generated Global Event Array (Single Item) ---")
        print(json.dumps(event_array, indent=2))
    else:
        print("Failed to generate a valid single-event array after multiple attempts.")

if __name__ == "__main__":
    main()
