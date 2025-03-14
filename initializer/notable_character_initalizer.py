#!/usr/bin/env python3

import os
import json
import time
import google.generativeai as genai
from collections import defaultdict

###############################################################################
#                           CONFIG & MODEL SETUP                              #
###############################################################################

def load_config():
    """
    Load API keys and other configurations from config.json.
    You need a file named 'config.json' in the same directory, e.g.:
    {
        "GEMINI_API_KEY": "<your-key-here>"
    }
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
        "temperature": 0.7,    # Balanced randomness
        "top_p": 0.95,
        "top_k": 40
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",  # or whichever model you've configured
        generation_config=generation_config
    )
    return model

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

Already-generated characters for {nation} have the following names: {used_names_str}.
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
7. Focus on politically relevant people, like politicians, leaders of movements, major business leaders, figureheads etc.

Thank you.
    """

    attempt = 0
    max_attempts = 4  # We'll give extra attempts in case the AI duplicates or fails
    while attempt < max_attempts:
        try:
            response = model.generate_content(prompt)
            raw_output = response.text.strip()[7:-3]

            # Attempt to parse the AI's output as JSON
            character_obj = json.loads(raw_output)
            
            print(json.dumps(character_obj,indent=2))
            # Check nationality
            # if character_obj["nationality"] != nation:
            #     print(f"Character nationality mismatch. Retrying (attempt {attempt+1})...")
            #     attempt += 1
            #     time.sleep(2)
            #     continue

            # Check if name was already used
            new_name = character_obj["fullName"]
            if new_name in used_names:
                print(f"Duplicate name '{new_name}' encountered. Retrying (attempt {attempt+1})...")
                attempt += 1
                time.sleep(2)
                continue

            # If all checks pass, return this character
            return character_obj

        except json.JSONDecodeError:
            print(f"Failed to parse AI output as valid JSON. Retrying (attempt {attempt+1})...")
            attempt += 1
            time.sleep(2)
            
        except Exception as e:
            print(f"Encountered error {e}, retrying in 2s")
            time.sleep(2)

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
#    BUILDING THE NOTABLE FIGURES FOR EACH NATION (POLLING ONE AT A TIME)     #
###############################################################################

def build_notable_characters(nations, char_count, schema_text, reference_year):
    """
    For each nation, polls the AI `char_count` times to get distinct
    historical figures in valid JSON, referencing the loaded `schema_text`,
    ensuring no duplicate names, and making them relevant to `reference_year`.
    """
    all_characters = []
    from collections import defaultdict
    used_names_dict = defaultdict(set)

    for nation in nations:
        for _ in range(char_count):
            print(f"\nRequesting AI for a new unique character from {nation} (year {reference_year})...")
            char_data = fetch_single_character_from_ai(
                nation=nation,
                model=model,
                schema_text=schema_text,
                used_names=used_names_dict[nation],
                reference_year=reference_year
            )
            # Add to final list & mark the name as used
            all_characters.append(char_data)
            used_names_dict[nation].add(char_data["fullName"])

    return all_characters

def save_notable_characters(characters, filename="notable_characters.json"):
    """
    Saves the final array of characters to a single JSON file.
    """
    if not characters:
        print("No characters to save.")
        return

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(characters, f, indent=2)
    print(f"Saved {len(characters)} total characters to {filename}")

###############################################################################
#                                 MAIN SCRIPT                                 #
###############################################################################

def main():
    # 1) Configure the generative AI model
    global model
    model = configure_genai()

    # 2) Load the schema text from a file to embed in the prompt
    schema_text = load_schema_text("global_subschemas/notable_characters_schema.json")

    # 3) Let the user define how many characters to generate per nation
    char_count = 10

    # 4) Nations for which we want to generate characters
    nations = ["US", "UK", "USSR"]

    # 5) The reference year (or period) for which characters should be relevant
    reference_year = 1930  # e.g., 1930, 1950, etc.

    # 6) Build a list of notable characters (polling one at a time)
    characters = build_notable_characters(nations, char_count, schema_text, reference_year)

    # 7) Save them all to a single JSON file
    save_notable_characters(characters, filename=f"simulation_data/generated_timeline_{reference_year}/notable_characters.json")

if __name__ == "__main__":
    main()
