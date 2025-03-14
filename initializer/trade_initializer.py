#!/usr/bin/env python3

import os
import json
import time
import google.generativeai as genai

###############################################################################
#                           CONFIG & MODEL SETUP                              #
###############################################################################

def load_config():
    """
    Load API keys and other configurations from config.json.
    Expected JSON format, e.g.:
    {
      "GEMINI_API_KEY": "<YOUR-KEY>"
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
    Configure the generative AI model with the API key and generation settings.
    """
    config = load_config()
    genai.configure(api_key=config["GEMINI_API_KEY"])

    generation_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",  # or whichever model version you prefer
        generation_config=generation_config
    )
    return model

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
    max_attempts = 3
    while attempt < max_attempts:
        try:
            response = model.generate_content(prompt)
            raw_output = response.text.strip()[7:-3]

            
            trade_obj = json.loads(raw_output)
            print(json.dumps(trade_obj,indent=2))
            
            return trade_obj

        except json.JSONDecodeError:
            print(f"Failed to parse AI output as valid JSON. Retrying (attempt {attempt+1})...")
            attempt += 1
            time.sleep(2)

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
#                   BUILD & SAVE TRADE RELATIONS (ONE BY ONE)                 #
###############################################################################

def build_trade_relations(nations, year, schema_text):
    """
    Poll the AI for each pair of nations to generate a single trade relation,
    building a list of all relations. Returns that list.
    """
    relations = []
    relation_id_count = 1

    for i in range(len(nations)):
        for j in range(i+1, len(nations)):
            nationA = nations[i]
            nationB = nations[j]
            relation_id = f"trade-rel-{relation_id_count}"
            relation_id_count += 1

            print(f"\nRequesting AI for trade relation between {nationA} and {nationB}...")
            trade_data = fetch_trade_relation_from_ai(
                nationA, nationB, year, relation_id, schema_text, model
            )
            relations.append(trade_data)

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
    model = configure_genai()

    # 2) Load the schema text from file
    schema_text = load_trade_schema("global_subschemas/global_trade_schema.json")

    # 3) Build the trade relations array, one pair at a time
    relations = build_trade_relations(nations, year, schema_text)

    # 4) Save them to a single JSON file
    save_trade_relations(relations, filename="simulation_data/generated_timeline_1965/global_trade.json")
    
    
def initialize_trade(nations,timeline):
    global model
    model = configure_genai()
    schema_text = load_trade_schema("global_subschemas/global_trade_schema.json")
    relations = build_trade_relations(nations, timeline, schema_text)
    save_trade_relations(relations, filename=f"simulation_data/generated_timeline_{timeline}/global_trade.json")
    return relations

if __name__ == "__main__":
    main()
