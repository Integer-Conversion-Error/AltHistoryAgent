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

# We assume you have these modules available:
# - nation_initalizer.py (with a main function or a known function called nation_init_main)
# - generate_event.py or other references for event creation
# - some produce_structured_data logic in low_level_writer.py
# Adjust imports based on your actual code structure:

try:
    import nation_initalizer
except ImportError:
    print("Error: Could not import 'nation_initalizer'. Check file structure or naming.")
    sys.exit(1)

try:
    from writers import low_level_writer
except ImportError:
    print("Error: Could not import 'low_level_writer' from 'writers'. Check file structure.")
    sys.exit(1)

try:
    from writers import generate_event
except ImportError:
    print("Warning: Could not import 'generate_event'. We'll placeholder event generation calls.")

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
        
        
def fetch_nation_events_brief(model, nation_name: str, start_year: int, end_year: int) -> list:
    """
    Asks the AI model for a simplified JSON array of important events in which 'nation_name' was involved,
    during the time period [start_year, end_year]. Each event in the array should only include:
    
    [
      {
        "date": "YYYY-MM-DD",
        "title": "Short title of the event",
        "description": "Brief explanation of the event"
      },
      ...
    ]

    :param model: A configured generative AI model (e.g. from configure_genai()).
    :param nation_name: The nation for which we want to gather historical events.
    :param start_year: The earliest year (inclusive) to look for events.
    :param end_year: The latest year (inclusive) to look for events.
    :return: A Python list of dictionaries, each with keys "date", "title", and "description".
             Returns an empty list if parsing fails or if the AI does not produce the desired format.
    """
    
    # 1) Build a prompt instructing the AI to produce a JSON array 
    #    with the minimal keys: date, title, description.
    prompt = f"""
    You are an expert historian. Provide a valid JSON array of important events 
    involving '{nation_name}' between {start_year} and {end_year}. 
    Each event object in the array must ONLY include these keys:
      "date" (in YYYY-MM-DD format),
      "title" (short name of the event),
      "description" (a concise explanation, no more than two sentences).

    The final output must be strictly valid JSON containing only an array of objects, 
    with no extra text or explanation. Do not wrap in quotes or add extra fields.
    """
    
    # 2) Send the prompt to the AI model and collect the response
    response = model.generate_content(prompt)
    
    # 3) Try parsing the AI response as JSON. 
    #    We expect a top-level array containing {date, title, description} objects.
    try:
        raw_output = response.text.strip()
        parsed_events = json.loads(raw_output)
        
        # Validate that it's a list of objects with the required keys
        if not isinstance(parsed_events, list):
            print("AI did not return a JSON array. Returning empty list.")
            return []
        
        # Optional: further check each item for date/title/description
        valid_events = []
        for ev in parsed_events:
            if (
                isinstance(ev, dict) 
                and all(k in ev for k in ["date", "title", "description"])
            ):
                valid_events.append(ev)
            else:
                print(f"Warning: One event is missing required keys or is not a dict:\n{ev}")

        return valid_events
    
    except json.JSONDecodeError:
        print("Failed to parse AI output as valid JSON. Raw output:")
        print(response.text)
        return []


def generate_historical_events(nations: list, start_date: str, lookback: int) -> list:
    """
    Generate or gather major events that impacted these nations in the last 'lookback' years.
    For demonstration, we create a placeholder event. In real usage, you might call an AI-based
    generator or load from a data source.

    :param nations: List of nation names
    :param start_date: The starting year of the scenario
    :param lookback: How many years to go back
    :return: A list of event objects (matching global_event_schema, typically)
    """
    print("\n--- Generating important events for each nation (looking back) ---")
    global_events = []

    if not nations:
        return global_events

    # Just one placeholder conflict for demonstration:
    placeholder_event = {
        "eventType": "Conflict",
        "eventData": {
            "conflictName": "Placeholder War",
            "startDate": f"{int(start_date) - 2}-01-15",
            "endDate": None,
            "status": "Ongoing",
            "belligerents": {
                "sideA": [nations[0]] if nations else ["ExampleN1"],
                "sideB": [nations[-1]] if len(nations) > 1 else ["ExampleN2"]
            },
            "casualties": {"military": 1000, "civilian": 500},
            "territorialChanges": []
        },
        "ramifications": [
            {
                "ramificationType": "Military",
                "severity": "High (Broad-scale impact, multiple sectors affected, long recovery needed)",
                "affectedParties": (
                    [nations[0], nations[-1]] if len(nations) > 1 else ["ExampleN1", "ExampleN2"]
                ),
                "description": "Regional instability leading to arms race.",
                "timeframe": "Short-Term (2 weeks to 3 months)"
            }
        ]
    }

    global_events.append(placeholder_event)
    return global_events

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
    nat_effects_schema_path = "national_effect_schema.json"
    try:
        with open(nat_effects_schema_path, "r", encoding="utf-8") as f:
            nat_effects_schema = json.load(f)
    except FileNotFoundError:
        print(f"Warning: {nat_effects_schema_path} not found. We'll do minimal effect records.")
        nat_effects_schema = None

    for ev in global_events:
        ramifications = ev.get("ramifications", [])
        # This placeholder uses eventData.conflictName as an eventId, real usage might differ
        event_id_label = ev["eventData"].get("conflictName", "EventNoName")

        for ram in ramifications:
            impacted_nations = ram.get("affectedParties", [])
            for nation_name in impacted_nations:
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

                new_effect = {
                    "nation": nation_name,
                    "effectId": f"{nation_name}-{int(time.time())}",
                    "originEventId": event_id_label,
                    "originEventType": ev["eventType"],
                    "ramificationType": ram.get("ramificationType", "Other"),
                    "severity": ram.get("severity", "Minimal"),
                    "affectedSectors": ["Military"],  # minimal
                    "description": ram.get("description", ""),
                    "timeframe": ram.get("timeframe", "Short-Term (2 weeks to 3 months)"),
                    "startDate": datetime.datetime.now().strftime("%Y-%m-%d"),
                    "isActive": True,
                    "nationalMemoryImpact": "Moderately Remembered (Occasionally referenced in media or academia)"
                }

                existing_effects.append(new_effect)
                with open(effects_file, "w", encoding="utf-8") as ef:
                    json.dump(existing_effects, ef, indent=2)

                print(f"Added effect to {nation_name}: {new_effect['ramificationType']}")

def generate_global_structures(nations: list, start_date: str, char_count: int):
    """
    Creates the overarching global data files, including:
    - global_sentiment.json
    - global_trade.json
    - notable_characters.json
    - organizations.json
    - strategic_interests.json
    - global_economy.json
    """
    simulation_path = os.path.join("simulation_data", f"Simulation_{start_date}")
    os.makedirs(simulation_path, exist_ok=True)

    # --- Global Sentiment ---
    if len(nations) > 1:
        print("\n--- Generating global_sentiment.json ---")
        global_sentiment_path = os.path.join(simulation_path, "global_sentiment.json")
        sentiment_array = []
        for i in range(len(nations)):
            for j in range(i+1, len(nations)):
                pair = {
                    "nationA": nations[i],
                    "nationB": nations[j],
                    "diplomaticRelations": "Neutral",
                    "economicTrust": 50,
                    "militaryTensions": 50,
                    "ideologicalAlignment": "Neutral"
                }
                sentiment_array.append(pair)
        with open(global_sentiment_path, "w", encoding="utf-8") as gf:
            json.dump(sentiment_array, gf, indent=2)
        print(f"Saved global_sentiment.json with {len(sentiment_array)} pairs.")
    else:
        print("Only one nation chosen, skipping global sentiment array creation.")

    # --- Global Trade ---
    if len(nations) > 1:
        print("\n--- Generating global_trade.json ---")
        global_trade_path = os.path.join(simulation_path, "global_trade.json")
        trade_relations = []
        relation_id_count = 1
        for i in range(len(nations)):
            for j in range(i+1, len(nations)):
                rel = {
                    "relationId": f"trade-rel-{relation_id_count}",
                    "year": int(start_date),
                    "nationA": nations[i],
                    "nationB": nations[j],
                    "totalTradeVolume": "Minimal Trade (<$10B)",
                    "tradeDifference": {
                        "balance": "Perfectly Balanced (0%)",
                        "surplusNation": "",
                        "deficitNation": ""
                    },
                    "exportsFromA": [],
                    "exportsFromB": [],
                    "tradeAgreements": []
                }
                relation_id_count += 1
                trade_relations.append(rel)
        with open(global_trade_path, "w", encoding="utf-8") as tf:
            json.dump(trade_relations, tf, indent=2)
        print(f"Saved global_trade.json with {len(trade_relations)} pairwise trade records.")
    else:
        print("Only one nation chosen, skipping global trade array creation.")

    # --- Notable Characters ---
    print("\n--- Generating notable_characters.json ---")
    notable_chars_path = os.path.join(simulation_path, "notable_characters.json")
    all_chars = []
    for n in nations:
        for c_i in range(char_count):
            c_obj = {
                "fullName": f"{n} Character {c_i+1}",
                "aliases": [],
                "birthDate": "1900-01-01",
                "deathDate": None,
                "nationality": n,
                "politicalAffiliation": "Independent",
                "role": "Other",
                "majorContributions": [],
                "associatedEvents": [],
                "publicPerception": "Unknown",
                "quotes": [],
                "legacy": "Moderate"
            }
            all_chars.append(c_obj)
    with open(notable_chars_path, "w", encoding="utf-8") as cf:
        json.dump(all_chars, cf, indent=2)
    print(f"Saved notable_characters.json with {len(all_chars)} character entries.")

    # --- Organizations (placeholder) ---
    print("\n--- Generating organizations.json ---")
    organizations_path = os.path.join(simulation_path, "organizations.json")
    orgs_array = [
        {
            "entityId": "ORG-0001",
            "entityType": "International Organization",
            "name": "Placeholder Alliance",
            "formationOrSigningDate": f"{start_date}-01-01",
            "dissolutionOrExpiryDate": None,
            "status": "Active",
            "memberStates": nations,
            "entityCategory": "Military",
            "primaryObjectives": ["Collective defense", "Strategic cooperation"],
            "influenceScore": 75
        }
    ]
    with open(organizations_path, "w", encoding="utf-8") as of:
        json.dump(orgs_array, of, indent=2)
    print(f"Saved organizations.json with {len(orgs_array)} entries.")

    # --- Strategic Interests (placeholder) ---
    print("\n--- Generating strategic_interests.json ---")
    interests_path = os.path.join(simulation_path, "strategic_interests.json")
    interests_array = [
        {
            "interestName": "Arctic Shipping Lanes",
            "region": "Arctic Circle",
            "resourceType": "Shipping lane",
            "importanceLevel": "High",
            "controllingEntities": ["Canada", "Russia"],
            "rivalClaims": nations if len(nations) > 2 else [],
            "strategicValue": "Potential for trade route shortcuts as ice recedes.",
            "potentialConflicts": [],
            "economicValue": "$100 billion",
            "environmentalConcerns": "Melting icecaps, endangered species"
        }
    ]
    with open(interests_path, "w", encoding="utf-8") as sf:
        json.dump(interests_array, sf, indent=2)
    print(f"Saved strategic_interests.json with {len(interests_array)} entries.")

    # --- Global Economy (placeholder) ---
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
    nations = input_nations()
    start_date = input_start_date()
    lookback = input_lookback_years()
    char_count = input_characters_count()

    print("\n=== Starting Global Initialization ===")
    print(f"Selected Nations: {nations}")
    print(f"Timeline Start: {start_date}")
    print(f"Lookback Years: {lookback}")
    print(f"Characters per Nation: {char_count}")

    # 2) Initialize each nation's data
    init_nations(nations, start_date)

    # 3) Generate major events that impacted these nations
    global_events = generate_historical_events(nations, start_date, lookback)

    # 4) For each event, apply ramifications to the relevant nations
    apply_ramifications_to_nations(nations, start_date, global_events)

    # 5) Generate all the global structures (sentiment, trade, characters, organizations, etc.)
    generate_global_structures(nations, start_date, char_count)

    print("\n=== Global Initialization Complete ===")
    print(f"Scenario data saved under 'simulation_data/Simulation_{start_date}/'.")


if __name__ == "__main__":
    main()

