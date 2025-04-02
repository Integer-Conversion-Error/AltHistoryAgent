#!/usr/bin/env python3

import os
import json
import time
import uuid
import re # For parsing retry delay and ID validation
import random
import time # For sleep
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
from collections import defaultdict
from initializer_util import *

###############################################################################
#                      LOADING THE SCHEMA FROM A JSON FILE                    #
###############################################################################

def load_schema_text(schema_file="global_agreements_schema.json"):
    """
    Reads the entire JSON schema from a file as text.
    """
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file '{schema_file}' not found.")

    with open(schema_file, "r", encoding="utf-8") as f:
        return f.read()  # Return the raw JSON text (not parsed)

###############################################################################
#              ASKING THE AI FOR A SINGLE GLOBAL AGREEMENT/ORG                #
###############################################################################

def fetch_single_entity_from_ai(reference_year, model, schema_text, used_names, allowed_nations):
    used_names_str = ", ".join(sorted(used_names)) if used_names else "None so far"
    allowed_nations_str = ", ".join(sorted(allowed_nations))

    prompt = f"""
You are given the following JSON Schema for "Global Agreements & Organizations". Generate one item of the array shown, following the schema exactly.

{schema_text}

We are focusing on the year {reference_year}. The entity (organization or treaty) must be historically accurate and relevant at that time. 
In other words, only include states that actually existed or were internationally recognized in {reference_year} 
(e.g., do not list Soviet breakaway states before they historically formed).

Already-generated entities have the following names: {used_names_str}. 
Do not pick the entities that use these names.

The entity must include at least one member from the following nations: {allowed_nations_str}.

Create exactly ONE new entity, ensuring:
- A unique 'name' that is different from any listed above.
- Logical consistency in the attributes.
- Realism in geopolitical influence for {reference_year}.
- The 'memberStates' field must contain at least one nation from {allowed_nations_str}.

Key requirements:
1. The entity must be either an "International Organization" or a "Global Treaty".
2. It must be relevant in {reference_year}.
3. Must include required fields:
   "entityId", "entityType", "name", "formationOrSigningDate", "status",
   "memberStates", "entityCategory", "primaryObjectives", "influenceScore"
4. The organization or treaty must have an appropriate scope (e.g., military alliances, economic unions, peace treaties).
5. The 'memberStates' list must contain at least one country from: {allowed_nations_str}.
6. Ensure 'memberStates' reflect only nations recognized or in existence as of {reference_year}.
7. Output ONLY the JSON object, with no extra commentary or Markdown.

Thank you.
"""

    attempt = 0
    max_attempts = 4
    while attempt < max_attempts:
        raw_output = "" # Initialize raw_output here to avoid UnboundLocalError
        try:
            response = model.generate_content(prompt)

            # Check for safety blocks or empty parts before accessing text
            if not response.parts:
                 finish_reason = getattr(response.candidates[0], 'finish_reason', None) if response.candidates else None
                 safety_ratings = getattr(response.candidates[0], 'safety_ratings', []) if response.candidates else []
                 # Using 4 as a common value for SAFETY finish_reason, adjust if needed based on library specifics
                 if finish_reason == 4:
                     print(f"  [SAFETY] AI response blocked due to safety settings (finish_reason={finish_reason}). Skipping attempt {attempt+1}.")
                     attempt += 1
                     # time.sleep(1) # Short delay before next attempt
                     continue # Skip parsing for this attempt
                 else:
                     # Handle other cases where parts might be empty unexpectedly
                     print(f"  [ERROR] AI response has no valid parts (finish_reason={finish_reason}). Attempt {attempt+1}/{max_attempts}.")
                     # Let it fall through to the general exception handling / retry logic
                     raise ValueError("AI response has no valid parts.") # Raise specific error

            # If parts exist, try to get text (this might still raise ValueError)
            if not response.parts:
                 finish_reason = getattr(response.candidates[0], 'finish_reason', None) if response.candidates else None
                 safety_ratings = getattr(response.candidates[0], 'safety_ratings', []) if response.candidates else []
                 # Using 4 as a common value for SAFETY finish_reason, adjust if needed based on library specifics
                 if finish_reason == 4:
                     print(f"  [SAFETY] AI response blocked due to safety settings (finish_reason={finish_reason}). Skipping attempt {attempt+1}.")
                     attempt += 1
                     # time.sleep(1) # Short delay before next attempt
                     continue # Skip parsing for this attempt
                 else:
                     # Handle other cases where parts might be empty unexpectedly
                     print(f"  [ERROR] AI response has no valid parts (finish_reason={finish_reason}). Attempt {attempt+1}/{max_attempts}.")
                     # Let it fall through to the general exception handling / retry logic
                     raise ValueError("AI response has no valid parts.") # Raise specific error

            # If parts exist, try to get text (this might still raise ValueError)
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
                             print("Warning: AI returned a list with one object for organization, extracting the object.")
                             raw_json = json.dumps(temp_list[0]) # Extract the single object
                         else:
                             raise ValueError("AI returned an array, but not a single-item array of objects.")
                     except json.JSONDecodeError:
                          raise ValueError("AI returned something starting/ending with [], but couldn't parse it.")
                 else:
                    raise ValueError("AI response doesn't appear to be a JSON object.")

            # Attempt to parse the extracted JSON string
            entity_obj = json.loads(raw_json)

            # Ensure it's actually a dictionary now
            if not isinstance(entity_obj, dict):
                raise ValueError("Parsed JSON is not a dictionary object.")

            new_name = entity_obj.get("name", f"UnnamedEntity_{attempt}") # Use get for safety
            if new_name in used_names:
                print(f"Duplicate name '{new_name}' encountered. Retrying (attempt {attempt+1})...")
                attempt += 1
                # time.sleep(2)
                continue

            # 1) Simple direct membership check
            if any(member in allowed_nations for member in entity_obj["memberStates"]):
                # If direct membership check passes, we proceed
                print(f"Entity '{new_name}' includes an allowed nation via direct match.")
            else:
                # 2) If direct check fails, do advanced AI verification
                #    This tries each allowed nation individually
                advanced_match_found = False
                for nation in allowed_nations:
                    ai_result = verify_nation_with_ai(nation, entity_obj["memberStates"], model)
                    if ai_result["response"]:
                        # If AI says we have a match for this nation
                        print(f"AI verification: '{nation}' was matched via {ai_result['matchedItem']}.")
                        advanced_match_found = True
                        break

                if not advanced_match_found:
                    print(f"Entity '{new_name}' does not include required nations (advanced check). Retrying (attempt {attempt+1})...")
                    attempt += 1
                    # time.sleep(2)
                    continue

            # Add a unique entity ID (if missing)
            if "entityId" not in entity_obj:
                entity_obj["entityId"] = str(uuid.uuid4())

            return entity_obj

        except (json.JSONDecodeError, ValueError) as e: # Catch parsing, validation, and potential response.text errors
            print(f"Failed to parse/validate AI output as valid JSON object for organization (Attempt {attempt+1}/{max_attempts}): {e}")
            # Only print raw_output if it was successfully assigned
            if raw_output:
                print(f"Raw AI output was:\n{raw_output}")
            else:
                print("Raw AI output was empty or inaccessible.") # Indicate if raw_output couldn't be read
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

    # Fallback placeholder
    print("Max attempts reached. Returning fallback entity.")
    fallback_name = f"Unknown Entity {len(used_names)+1}"
    return {
        "entityId": str(uuid.uuid4()),
        "entityType": "International Organization",
        "name": fallback_name,
        "formationOrSigningDate": "1900-01-01",
        "status": "Active",
        "memberStates": [allowed_nations[0]] if allowed_nations else ["Unknown"],
        "entityCategory": "Political",
        "primaryObjectives": ["Unknown"],
        "influenceScore": 50
    }




def validate_and_correct_entity_ids(entities:list):
    """
    Ensures that each entity's 'entityId' is correctly formatted and unique.

    - Correct format: 'EID-XXXX' where XXXX is a 4-digit integer, e.g. 'EID-1032'
    - If an entity's ID is missing, malformed, or conflicts with another ID in the list,
      a new valid ID is automatically assigned.
    - Updates are performed in place.
    """

    used_ids = set()
    proper_pattern = re.compile(r"^EID-\d{4}$")
    
    for entity in entities:
        original_id = entity.get("entityId", "")
        
        # We decide if this entityId is invalid if:
        # 1) It doesn't match the 'EID-####' pattern
        # 2) It's already used by another entity
        if (not proper_pattern.match(original_id)) or (original_id in used_ids):
            # Generate a new ID that isn't in used_ids
            new_id = None
            while not new_id or new_id in used_ids:
                # Create something like 'EID-1234'
                new_id = f"EID-{random.randint(1000, 9999)}"
            entity["entityId"] = new_id
        
        used_ids.add(entity["entityId"])

    
def verify_nation_with_ai(nation, member_states, model):
    """
    Asks the AI whether 'nation' is effectively represented by
    any item in 'member_states'. Some items may be shorthand or alternate
    names for the given nation.

    The AI should respond with a JSON object:
    {
        "response": "Yes" or "No",
        "rationale": "...",
        "matchedItem": "...",   # the actual memberState that the AI thinks maps to 'nation'
    }
    """

    # Make a single string of the member states for prompt clarity
    member_states_str = ", ".join(member_states)

    prompt = f"""
We have a country named "{nation}", and a list of member states: [{member_states_str}].
Some items in the list might be shorthand or alternate names for "{nation}".
Please decide if one of these items corresponds to "{nation}" in an alternate or partial way.

Output ONLY a valid JSON object with fields:
  "response": "Yes" or "No"
  "rationale": (a short sentence explaining why or why not)
  "matchedItem": (the actual item from the list you think refers to "{nation}", or "" if none)

Examples:
If "GB" is in the list and you believe "GB" refers to the "UK",
you might respond:
{{
  "response": true,
  "rationale": "GB stands for Great Britain, which includes the UK.",
  "matchedItem": "GB"
}}

If you find no suitable match, respond:
{{
  "response": false,
  "rationale": "None of the items in the list map to '{nation}'.",
  "matchedItem": ""
}}
    """

    # Call the model
    response = model.generate_content(prompt)
    raw_output = response.text.strip()

    # Parse the output
    try:
        ai_answer = json.loads(raw_output)
        # Ensure it has the necessary keys; if not, fix or handle gracefully
        if not all(k in ai_answer for k in ("response", "rationale", "matchedItem")):
            raise ValueError("AI response missing required keys.")
        return ai_answer
    except (json.JSONDecodeError, ValueError) as e:
        # If parsing fails or the AI didn't follow instructions, we decide how to handle it
        print(f"AI verification failed for nation={nation}. Reason: {e}")
        return {
            "response": "No",
            "rationale": "AI output was invalid JSON or missing keys.",
            "matchedItem": ""
        }


###############################################################################
#         BUILDING A SINGLE LIST OF ENTITIES FOR THE ALLOWED NATIONS          #
###############################################################################

def build_global_agreements(entity_count, schema_text, reference_year, allowed_nations):
    """
    Generates 'entity_count' total global agreements/organizations for a given year,
    ensuring at least one of the 'allowed_nations' is in each entity's memberStates.
    """
    
    
    all_entities = []
    used_names_set = set()

    for i in range(entity_count):
        print(f"\nRequesting AI for global entity #{i+1} (year {reference_year})...")
        entity_data = fetch_single_entity_from_ai(
            reference_year=reference_year,
            model=model,
            schema_text=schema_text,
            used_names=used_names_set,
            allowed_nations=allowed_nations
        )
        
        print(json.dumps(entity_data,indent=2))
        all_entities.append(entity_data)
        used_names_set.add(entity_data["name"])
    validate_and_correct_entity_ids(all_entities)
    return all_entities

###############################################################################
#                       SAVING THE GENERATED DATA                              #
###############################################################################

def save_global_agreements(entities, filename="global_agreements.json"):
    """
    Saves the final array of global agreements & organizations to a JSON file.
    Ensures the directory structure exists before saving.
    """
    if not entities:
        print("No entities to save.")
        return
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    # Save the JSON file
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(entities, f, indent=2)
    print(f"Saved {len(entities)} total entities to {filename}")

###############################################################################
#                                 MAIN SCRIPT                                 #
###############################################################################

def main():
    # 1) Configure the generative AI model
    global model
    model = configure_genai()

    # 2) Load the schema text from a file to embed in the prompt
    schema_text = load_schema_text("global_subschemas/organizations_schema.json")

    # 3) Define parameters
    entity_count = 30
    reference_year = 1975
    allowed_nations = ["US", "UK", "USSR"]

    # 4) Build a single list of global agreements & organizations 
    # that must include at least one of the allowed nations.
    entities = build_global_agreements(entity_count, schema_text, reference_year, allowed_nations)

    # 5) Save them all to a single JSON file
    save_global_agreements(entities, filename=f"simulation_data/generated_timeline_{reference_year}/global_agreements.json")

def initialize_global_agreements(entity_count=10, reference_year=1975, allowed_nations=None):
    """
    A wrapper function to initialize data without running the script from CLI.
    Pass in a list of 'allowed_nations' to ensure each entity has at least one of those members.
    """
    if allowed_nations is None:
        allowed_nations = ["US", "UK", "USSR"]

    global model
    model = configure_genai(model="gemini-2.0-flash")
    schema_text = load_schema_text("global_subschemas/organizations_schema.json")
    entities = build_global_agreements(entity_count, schema_text, reference_year, allowed_nations)
    save_global_agreements(entities, filename=f"simulation_data/generated_timeline_{reference_year}/global_agreements.json")
    return entities

if __name__ == "__main__":
    main()
