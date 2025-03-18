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

def init_nations(nations: list, start_date: str):
    """
    Calls nation_initalizer to build out each nation's internal & external affairs data.
    Saves them under 'simulation_data/Simulation_<start_date>/nations/<Country>/...'
    """
    print("\n--- Initializing Nations ---")
    try:
        nation_initalizer.nation_init_main(
            countries=nations,
            time_period=start_date
        )
    except Exception as e:
        print(f"Error calling nation_initalizer: {e}")
        sys.exit(1)
    


def apply_ramifications_to_nations(nations: list, start_date: str, global_events: list):
    """
    For each event, if it has ramifications referencing specific nations, we add them
    to that nation's 'effects'. We store these in 'nation_effects.json'.

    :param nations: The list of nation names that we have data for
    :param start_date: The simulation's start date
    :param global_events: The list of event objects
    """
    print("\n--- Adding ramifications to each nation's effects ---")
    simulation_dir = os.path.join("simulation_data", f"Simulation_{start_date}", "nations")
    nat_effects_schema_path = "nation_subschemas/internal_affairs_subschemas/national_effect_schema.json"
    try:
        with open(nat_effects_schema_path, "r", encoding="utf-8") as f:
            nat_effects_schema = json.load(f)
    except FileNotFoundError:
        print(f"Warning: {nat_effects_schema_path} not found. We'll do minimal effect records.")
        nat_effects_schema = None

    for ev in global_events:
        ramifications = ev.get("ramifications", [])
        
        event_id_label = ev.get("eventID", "NoEventID")

        for ram in ramifications:
            impacted_nations = ram.get("affectedParties", [])
            for nation_name in impacted_nations:
                nation_summary = lazy_nation_summarizer.load_and_summarize_nation(nation=nation_name,timeline=start_date)
                if nation_name not in nations:
                    continue  # skip if it's not in the chosen list
                nation_path = os.path.join(simulation_dir, nation_name)
                if not os.path.exists(nation_path):
                    print(f"Nation folder not found for {nation_name}, skipping effects insertion.")
                    continue

                effects_file = os.path.join(nation_path, "nation_effects.json")
                if not os.path.exists(effects_file):
                    existing_effects = []
                else:
                    with open(effects_file, "r", encoding="utf-8") as ef:
                        try:
                            existing_effects = json.load(ef)
                        except json.JSONDecodeError:
                            existing_effects = []
                
                effects = ramification_generator.fetch_and_save_nation_effects(ram,nation_name,nation_summary,start_date)

                existing_effects += effects
                with open(effects_file, "w", encoding="utf-8") as ef:
                    json.dump(existing_effects, ef, indent=2)
                for effect in effects:
                    print(f"Added effect to {nation_name}: {effect['ramificationType']}")

def create_simulation_directory(start_date: str) -> str:
    """
    Creates and returns the path to the simulation directory for the given start_date.
    """
    simulation_path = os.path.join("simulation_data", f"generated_timeline_{start_date}")
    os.makedirs(simulation_path, exist_ok=True)
    return simulation_path

def generate_global_sentiment(nations: list, start_date: str, simulation_path: str):
    """
    Generates a `global_sentiment.json` file containing pairwise diplomatic/economic relations
    for the provided list of nations, if more than one nation is present.
    """
    import sentiment_initializer
    return sentiment_initializer.initialize_sentiment(nations,simulation_path+"/global_sentiment.json",start_date)

def generate_global_trade(nations: list, start_date: str, simulation_path: str):
    """
    Generates a `global_trade.json` file containing pairwise trade relations
    for the provided list of nations, if more than one nation is present.
    """
    import trade_initializer
    return trade_initializer.initialize_trade(nations,start_date)
    

def generate_notable_characters(nations: list, start_date: str, char_count: int, simulation_path: str):
    """
    Generates a `notable_characters.json` file containing placeholder characters for each nation.
    """
    import notable_character_initalizer
    return notable_character_initalizer.initialize_characters(char_count=char_count,reference_year=start_date,nations=nations)
    

def generate_organizations(nations: list, start_date: str, simulation_path: str,org_count:int):
    """
    Generates an `organizations.json` file with placeholder content describing
    international or otherwise notable organizations.
    """
    
    import organizations_initializer
    return organizations_initializer.initialize_global_agreements(reference_year=start_date,allowed_nations=nations,entity_count=org_count)


def generate_strategic_interests(nations: list, start_date: str, simulation_path: str):
    """
    Generates a `strategic_interests.json` file with placeholder content describing
    strategic interests for the listed nations.
    """
    import strategic_interest_initalizer
    return strategic_interest_initalizer.initalize_strategic_interests(start_date)

def generate_global_economy(nations: list, start_date: str, simulation_path: str):
    """
    Generates a `global_economy.json` file with placeholder data about the global economy.
    """
    print("\n--- Generating global_economy.json ---")
    global_economy_path = os.path.join(simulation_path, "global_economy.json")
    global_economy_data = {
        "globalGDP": "$10 trillion",
        "stockMarketTrends": {
            "DowJones": 10000,
            "Nasdaq": 2000,
            "ShanghaiComposite": 2500,
            "EuroStoxx": 3000
        },
        "majorTradeDisputes": [],
        "globalInflationRate": 3.2
    }
    with open(global_economy_path, "w", encoding="utf-8") as gf:
        json.dump(global_economy_data, gf, indent=2)
    print("Saved global_economy.json")

def generate_global_structures(nations: list, start_date: str, char_count: int):
    """
    Orchestrates the creation of multiple global structure files.
    Calls separate helper functions for each file:
     - global_sentiment.json
     - global_trade.json
     - notable_characters.json
     - organizations.json
     - strategic_interests.json
     - global_economy.json
    """
    import trade_sentiment_initializer
    simulation_path = create_simulation_directory(start_date)

    # generate_global_sentiment(nations, start_date, simulation_path)
    # generate_global_trade(nations, start_date, simulation_path)
    #trade_sentiment_initializer.initialize_combined(nations=nations,year=start_date)
    #generate_notable_characters(nations, start_date, char_count, simulation_path)
    generate_organizations(nations, start_date, simulation_path,30)
    #generate_strategic_interests(nations, start_date, simulation_path)
    generate_global_economy(nations, start_date, simulation_path)

    print("\n=== Finished generating global structures ===")



###############################################################################
#                    3) MAIN ORCHESTRATION FUNCTION                           #
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

    start_date = 1975#input_start_date()
    lookback = 1900#input_lookback_years()
    char_count = 8#input_characters_count()

    print("\n=== Starting Global Initialization ===")
    print(f"Selected Nations: {nations}")
    print(f"Timeline Start: {start_date}")
    print(f"Lookback Years: {lookback}")
    #print(f"Characters per Nation: {char_count}")

    # 2) Initialize each nation's data
    #init_nations(nations, start_date)

    # 3) Generate major events that impacted these nations
    global_events = fetch_nation_events.fetch_and_save_nations_events(nations, lookback, start_date)

    # 4) For each event, apply ramifications to the relevant nations
    #apply_ramifications_to_nations(nations, start_date, global_events)

    # 5) Generate all the global structures (sentiment, trade, characters, organizations, etc.)
    #generate_global_structures(nations, start_date, char_count)

    print("\n=== Global Initialization Complete ===")
    print(f"Scenario data saved under 'simulation_data/Simulation_{start_date}/'.")


if __name__ == "__main__":
    main()

