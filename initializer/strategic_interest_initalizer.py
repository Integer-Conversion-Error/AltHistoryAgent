#!/usr/bin/env python3

import os
import json
import time
import google.generativeai as genai
from initializer_util import *

numRequests = 0
###############################################################################
#                              STEP 1: THEATRES                               #
###############################################################################

def fetch_all_theatres_basic(reference_year, model, schema_text):
    """
    Prompts the AI to generate a JSON array of theatres, each with
    NO strategic interests (i.e., "strategicInterests": []) so we can fill them later.

    Example prompt approach:
    1) We reference the theatre schema but instruct the AI to keep 'strategicInterests' empty.
    2) We keep retries in case of invalid JSON or parse errors.
    """

    prompt = f"""
        You are given the following JSON Schema for "Global Strategic Theatres" (including strategicInterests, etc.).
        However, we only want you to fill in the theatre-level fields (like theatreName, theatreRegion, etc.)
        and set "strategicInterests": [] for now. We will fill those later.

        Generate a SINGLE JSON array of ALL major strategic theatres relevant to the year {reference_year}. Make sure to be exhaustive and complete, getting EVERY SINGLE strategic theatre. DO NOT LEAVE OUT ANY STRATEGIC THEATRES. 
        Do NOT include any strategic interests. That is, each theatre object should have "strategicInterests": [].

        Return only valid JSON, no extra text. Follow the schema except for leaving the interests empty.

        Schema:
        {schema_text}
    """
    global numRequests
    model = configure_genai(model="gemini-2.0-pro-exp-02-05",temp=0.3)
    max_attempts = 3
    print(f"[AI] Fetch theatres (no interests yet)...")
    for attempt in range(1, max_attempts + 1):
        #print(f"[AI] Fetch theatres (no interests yet)...")
        try:
            response = model.generate_content(prompt)
            numRequests += 1
            raw_output = response.text.strip()[7:-3]
            theatres = json.loads(raw_output)
            print(json.dumps(theatres,indent=2))

            if not isinstance(theatres, list):
                raise ValueError("Top-level structure is not a JSON array.")

            # Validate each theatre has "strategicInterests": []
            for t in theatres:
                if "strategicInterests" not in t or t["strategicInterests"] != []:
                    raise ValueError("One of the theatres included strategicInterests != [].")

            return theatres

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Parsing or validation error: {e}. Retrying...")
            time.sleep(2)

    print("Failed to get valid theatres with empty interests. Returning empty list.")
    return []

###############################################################################
#                      STEP 2: STRATEGIC INTERESTS PER THEATRE               #
###############################################################################

def fetch_strategic_interests_for_theatre(theatre, reference_year, model):
    """
    Given a single 'theatre' dict with no strategic interests,
    ask the AI to produce an array of strategic interests for it.

    Implements:
    - AI rate limiting handling (wait 2s on rate limits)
    - JSON parsing & validation
    - Multiple retry attempts (5 max)
    """
    global numRequests
    theatre_name = theatre.get("theatreName", "Unknown Theatre")
    theatre_region = theatre.get("theatreRegion", "Unknown Region")

    prompt = f"""
        We have a strategic theatre called '{theatre_name}', located in '{theatre_region}', relevant to the year {reference_year}. Nothing past {reference_year} should be included.

        Please generate a JSON array of **all** strategic interests for this theatre. It is **essential** that you do not exclude or overlook **any** strategic interest relevant to the year {reference_year}. Each interest **must** follow the schema for a 'Global Strategic Interest' object, but do **not** include 'majorPlayers' yet (those will be added later).

        Make sure every significant resource-based, economic, military, or geopolitical interest is included. Provide **strictly valid** JSON, with **no additional commentary** or text beyond the final array.

        Output ONLY a JSON array of interest objects. No commentary.

        Some guidelines:
        - Make them historically plausible for {reference_year}.
        - Include controllingEntities / rivalClaims if relevant.
        - Follow the required fields of a strategic interest:
        "interestName", "region", "resourceType", "importanceLevel",
        "controllingEntities", etc.

        Return strictly valid JSON, no extra text.
    """

    max_attempts = 5  # More attempts to handle API failures
    attempt = 0
    print(f"  [AI] Fetch interests for theatre '{theatre_name}'...")
    while attempt < max_attempts:
        attempt += 1
        

        try:
            response = model.generate_content(prompt)
            numRequests += 1
            raw_output = response.text.strip()[7:-3]

            # Handle rate limiting
            if "rate limit" in raw_output.lower() or "too many requests" in raw_output.lower():
                print("  [WARNING] Rate limit encountered. Waiting 2 seconds before retrying...")
                time.sleep(2)
                continue  # Retry after waiting

            # Parse JSON output
            interests = json.loads(raw_output)

            # Ensure it's a list
            if not isinstance(interests, list):
                raise ValueError("Did not return a JSON array of strategic interests.")

            # Validate that each interest has the required fields
            for i_obj in interests:
                if "interestName" not in i_obj or "region" not in i_obj or "resourceType" not in i_obj:
                    raise ValueError(f"One interest is missing required fields: {i_obj}")

            return interests  # Success

        except json.JSONDecodeError:
            print(f"  [ERROR] Failed to parse AI output as valid JSON. Retrying in 2 seconds...")
            time.sleep(2)

        except Exception as e:
            print(f"  [ERROR] Unexpected issue: {e}. Retrying in 2 seconds...")
            time.sleep(2)

    print(f"  [FAILURE] Could not get valid strategic interests for theatre '{theatre_name}' after {max_attempts} attempts. Returning [].")
    return []

###############################################################################
#               STEP 3: MAJOR PLAYERS PER STRATEGIC INTEREST                 #
###############################################################################

def fetch_major_players_for_interest(interest, reference_year, model):
    """
    Given a strategic interest object with controllingEntities / rivalClaims,
    produce 'majorPlayers' for each unique entity by calling the AI to
    generate a single array of majorPlayers (with fields 'entityName', 'aims', etc.).

    Implements error handling for rate limits and parsing failures.
    """
    global numRequests  
    # Collect unique entities from controllingEntities & rivalClaims
    controlling = interest.get("controllingEntities", [])
    rivals = interest.get("rivalClaims", [])
    all_entities = sorted(set(controlling + rivals))

    # If there are no involved entities, we return an empty list
    if not all_entities:
        return []

    interest_name = interest.get("interestName", "Unknown Interest")
    
    prompt = f"""
        We have a strategic interest named '{interest_name}', relevant to the year {reference_year}. Nothing past the year {reference_year} should be included.
        It involves these entities: {all_entities}.
        For each involved entity, create an entry in a JSON array 'majorPlayers', describing:
        "entityName": the name, (should be a real nation, organization, or alliance)
        "aims": an array of specific goals,
        "levelOfInfluence": one of ["Dominant","High","Moderate","Low","Marginal","Emerging","Declining","Contested"],
        "meansOfInfluence": e.g. ["Military", "Diplomatic", "Economic"],
        "conflictPotential": ["Low","Moderate","High"]

        Output ONLY the JSON array. Each item corresponds to one entity from the list.
    """

    max_attempts = 15  # Increase attempts to allow for rate-limiting retries
    attempt = 0
    print(f"    [AI] Get majorPlayers for '{interest_name}'...")
    while attempt < max_attempts:
        attempt += 1
        #print(f"    [AI] Attempt {attempt}/{max_attempts} to get majorPlayers for '{interest_name}'...")

        try:
            response = model.generate_content(prompt)
            numRequests += 1
            raw_output = response.text.strip()[7:-3]

            # Check for rate limiting error in response
            if "rate limit" in raw_output.lower() or "too many requests" in raw_output.lower():
                #print("    [WARNING] Rate limit encountered. Waiting 2 seconds before retrying...")
                time.sleep(2)
                continue  # Retry after waiting

            players_array = json.loads(raw_output)

            # Ensure the response is a valid JSON array
            if not isinstance(players_array, list):
                raise ValueError("Did not return a JSON array of majorPlayers.")

            return players_array  # Successful return

        except json.JSONDecodeError:
            #print(f"    [ERROR] Failed to parse AI output as valid JSON. Retrying in 2 seconds...")
            time.sleep(2)

        except Exception as e:
            #print(f"    [ERROR] Unexpected issue: {e}. Retrying in 2 seconds...")
            time.sleep(2)

    print(f"    [FAILURE] Could not get valid majorPlayers for '{interest_name}' after {max_attempts} attempts. Returning [].")
    return []

###############################################################################
#                            MAIN WORKFLOW / SCRIPT                           #
###############################################################################

def main():
    # 1) Configure the AI model
    global model
    model = configure_genai(temp=0.45, model="gemini-2.0-flash")

    # 2) Load the theatre-level schema
    schema_file = "global_subschemas/strategic_interests_schema.json"
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file '{schema_file}' not found.")
    with open(schema_file, "r", encoding="utf-8") as f:
        schema_text = f.read()

    # 3) Decide the year
    reference_year = 1975

    # 4) Step One: Generate Theatres (with empty strategicInterests)
    theatres = fetch_all_theatres_basic(reference_year, model, schema_text)

    # 5) Step Two: For each theatre, generate a list of strategicInterests
    for theatre in theatres:
        interests = fetch_strategic_interests_for_theatre(theatre, reference_year, model)
        theatre["strategicInterests"] = interests  # fill them in

        # 6) Step Three: For each interest, generate 'majorPlayers'
        for interest in theatre["strategicInterests"]:
            major_players = fetch_major_players_for_interest(interest, reference_year, model)
            interest["majorPlayers"] = major_players
    
    # 7) Save the final data
    filename = f"simulation_data/generated_timeline_{reference_year}/global_strategic_theatres.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as out_f:
        json.dump(theatres, out_f, indent=2)

    print(f"\nGenerated {len(theatres)} theatres, with strategic interests and major players. Sent {numRequests} Gemini API requests. Saved to {filename}.")
    
    
def initalize_strategic_interests(reference_year = 1975):
    # 1) Configure the AI model
    global model
    model = configure_genai(temp=0.45, model="gemini-2.0-flash-exp")

    # 2) Load the theatre-level schema
    schema_file = "global_subschemas/strategic_interests_schema.json"
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file '{schema_file}' not found.")
    with open(schema_file, "r", encoding="utf-8") as f:
        schema_text = f.read()

    # 3) Decide the year
    

    # 4) Step One: Generate Theatres (with empty strategicInterests)
    theatres = fetch_all_theatres_basic(reference_year, model, schema_text)

    # 5) Step Two: For each theatre, generate a list of strategicInterests
    for theatre in theatres:
        interests = fetch_strategic_interests_for_theatre(theatre, reference_year, model)
        theatre["strategicInterests"] = interests  # fill them in

        # 6) Step Three: For each interest, generate 'majorPlayers'
        for interest in theatre["strategicInterests"]:
            major_players = fetch_major_players_for_interest(interest, reference_year, model)
            interest["majorPlayers"] = major_players
    
    # 7) Save the final data
    filename = f"simulation_data/generated_timeline_{reference_year}/global_strategic_theatres.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as out_f:
        json.dump(theatres, out_f, indent=2)
    
    print(f"\nGenerated {len(theatres)} theatres, with strategic interests and major players. Sent {numRequests} Gemini API requests. Saved to {filename}.")

    return theatres
if __name__ == "__main__":
    import os
    main()
