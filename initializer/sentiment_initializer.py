#!/usr/bin/env python3

import os
import json
import time
import google.generativeai as genai


#GET RELEVANT EVENTS WITH A QUERYING METHOD, DON'T LEAVE IT UP TO AI

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
#                        ASKING THE AI FOR ONE RELATION                       #
###############################################################################

def fetch_relation_from_ai(nationA, nationB, model,time_period):
    """
    Polls the AI model to obtain a single JSON object representing
    the relationship between nationA and nationB, following the schema:

    {
       "nationA": "...",
       "nationB": "...",
       "diplomaticRelations": one of ["Allied","Friendly","Neutral","Tense","Hostile"],
       "economicTrust": 0-100,
       "militaryTensions": 0-100,
       "ideologicalAlignment": one of ["Identical","Similar","Neutral","Divergent","Opposed"],
       "relevantEvents": [ { "eventId": "...", "date": "YYYY-MM-DD", "impactOnRelations": "...", "notes": "..." }, ...]
    }

    Returns a dictionary. If parsing fails, it retries a few times before giving up.
    """
    prompt = f"""
You are given two nations: {nationA} and {nationB}. You will generate their relations between one another, at a given point in time: {time_period}. The relevantEvents array will only hold objects that pertain to that time or before.
Generate a strictly valid JSON object (no extra keys) matching this schema:

Required fields:
1. "nationA" (string): should be exactly "{nationA}".
2. "nationB" (string): should be exactly "{nationB}".
3. "diplomaticRelations" (enum): one of ["Allied","Friendly","Neutral","Tense","Hostile"].
4. "economicTrust" (number 0-100).
5. "militaryTensions" (number 0-100).
6. "ideologicalAlignment" (enum): one of ["Identical","Similar","Neutral","Divergent","Opposed"].
7. "relevantEvents" (array of objects) - Each event object has:
   - "eventId": string
   - "date": in YYYY-MM-DD format
   - "impactOnRelations": one of ["Minimal","Moderate","Severe","Transformational"]
   - "notes": optional freeform text

Please provide ONLY the JSON object as the final output, with no extra commentary or markdown formatting.
    """

    attempt = 0
    max_attempts = 3
    while attempt < max_attempts:
        try:
            response = model.generate_content(prompt)
            raw_output = response.text.strip()[7:-3]

            # Attempt to parse the AI's output as JSON
            relation_dict = json.loads(raw_output)

            # Validate required fields
            if not all(key in relation_dict for key in [
                "nationA", "nationB", "diplomaticRelations",
                "economicTrust", "militaryTensions", "ideologicalAlignment"
            ]):
                print(f"Missing required keys in the JSON object. Retrying (attempt {attempt+1})...")
                attempt += 1
                time.sleep(2)
                continue

            return relation_dict

        except json.JSONDecodeError:
            print(f"Failed to parse AI output as valid JSON. Retrying (attempt {attempt+1})...")
            attempt += 1
            time.sleep(2)

    # If all attempts fail, return a fallback object or None
    print("Max attempts reached. Returning a fallback object.")
    return {
        "nationA": nationA,
        "nationB": nationB,
        "diplomaticRelations": "Neutral",
        "economicTrust": 50,
        "militaryTensions": 50,
        "ideologicalAlignment": "Neutral",
        "relevantEvents": []
    }

###############################################################################
#                      MAIN SCRIPT: BUILDING THE RELATIONS                    #
###############################################################################

def build_global_sentiment(nations,time_period):
    """
    For each pair of nations (one-by-one), ask the AI for the relationship JSON.
    Collect all such relations in a list, then return it.
    """

    # Example user wants to poll in a certain order. For 3 nations [US,UK,USSR]:
    #   1) UK & USSR
    #   2) UK & US
    #   3) USSR & US
    # If you'd like a more systematic approach (like typical combos), just do a nested loop:
    #   for i in range(len(nations)):
    #       for j in range(i+1, len(nations)):
    #           ...
    
    relations = []

    # We can either follow a fixed order (like user mentioned) or systematically handle all pairs.
    # Let's do the systematic approach with nested loops, skipping same-nation pairs.
    for i in range(len(nations)):
        for j in range(i+1, len(nations)):
            nationA = nations[i]
            nationB = nations[j]

            # Poll the AI for a single relation
            print(f"\nRequesting AI for relation: {nationA} and {nationB}...")
            relation_data = fetch_relation_from_ai(nationA, nationB, model,time_period)
            relations.append(relation_data)

    return relations

def save_global_sentiment(relations, filename="global_sentiment.json"):
    """
    Saves the final array of relations to a single JSON file.
    """
    if not relations:
        print("No relations to save.")
        return

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(relations, f, indent=2)
    print(f"Saved {len(relations)} relations to {filename}")

def main():
    # Example list of nations
    nations = ["US", "UK", "USSR", "India"]

    # 1) Configure the generative AI model
    global model
    model = configure_genai()

    # 2) Build the "global sentiment" relations array
    relations = build_global_sentiment(nations,"1985")
    
    for relation in relations:
        print(json.dumps(relation, indent=2))
    # 3) Save them to a JSON file
    #save_global_sentiment(relations, filename="global_sentiment.json")
    
    
def initialize_sentiment(nations:list,filename:str,time_period:str):
    global model
    model = configure_genai()
    relations = build_global_sentiment(nations,time_period)
    save_global_sentiment(relations,filename)

if __name__ == "__main__":
    main()
