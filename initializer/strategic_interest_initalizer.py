#!/usr/bin/env python3

import os
import json
import re # For parsing retry delay
import time
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
import concurrent.futures # Added for parallel processing
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

        except (json.JSONDecodeError, ValueError) as parse_val_err:
            print(f"Parsing or validation error (Attempt {attempt}/{max_attempts}): {parse_val_err}. Retrying...")
            if attempt == max_attempts: break
            # print("Waiting 2 seconds before retrying...")
            # time.sleep(2)
        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' fetching theatres (Attempt {attempt}/{max_attempts}): {rate_limit_error}")
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
            print(f"Unexpected error fetching theatres (Attempt {attempt}/{max_attempts}): {type(e).__name__} - {e}. Retrying...")
            if attempt == max_attempts: break
            # print("Waiting 5 seconds before retrying...")
            # time.sleep(5)

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
            raw_output = response.text.strip()
            # Clean potential markdown
            if raw_output.startswith("```json"):
                raw_output = raw_output[7:]
            if raw_output.endswith("```"):
                raw_output = raw_output[:-3]
            raw_output = raw_output.strip()

            # Parse JSON output
            interests = json.loads(raw_output) # Assume it's an array based on prompt

            # Ensure it's a list
            if not isinstance(interests, list):
                # Handle case where AI might return a single object instead of array?
                if isinstance(interests, dict):
                    print(f"  Warning: AI returned a single object for interests of '{theatre_name}', wrapping in a list.")
                    interests = [interests] # Wrap the single object in a list
                else:
                    raise ValueError("Did not return a JSON array or a single JSON object for strategic interests.")
                raise ValueError("Did not return a JSON array of strategic interests.")

            # Validate that each interest has the required fields
            for i_obj in interests:
                if "interestName" not in i_obj or "region" not in i_obj or "resourceType" not in i_obj:
                    raise ValueError(f"One interest is missing required fields: {i_obj}")

            return interests  # Success

        except json.JSONDecodeError as json_err:
            print(f"  [ERROR] Failed to parse AI output as valid JSON (Attempt {attempt}/{max_attempts}). Error: {json_err}")
            print("  Raw AI Response causing error:\n", raw_output)
            if attempt == max_attempts: break
            # print("  Waiting 2 seconds before retrying...")
            # time.sleep(2)
        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"  [ERROR] Rate limit hit for model '{model_name}' fetching interests for {theatre_name} (Attempt {attempt}/{max_attempts}): {rate_limit_error}")
            if attempt == max_attempts:
                print(f"  [FAILURE] Max retries reached for model '{model_name}' after rate limit error.")
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
            # print(f"  Waiting for {retry_delay} seconds due to rate limit...")
            # time.sleep(retry_delay)
        except Exception as e:
            print(f"  [ERROR] Unexpected issue fetching interests for {theatre_name} (Attempt {attempt}/{max_attempts}): {type(e).__name__} - {e}")
            if attempt == max_attempts: break
            # print("  Waiting 5 seconds before retrying...")
            # time.sleep(5)

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
            raw_output = response.text.strip()
             # Clean potential markdown
            if raw_output.startswith("```json"):
                raw_output = raw_output[7:]
            if raw_output.endswith("```"):
                raw_output = raw_output[:-3]
            raw_output = raw_output.strip()

            players_array = json.loads(raw_output) # Assume it's an array based on prompt

            # Ensure the response is a valid JSON array
            if not isinstance(players_array, list):
                # Handle case where AI might return a single object instead of array?
                if isinstance(players_array, dict):
                    print(f"    Warning: AI returned a single object for players of '{interest_name}', wrapping in a list.")
                    players_array = [players_array] # Wrap the single object in a list
                else:
                    raise ValueError("Did not return a JSON array or a single JSON object for major players.")
                raise ValueError("Did not return a JSON array of majorPlayers.")

            return players_array  # Successful return

        except (json.JSONDecodeError, ValueError) as e: # Catch both parsing and validation errors
            print(f"    [ERROR] Failed to parse/validate AI output as valid JSON array for players of '{interest_name}' (Attempt {attempt}/{max_attempts}): {e}")
            print(f"    Raw AI output was:\n{raw_output}") # Show the problematic output
            if attempt == max_attempts: break
            # print("    Waiting 2 seconds before retrying...")
            # time.sleep(2)
        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"    [ERROR] Rate limit hit for model '{model_name}' fetching players for {interest_name} (Attempt {attempt}/{max_attempts}): {rate_limit_error}")
            if attempt == max_attempts:
                print(f"    [FAILURE] Max retries reached for model '{model_name}' after rate limit error.")
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
            # print(f"    Waiting for {retry_delay} seconds due to rate limit...")
            # time.sleep(retry_delay)
        except Exception as e:
            print(f"    [ERROR] Unexpected issue fetching players for {interest_name} (Attempt {attempt}/{max_attempts}): {type(e).__name__} - {e}")
            if attempt == max_attempts: break
            # print("    Waiting 5 seconds before retrying...")
            # time.sleep(5)

    print(f"    [FAILURE] Could not get valid majorPlayers for '{interest_name}' after {max_attempts} attempts. Returning [].")
    return []

###############################################################################
#                            MAIN WORKFLOW / SCRIPT (PARALLELIZED)            #
###############################################################################

# Define a default number of workers
DEFAULT_MAX_WORKERS = 10

def process_theatre_interests_parallel(theatres, reference_year, model, max_workers=DEFAULT_MAX_WORKERS):
    """Fetches strategic interests for all theatres in parallel."""
    theatre_interests_map = {} # Store results mapped to theatre name/id for reconstruction
    futures = []
    print(f"\n--- Starting Parallel Fetch for Strategic Interests ({len(theatres)} theatres) ---")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for theatre in theatres:
            theatre_name = theatre.get("theatreName", "UnknownTheatre")
            future = executor.submit(fetch_strategic_interests_for_theatre, theatre, reference_year, model)
            futures.append((future, theatre_name)) # Keep track of which future belongs to which theatre

        for future, theatre_name in futures:
            try:
                interests = future.result()
                theatre_interests_map[theatre_name] = interests
                print(f"  Collected {len(interests)} interests for theatre '{theatre_name}'.")
            except Exception as exc:
                print(f"!!! Thread for theatre '{theatre_name}' interests raised an exception: {exc}")
                theatre_interests_map[theatre_name] = [] # Assign empty list on error

    # Assign fetched interests back to the original theatre objects
    all_interests_with_theatre_ref = []
    for theatre in theatres:
        theatre_name = theatre.get("theatreName", "UnknownTheatre")
        interests = theatre_interests_map.get(theatre_name, [])
        theatre["strategicInterests"] = interests
        # Also collect all interests with a reference back to their theatre for player fetching
        for interest in interests:
            all_interests_with_theatre_ref.append({"interest": interest, "theatre_name": theatre_name})

    print(f"--- Finished Fetching Strategic Interests ---")
    return theatres, all_interests_with_theatre_ref


def process_interest_players_parallel(all_interests_with_ref, reference_year, model, max_workers=DEFAULT_MAX_WORKERS):
    """Fetches major players for all interests in parallel."""
    interest_players_map = {} # Store results mapped to interest name for reconstruction
    futures = []
    print(f"\n--- Starting Parallel Fetch for Major Players ({len(all_interests_with_ref)} interests) ---")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for item in all_interests_with_ref:
            interest = item["interest"]
            interest_name = interest.get("interestName", "UnknownInterest")
            future = executor.submit(fetch_major_players_for_interest, interest, reference_year, model)
            futures.append((future, interest_name)) # Keep track of which future belongs to which interest

        for future, interest_name in futures:
            try:
                players = future.result()
                interest_players_map[interest_name] = players
                print(f"    Collected {len(players)} players for interest '{interest_name}'.")
            except Exception as exc:
                print(f"!!! Thread for interest '{interest_name}' players raised an exception: {exc}")
                interest_players_map[interest_name] = [] # Assign empty list on error

    print(f"--- Finished Fetching Major Players ---")
    return interest_players_map


def initalize_strategic_interests(reference_year = 1975, max_workers=DEFAULT_MAX_WORKERS):
    """
    Initializes strategic interests data in parallel and saves it.
    """
    # 1) Configure the AI model
    global model # Ensure model is configured and accessible globally or passed down
    # Use different models/temps for different stages if needed
    model_theatre = configure_genai(temp=0.3, model="gemini-2.0-pro-exp-02-05") # Model for initial theatre list
    model_interest = configure_genai(temp=0.45, model="gemini-2.0-flash") # Model for interests
    model_player = configure_genai(temp=0.5, model="gemini-2.0-flash") # Model for players

    # 2) Load the theatre-level schema
    schema_file = "global_subschemas/strategic_interests_schema.json"
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file '{schema_file}' not found.")
    with open(schema_file, "r", encoding="utf-8") as f:
        schema_text = f.read()

    # 3) Step One: Generate Theatres (Sequential - single AI call)
    theatres = fetch_all_theatres_basic(reference_year, model_theatre, schema_text)
    if not theatres:
        print("Error: Failed to fetch initial list of theatres. Aborting.")
        return []

    # 4) Step Two: Fetch Interests for each Theatre (Parallel)
    theatres, all_interests_with_ref = process_theatre_interests_parallel(
        theatres, reference_year, model_interest, max_workers
    )

    # 5) Step Three: Fetch Major Players for each Interest (Parallel)
    interest_players_map = process_interest_players_parallel(
        all_interests_with_ref, reference_year, model_player, max_workers
    )

    # 6) Step Four: Assign players back to their interests within the theatres structure
    print("\n--- Assigning Players back to Interests ---")
    for theatre in theatres:
        for interest in theatre.get("strategicInterests", []):
            interest_name = interest.get("interestName", "UnknownInterest")
            players = interest_players_map.get(interest_name, [])
            interest["majorPlayers"] = players
    print("--- Finished Assigning Players ---")

    # 7) Save the final data
    filename = f"simulation_data/generated_timeline_{reference_year}/global_strategic_theatres.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as out_f:
        json.dump(theatres, out_f, indent=2)

    print(f"\nGenerated {len(theatres)} theatres, with strategic interests and major players (parallelized). Sent {numRequests} Gemini API requests. Saved to {filename}.")

    return theatres

if __name__ == "__main__":
    # Example of calling the parallelized initialization
    example_year = 1975
    example_workers = 15 # Adjust based on system/API limits

    # Call the main initialization function
    initalize_strategic_interests(
        reference_year=example_year,
        max_workers=example_workers
    )

    # Note: The original main() function is removed as its logic is now in initalize_strategic_interests
