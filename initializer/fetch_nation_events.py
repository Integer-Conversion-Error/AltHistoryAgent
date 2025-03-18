#!/usr/bin/env python3

"""
test_fetch_nation_events_brief.py

This script provides a test harness for the `fetch_nation_events_brief` function.
It configures an actual AI model, calls the function with sample parameters,
and displays the returned results for verification.
"""


import sys, os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(parent_dir)

import json
import google.generativeai as genai
import time
from writers import low_level_writer
from initializer_util import *

###############################################################################
#                        FUNCTION TO FETCH EVENTS                             #
###############################################################################

def fetch_nation_events_brief(model, nation_name: str, start_year: int, end_year: int) -> list:
    """
    Asks the AI model for a JSON array of important events in which 'nation_name' was involved,
    during the time period [start_year, end_year]. Each event in the array should only include:

      [
        {
          "date": "YYYY-MM-DD",
          "title": "Short title of the event",
          "description": "Brief explanation of the event"
        },
        ...
      ]

    :param model: A configured generative AI model.
    :param nation_name: The nation for which we want to gather historical events.
    :param start_year: The earliest year (inclusive) to look for events.
    :param end_year: The latest year (inclusive) to look for events.
    :return: A Python list of dictionaries, each with keys "date", "title", and "description".
             Returns an empty list if parsing fails or if the AI does not produce the desired format.
    """


    
    prompt = f"""
    You are an expert historian. Provide a valid JSON array of important events 
    involving '{nation_name}' between {start_year} and {end_year}. The events MUST be between these two dates. Exclude any events that are not within these two dates. Any event after {end_year} CANNOT BE INCLUDED, and likewise for any event before {start_year}.

    Each event object in the array must ONLY include these keys:
      - "date" (in YYYY-MM-DD format) – The exact date of the event.
      - "title" (short name of the event) – A concise, well-known name.
      - "description" (a concise explanation, no more than a few sentences).
      - "eventType" (the general category of the event) – Choose from one or more of (multiple choice possible, but cannot use Conflict and Battle at the same time, everything else is fair game though):
        ["Conflict", "Battle", "Economic Event", "Political Violence", 
         "Scientific Discovery", "Natural Disaster", "Humanitarian Crisis", 
         "Political Event", "Generic Event"]

    The final output must be strictly valid JSON containing only an array of objects, 
    with no extra text or explanation. Do not wrap in quotes or add extra fields.
    
    Before finalizing an event, **validate** that the selected "eventType" is the most appropriate category for it.
    
    **Validation Rules:**
    - "Conflict" → Must involve armed combat, military confrontations, wars, or large-scale violence between nations or factions. Peace treaties, truces, ceasefires, and/or the end of conflicts are NOT included here.
    - "Battle" → A specific engagement within a larger conflict. Must have clear belligerents, a location, and an outcome.
    - "Economic Event" → Must involve financial crises, economic recessions, market crashes, trade agreements, or monetary policies with national/global impact.
    - "Political Violence" → Must involve assassinations, coups, terror attacks, uprisings, insurgencies, or any politically motivated large-scale violence.
    - "Scientific Discovery" → Must be a breakthrough in science or technology, such as space exploration milestones, medical advancements, or engineering feats.
    - "Natural Disaster" → Must be a large-scale natural catastrophe such as an earthquake, hurricane, tsunami, or volcanic eruption, affecting nations or regions.
    - "Humanitarian Crisis" → Must involve a large-scale crisis impacting civilian populations, such as famine, refugee waves, epidemics, or severe displacement.
    - "Political Event" → Must involve governmental changes, revolutions, diplomatic agreements, major treaties, new state formations, or shifts in power.
    - "Generic Event" → A broad category for events that do not fit precisely into the above but have historical importance and long-term consequences.

    **DO NOT allow incorrect classifications.**
    - If a military engagement is described, it **MUST** be either a "Battle" or a "Conflict"—not an "Economic Event."
    - If an event describes political changes, it **CANNOT** be labeled as a "Scientific Discovery."
    - If an event describes the outbreak of war, it **CANNOT** be labeled "Political Event" unless war declaration/diplomatic negotiations are the primary focus.

    The final output **MUST** match the correct event type based on the above criteria. **No misclassifications are allowed.**
    
    Ensure that each event is significant on a national or international level. 
    Do NOT list sub-events that are part of a larger event (e.g., "The Invasion of the USSR" 
    should not be listed separately from "World War II" unless there is a specific reason). 

    Focus on events that had lasting political, military, economic, or social ramifications. 
    """


    
    attempt = 0
    max_attempts = 15
    while attempt < max_attempts:
        try:
            response = model.generate_content(prompt)
            raw_output = response.text.strip()[7:-3]
            print(raw_output)
            parsed_events = json.loads(raw_output)
            
            if not isinstance(parsed_events, list):
                print(f"Attempt {attempt + 1}: AI did not return a JSON array. Retrying...")
                attempt += 1
                time.sleep(5)
                continue

            valid_events = []
            for ev in parsed_events:
                if (
                    isinstance(ev, dict) 
                    and all(k in ev for k in ["date", "title", "description"])
                ):
                    valid_events.append(ev)
                else:
                    print(f"Warning: An event is missing required keys or is not a dict:\n{ev}")

            return valid_events
        
        except json.JSONDecodeError:
            print(f"Attempt {attempt + 1}: Failed to parse AI output as JSON. Retrying...")
            attempt += 1
            time.sleep(5)
            
        except Exception as e:
            print(f"Ran into exception {e} (most likely rate limiting). Retrying (attempt {attempt+1})...")
            attempt += 1
            time.sleep(2)

    print("Max attempts reached. Returning empty list.")
    return []


def save_events_as_json(events, save_path="simulation_data/events"):
    """
    Converts raw event descriptions into structured JSON files, following
    the correct schema based on eventType.

    :param events: List of event dictionaries from `fetch_nation_events_brief`.
    :param nation_name: The nation these events belong to.
    :param save_path: Directory where JSON files will be saved.
    """
    if not events:
        print(f"No events to process.")
        return

    os.makedirs(save_path, exist_ok=True)

    schema_map = {
        "Conflict": "global_subschemas/event_subschemas/conflicts_schema.json",
        "Battle": "global_subschemas/event_subschemas/conflicts_schema.json",
        "Economic Event": "global_subschemas/event_subschemas/economic_events_schema.json",
        "Political Violence": "global_subschemas/event_subschemas/political_violence_schema.json",
        "Scientific Discovery": "global_subschemas/event_subschemas/scientific_discoveries_schema.json",
        "Natural Disaster": "global_subschemas/event_subschemas/natural_disasters_schema.json",
        "Humanitarian Crisis": "global_subschemas/event_subschemas/humanitarian_crises_schema.json",
        "Political Event": "global_subschemas/event_subschemas/political_events_schema.json",
        "Generic Event": "global_subschemas/event_subschemas/generic_event_schema.json"
    }

    for event in events:
        event_types = event["eventType"]

        # Ensure a valid schema exists
        for event_type in event_types:
            if event_type not in list(schema_map):
                print(f"Warning: Unknown eventType '{event_type}'. Skipping event.")
                continue

            schema_path = schema_map[event_type]

            try:
                with open(schema_path, "r", encoding="utf-8") as file:
                    event_schema = json.load(file)
            except FileNotFoundError:
                print(f"Error: Schema file {schema_path} not found. Skipping event.")
                continue

            # Generate structured event JSON using low_level_writer
            structured_event = low_level_writer.produce_structured_data(
                json_schema=event_schema,
                action=f"Generate a structured event for '{event['title']}'",
                context=event["description"]
            )

            if structured_event:
                event_file = os.path.join(save_path, f"{event['date']}_{event_type}.json")
                with open(event_file, "w", encoding="utf-8") as f:
                    json.dump(structured_event, f, indent=2)
                print(f"Saved: {event_file}")

###############################################################################
#                              TESTING FUNCTION                               #
###############################################################################

def test_fetch_and_save_nation_events():
    """
    Calls `fetch_nation_events_brief` and `save_events_as_json` to fully test
    fetching and storing structured event data.
    """
    model = configure_genai(temp = 0.1)

    nation_name = "Finland"
    start_year = 1920
    end_year = 1970

    events = fetch_nation_events_brief(model, nation_name, start_year, end_year)

    print(f"\nFetched {len(events)} events for {nation_name}:")
    for e in events:
        print(json.dumps(e, indent=2))

    save_events_as_json(events, nation_name)
    
    
def fetch_and_save_nations_events(nations = ["United States of America"], start_year = 1920, end_year = 1965):
    """
    Calls `fetch_nation_events_brief` and `save_events_as_json` to fully test
    fetching and storing structured event data.
    """
    
    
    model = configure_genai()
    events = []
    for nation_name in nations:
        save_dir = f"simulation_data/generated_timeline_{end_year}/nations/{nation_name}/events"
        events = fetch_nation_events_brief(model, nation_name, start_year, end_year)

        print(f"\nFetched {len(events)} events for {nation_name}:")
        for e in events:
            print(json.dumps(e, indent=2))

        save_events_as_json(events, save_dir)
    
    return events

# If run as a script, trigger the test
if __name__ == "__main__":
    test_fetch_and_save_nation_events()