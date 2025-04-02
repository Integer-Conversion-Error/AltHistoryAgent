#!/usr/bin/env python3
"""
global_initializer.py

This script orchestrates the initialization of an AI-driven alternate historical scenario.
It does the following:

1) Asks the user to:
   - Provide a list of nation names (comma-separated).
   - Provide a start date (YYYY) for the timeline initialization.
   - Provide how many years to look back for generating important events that shaped these nations.
   - Provide how many notable characters (3-5 recommended) to generate per nation.

2) Calls nation_initalizer.py to initialize the respective JSON objects for each selected nation,
   saving them (internal affairs, external affairs, etc.) in the proper structure.

3) Generates important events from the last X years (the user-chosen lookback) that impacted each chosen nation.
   - For instance, we could call generate_event.py or a custom function to produce historical events.
   - We then store those events in a top-level 'global_events' structure or sub-schemas.

4) For each event that pertains to specific countries, we add national effects to each impacted nation
   (e.g., references to the event in their 'effects' array, following national_effect_schema.json).

5) Generates or merges:
   - global sentiment array (per global_sentiment_schema.json).
   - global trade array (per global_trade_schema.json) between each of the chosen nations.
   - a set of notable characters (notable_characters_schema.json) for each nation (3-5 each).
   - organizations / global treaties from organizations_schema.json.
   - strategic interests (strategic_interests_schema.json).
   - global economy object (global_economy_schema.json).
   ... saving each item to the appropriate JSON file.

In short, this script unifies multiple steps to create a robust initial “global state” for your alternate history scenario.
"""

import os
import json
import sys
import datetime
import time
from initializer_util import *
import nation_initalizer
import fetch_nation_events
import ramification_generator
import global_economy_initializer # Import the new initializer

from writers import low_level_writer
from writers import generate_event

from summarizers import lazy_nation_summarizer


###############################################################################
#                            1) HELPER FUNCTIONS                              #
###############################################################################

def input_nations() -> list:
    """
    Prompt the user for a comma-separated list of nation names.
    Returns them as a list of trimmed strings.
    """
    print("Enter the list of nations (comma-separated), e.g. 'Germany, USA, France':")
    raw = input("Nations: ").strip()
    if not raw:
        print("No nations provided, using default example: ['Germany', 'Soviet Union']")
        return ["Germany", "Soviet Union"]
    return [n.strip() for n in raw.split(",") if n.strip()]

def input_start_date() -> str:
    """
    Prompt user for a start date (year). 
    Returns a string, e.g. "1965".
    """
    print("Enter the start year for the timeline (e.g. '1965'):")
    year = input("Start Year: ").strip()
    if not year.isdigit():
        print("Invalid input, using default '1965'")
        return "1965"
    return year

def input_lookback_years() -> int:
    """
    Prompt user for how many years to look back for generating historical events.
    Returns an integer. 
    """
    print("How many years to look back for generating major events that shaped these nations?")
    val = input("Lookback Years: ").strip()
    if not val.isdigit():
        print("Invalid input, defaulting to 10 years.")
        return 10
    return int(val)

def input_characters_count() -> int:
    """
    Prompt how many notable characters to create per nation.
    Typically 3-5 is recommended.
    """
    print("How many notable characters should be generated per nation? (e.g., 3 or 5)")
    val = input("Characters Count: ").strip()
    if not val.isdigit():
        print("Invalid input, defaulting to 3.")
        return 3
    return int(val)

###############################################################################
#                    2) MAIN FLOW: GLOBAL INITIALIZER                         #
###############################################################################

# Define a default number of workers
DEFAULT_MAX_WORKERS = 150

def init_nations(nations: list, start_date: str, max_workers: int = DEFAULT_MAX_WORKERS):
    """
    Calls nation_initalizer to build out each nation's internal & external affairs data.
    Saves them under 'simulation_data/Simulation_<start_date>/nations/<Country>/...'
    """
    print("\n--- Initializing Nations ---")
    try:
        # Pass max_workers to the parallelized nation initializer
        nation_initalizer.nation_init_main(
            countries=nations,
            time_period=start_date,
            max_workers=max_workers
        )
    except Exception as e:
        print(f"Error calling nation_initalizer: {e}")
    sys.exit(1)
    

# Removed apply_ramifications_to_nations function as this logic is now handled dynamically by EventEngine/RamificationExecutor

def create_simulation_directory(start_date: str) -> str:
    """
    Creates and returns the path to the simulation directory for the given start_date.
    """
    simulation_path = os.path.join("simulation_data", f"generated_timeline_{start_date}")
    os.makedirs(simulation_path, exist_ok=True)
    return simulation_path

def generate_global_sentiment(nations: list, start_date: str, simulation_path: str, max_workers: int = DEFAULT_MAX_WORKERS):
    """
    Generates a `global_sentiment.json` file containing pairwise diplomatic/economic relations
    for the provided list of nations, if more than one nation is present.
    """
    import sentiment_initializer
    output_file = os.path.join(simulation_path, "global_sentiment.json")
    print("\n--- Generating Global Sentiment (Parallel) ---")
    return sentiment_initializer.initialize_sentiment(
        nations=nations,
        filename=output_file,
        time_period=start_date,
        max_workers=max_workers
    )

def generate_global_trade(nations: list, start_date: str, simulation_path: str, max_workers: int = DEFAULT_MAX_WORKERS):
    """
    Generates a `global_trade.json` file containing pairwise trade relations
    for the provided list of nations, if more than one nation is present.
    """
    import trade_initializer
    output_file = os.path.join(simulation_path, "global_trade.json")
    print("\n--- Generating Global Trade (Parallel) ---")
    return trade_initializer.initialize_trade(
        nations=nations,
        timeline=start_date,
        max_workers=max_workers
        # filename is handled inside initialize_trade now
    )


def generate_notable_characters(nations: list, start_date: str, char_count: int, simulation_path: str, max_workers: int = DEFAULT_MAX_WORKERS):
    """
    Generates a `notable_characters.json` file containing characters for each nation in parallel.
    """
    import notable_character_initalizer
    output_file = os.path.join(simulation_path, "notable_characters.json")
    print("\n--- Generating Notable Characters (Parallel) ---")
    return notable_character_initalizer.initialize_characters(
        char_count=char_count,
        reference_year=start_date,
        nations=nations,
        max_workers=max_workers
        # filename is handled inside initialize_characters now
    )


def generate_organizations(nations: list, start_date: str, simulation_path: str, org_count: int):
    """
    Generates an `organizations.json` file with placeholder content describing
    international or otherwise notable organizations.
    """
    
    import organizations_initializer
    return organizations_initializer.initialize_global_agreements(reference_year=start_date,allowed_nations=nations,entity_count=org_count) # Not parallelized by nation/pair


def generate_strategic_interests(nations: list, start_date: str, simulation_path: str, max_workers: int = DEFAULT_MAX_WORKERS):
    """
    Generates a `strategic_interests.json` file by calling the parallelized initializer.
    """
    import strategic_interest_initalizer
    print("\n--- Generating Strategic Interests (Parallel Internally) ---")
    # Pass max_workers to the internally parallelized function
    return strategic_interest_initalizer.initalize_strategic_interests(
        reference_year=start_date,
        max_workers=max_workers
    )

def generate_global_economy(nations: list, start_date: str, simulation_path: str): # Not parallelized by nation/pair
    """
    Generates a `global_economy.json` file using the AI initializer.
    """
    global_economy_path = os.path.join(simulation_path, "global_economy.json")
    try:
        return global_economy_initializer.initialize_global_economy(
            nations=nations,
            reference_year=start_date,
            output_path=global_economy_path
        )
    except Exception as e:
        print(f"Error generating global economy data: {e}")
        # Decide if you want to fall back to placeholder or stop
        # For now, just print the error and continue
        return None # Indicate failure

def generate_global_structures(nations: list, start_date: str, char_count: int, max_workers: int = DEFAULT_MAX_WORKERS):
    """
    Orchestrates the creation of multiple global structure files.
    Calls separate helper functions for each file, passing max_workers where applicable.
     - global_sentiment.json (Parallel by pair)
     - global_trade.json (Parallel by pair)
     - notable_characters.json (Parallel by nation)
     - organizations.json (Sequential)
     - strategic_interests.json (Sequential)
     - global_economy.json (Sequential)
    """
    import trade_sentiment_initializer # This one handles both sentiment and trade in one go
    simulation_path = create_simulation_directory(start_date)

    print("\n--- Generating Global Structures ---")

    # Option 1: Generate Sentiment and Trade Separately (using parallelized functions)
    # generate_global_sentiment(nations, start_date, simulation_path, max_workers)
    # generate_global_trade(nations, start_date, simulation_path, max_workers)

    # Option 2: Generate Sentiment and Trade Combined (using parallelized function)
    print("\n--- Generating Combined Sentiment & Trade (Parallel by Pair) ---")
    trade_sentiment_initializer.initialize_combined(
        nations=nations,
        year=start_date,
        max_workers=max_workers
    )

    # # Generate Characters (Parallel by Nation)
    # generate_notable_characters(nations, start_date, char_count, simulation_path, max_workers)

    # Generate Organizations (Sequential)
    print("\n--- Generating Organizations (Sequential) ---")
    generate_organizations(nations, start_date, simulation_path, 30) # Assuming 30 orgs

    # Generate Strategic Interests (Parallel Internally)
    print("\n--- Generating Strategic Interests (Parallel Internally) ---")
    generate_strategic_interests(nations, start_date, simulation_path, max_workers) # Pass max_workers

    # Generate Global Economy (Sequential)
    print("\n--- Generating Global Economy (Sequential) ---")
    generate_global_economy(nations, start_date, simulation_path)

    print("\n=== Finished generating global structures ===")


###############################################################################
#           4) ASSEMBLE & SAVE FINAL GLOBAL STATE FILE                        #
###############################################################################

def assemble_and_save_global_state(start_date: str, nations_list: list):
    """
    Loads all generated component files and assembles the final global_state.json.
    """
    print("\n--- Assembling Final Global State ---")
    simulation_dir = os.path.join("simulation_data", f"generated_timeline_{start_date}")
    nations_input_dir = os.path.join(simulation_dir, "nations")
    global_state_output_path = os.path.join(simulation_dir, "global_state.json")

    global_state = {
        "current_date": f"{start_date}-01-01", # Default to Jan 1st of start year
        "nations": {}, # Nations will be a dict keyed by nationId
        "globalEvents": [],
        "effects": [],
        "ramifications": [],
        "conflicts": { # Initialize basic conflict structure if needed by event engine
             "activeWars": [], "borderSkirmishes": [], "internalUnrest": [], "proxyWars": []
        },
        # Add keys for other global structures
        "globalEconomy": {},
        "globalSentiment": [],
        "globalTrade": [],
        "notableCharacters": [],
        "organizations": [],
        "strategicInterests": []
    }

    # Load Nations
    print("Loading nation files...")
    nation_files_loaded = 0
    if os.path.isdir(nations_input_dir):
        for nation_file in os.listdir(nations_input_dir):
            if nation_file.endswith(".json"):
                nation_name_from_file = nation_file[:-5] # Get name from filename
                # Find the corresponding nation name from the input list to handle potential case differences
                matched_nation_name = next((n for n in nations_list if n.lower() == nation_name_from_file.lower()), None)
                if matched_nation_name:
                    try:
                        with open(os.path.join(nations_input_dir, nation_file), "r", encoding="utf-8") as f:
                            nation_data = json.load(f)
                            nation_id = nation_data.get("nationId") # Get ID from loaded data
                            if nation_id:
                                global_state["nations"][nation_id] = nation_data
                                nation_files_loaded += 1
                            else:
                                print(f"Warning: Missing 'nationId' in {nation_file}. Skipping.")
                    except Exception as e:
                        print(f"Error loading nation file {nation_file}: {e}")
    print(f"Loaded data for {nation_files_loaded} nations.")


    # Load Global Events
    global_events_path = os.path.join(simulation_dir, "global_events.json")
    if os.path.exists(global_events_path):
        try:
            with open(global_events_path, "r", encoding="utf-8") as f:
                global_state["globalEvents"] = json.load(f)
            print(f"Loaded {len(global_state['globalEvents'])} global events.")
        except Exception as e:
            print(f"Error loading {global_events_path}: {e}")

    # Load other global files (add error handling as needed)
    other_files = {
        "globalEconomy": "global_economy.json",
        "globalSentiment": "global_sentiment.json",
        "globalTrade": "global_trade.json",
        "notableCharacters": "notable_characters.json",
        "organizations": "global_agreements.json", # Note filename difference
        "strategicInterests": "global_strategic_theatres.json" # Note filename difference
    }

    for key, filename in other_files.items():
        file_path = os.path.join(simulation_dir, filename)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    global_state[key] = json.load(f)
                print(f"Loaded {filename}.")
            except Exception as e:
                 print(f"Error loading {filename}: {e}")
        else:
             print(f"Warning: File not found - {filename}. Initializing '{key}' as empty/default.")
             # Keep default empty list/dict initialized earlier

    # Save the assembled state
    try:
        save_json(global_state, global_state_output_path) # Use existing save_json function from initializer_util
        print(f"Successfully assembled and saved global state to {global_state_output_path}")
    except Exception as e:
        print(f"Error saving final global state: {e}")


###############################################################################
#                    5) MAIN ORCHESTRATION FUNCTION                           #
###############################################################################

def main():
    """
    The main function that orchestrates the entire global initialization:
      1) Collect user inputs
      2) Initialize each nation's data
      3) Generate major events
      4) Apply ramifications to each nation
      5) Generate global-level structures
    """
    # 1) Gather user inputs
    #nations = input_nations()
    nations = ["West Germany","East Germany", "Finland", "Soviet Union", "France", "United States of America", "United Kingdom", "Japan", "Hungary", "Turkey", "Canada", "Italy","Yugoslavia","Communist China","Taiwan (ROC)","Egypt","Poland","Spain","Portugal","Iran", "South Vietnam","North Vietnam", "South Korea", "North Korea", "Norway", "Sweden", "Saudi Arabia", "India","Pakistan", "Malaysia", "Indonesia", "South Africa", "Israel", "Singapore", "Burma", "Australia","Rhodesia"]

    start_date = input_start_date()
    lookback = input_lookback_years()
    char_count = input_characters_count()

    print("\n=== Starting Global Initialization ===")
    print(f"Selected Nations: {nations}")
    print(f"Timeline Start: {start_date}")
    print(f"Lookback Years: {lookback}")
    print(f"Characters per Nation: {char_count}")

    # 2) Initialize each nation's data (Parallel by Nation)
    init_nations(nations, start_date) 

    # 3) Generate major historical events (Parallel by Nation)
    print("\n--- Generating Historical Events (Parallel by Nation) ---")
    global_events = fetch_nation_events.fetch_and_save_nations_events(
        nations=nations,
        start_year=lookback, # Assuming lookback is the start year for events
        end_year=int(start_date), # Assuming start_date is the end year for events
        max_workers=DEFAULT_MAX_WORKERS # Added parallel worker control
    )
    # Note: The generated global_events file should be placed in the simulation_path directory if not already handled by fetch_nation_events

    # 4) Ramifications/Effects are no longer applied at initialization.

    # 5) Generate other global structures
    generate_global_structures(nations, start_date, char_count)

    # 6) Assemble and save the final global_state.json
    assemble_and_save_global_state(start_date, nations)

    print("\n=== Global Initialization Complete ===")
    # The final state file is now at simulation_data/generated_timeline_{start_date}/global_state.json

def testmain():
    """
    The main function that orchestrates the entire global initialization:
      1) Collect user inputs
      2) Initialize each nation's data
      3) Generate major events
      4) Apply ramifications to each nation
      5) Generate global-level structures
    """
    # 1) Gather user inputs
    #nations = input_nations()
    nations = ["West Germany","East Germany", "Finland", "Soviet Union", "France", "United States of America", "United Kingdom", "Japan", "Hungary", "Turkey", "Canada", "Italy","Yugoslavia","Communist China","Taiwan (ROC)","Egypt","Poland","Spain","Portugal","Iran", "South Vietnam","North Vietnam", "South Korea", "North Korea", "Norway", "Sweden", "Saudi Arabia", "India","Pakistan", "Malaysia", "Indonesia", "South Africa", "Israel", "Singapore", "Burma", "Australia","Rhodesia"]

    start_date = 1965#input_start_date()
    lookback = 1900#input_lookback_years()
    char_count = 25#input_characters_count()

    print("\n=== Starting Global Initialization ===")
    print(f"Selected Nations: {nations}")
    print(f"Timeline Start: {start_date}")
    print(f"Lookback Years: {lookback}")
    print(f"Characters per Nation: {char_count}")

    # 2) Initialize each nation's data
    init_nations(nations, start_date) # Assuming this is already parallelized

    # 3) Generate major historical events (ensure fetch_nation_events conforms to new global_event_schema)
    print("\n--- Generating Historical Events (Parallel by Nation) ---")
    global_events = fetch_nation_events.fetch_and_save_nations_events(
        nations=nations,
        start_year=lookback, # Assuming lookback is the start year for events
        end_year=int(start_date), # Assuming start_date is the end year for events
        max_workers=DEFAULT_MAX_WORKERS # Added parallel worker control
    )
    # Note: The generated global_events file should be placed in the simulation_path directory if not already handled by fetch_nation_events

    # 4) Ramifications/Effects are no longer applied at initialization.

    # 5) Generate other global structures (using internal parallelization where applicable)
    generate_global_structures(nations, start_date, char_count) # Pass worker count
    #import trade_sentiment_initializer
    #trade_sentiment_initializer.initialize_combined(nations=nations, year=start_date,max_workers=DEFAULT_MAX_WORKERS)

    # # 6) Assemble and save the final global_state.json (Sequential)
    assemble_and_save_global_state(str(start_date), nations) # Ensure start_date is string

    print("\n=== Global Initialization Complete ===")
    # The final state file is now at simulation_data/generated_timeline_{start_date}/global_state.json
    
if __name__ == "__main__":
    testmain()
