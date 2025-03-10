#!/usr/bin/env python3

import os
import json
import time
import google.generativeai as genai

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
        model_name="gemini-2.0-flash-exp",
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
    You are an expert in generating structured JSON data for an alternate history or scenario.
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
            if end_time < 6:
                wait_extra = 7.2 - end_time
                time.sleep(wait_extra)
                print(f"Added wait time: {wait_extra:.2f}s")

            # Attempt to parse the AI response as JSON
            text = response.text.strip()[7:-3]
            event_data = json.loads(text)  # Expect an array with one item

            # Basic validation: Must be an array of length 1
            if not isinstance(event_data, list) or len(event_data) != 1:
                raise ValueError("Output must be an array with exactly one object.")

            return event_data  # e.g. [ { "eventType": "...", "eventData": {...} } ]

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Invalid or incomplete JSON: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        if attempt < max_retries - 1:
            print(f"Retrying in {retry_delay} seconds... (Attempt {attempt + 2}/{max_retries})")
            time.sleep(retry_delay)
        else:
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
