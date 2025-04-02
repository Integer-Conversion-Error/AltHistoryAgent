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
import re # For parsing retry delay
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
import time
import concurrent.futures # Added for parallel processing
from writers import low_level_writer
from initializer_util import *

###############################################################################
#                        FUNCTION TO FETCH EVENTS                             #
###############################################################################

def fetch_nation_events_brief(model, nation_name: str, start_year: int, end_year: int) -> list:
    """
    Asks the AI model for a JSON array of important global events involving 'nation_name'
    during the time period [start_year, end_year]. Each event should conform to the
    global_event_schema.json structure.

    :param model: A configured generative AI model.
    :param nation_name: The nation for which we want to gather historical events.
    :param start_year: The earliest year (inclusive) to look for events.
    :param end_year: The latest year (inclusive) to look for events.
    :return: A Python list of dictionaries, each representing a global event object.
             Returns an empty list if parsing fails or if the AI does not produce the desired format.
    """
    # Load the global event schema to provide context to the AI
    try:
        with open("global_subschemas/global_event_schema.json", "r", encoding="utf-8") as f:
            global_event_schema = json.load(f)
            # We might only need the 'items' part for the prompt if it's an array schema
            if global_event_schema.get("type") == "array" and "items" in global_event_schema:
                 event_object_schema = global_event_schema["items"]
            else:
                 event_object_schema = global_event_schema # Assume it's the object schema directly
    except FileNotFoundError:
        print("Error: global_event_schema.json not found. Cannot generate events.")
        return []
    except json.JSONDecodeError:
        print("Error: Failed to parse global_event_schema.json.")
        return []

    # Simplified prompt focusing on the full structure
    prompt = f"""
    You are an expert historian generating data for an alternate history simulation.
    Provide a valid JSON array of significant global events involving '{nation_name}'
    that occurred between {start_year} and {end_year} (inclusive).

    Each object in the array MUST strictly follow this JSON schema for a global event:
    {json.dumps(event_object_schema, indent=2)}

    Key requirements:
    - Generate a unique UUID for 'eventId'.
    - Select the most appropriate 'eventType' from the enum. Validate your choice based on the event's nature (e.g., Conflict, Economic Event, Political Event).
    - Fill 'eventData' with historically plausible details relevant to the 'eventType'. You may need to infer details based on the event title and context. The structure of 'eventData' depends on the 'eventType'.
    - **IMPORTANT: Within 'eventData', include a field named `standardizedEventName`. This name MUST follow the format: "EventType: Brief Descriptive Title (Year)". Use the actual eventType and the primary year the event occurred.** Example: "Political Event: Helsinki Accords Signed (1975)".
    - Set 'parentEventId', 'childEventIds', 'siblingEventIds' to null or empty arrays ([]) unless there's a clear historical relationship within the generated list or common knowledge (e.g., a specific battle as a child of a war).
    - Include '{nation_name}' (or its corresponding nationId if known, otherwise use the name) in the 'participatingNations' array. Include other known participating nations if applicable.
    - Add 1-3 general 'ramifications' describing potential high-level outcomes (political, economic, military etc.) with appropriate 'severity', 'affectedParties' (list nation names), 'description', and 'timeframe'.
    - Ensure the event date within 'eventData' (e.g., 'startDate') falls between {start_year} and {end_year}.

    Output ONLY the valid JSON array. No explanations, comments, or surrounding text.
    """

    attempt = 0
    max_attempts = 15
    while attempt < max_attempts:
        try:
            print(f"Attempt {attempt + 1}: Fetching events for {nation_name} ({start_year}-{end_year})...")
            response = model.generate_content(prompt)
            # Apply the requested slicing directly
            raw_json_text = response.text.strip()[7:-3]

            #print(f"Raw JSON received:\n{raw_json_text}\n") # Debugging
            parsed_events = json.loads(raw_json_text) # Expect an array

            if not isinstance(parsed_events, list):
                # Handle case where AI might return a single object instead of array?
                if isinstance(parsed_events, dict):
                    print(f"Warning: AI returned a single object for events of '{nation_name}', wrapping in a list.")
                    parsed_events = [parsed_events] # Wrap the single object in a list
                else:
                    # If it's not a list and not a dict we could wrap, it's an error
                    print(f"Attempt {attempt + 1}: AI did not return a JSON array or single object. Retrying...")
                    attempt += 1
                    time.sleep(5)
                continue

            # Basic validation (check for eventId and eventType)
            valid_events = []
            for ev in parsed_events:
                if isinstance(ev, dict) and "eventId" in ev and "eventType" in ev:
                    # Ensure participatingNations includes the target nation
                    if nation_name not in ev.get("participatingNations", []):
                         ev.setdefault("participatingNations", []).append(nation_name)
                    valid_events.append(ev)
                else:
                    print(f"Warning: Invalid event structure received:\n{ev}")

            print(f"Successfully fetched {len(valid_events)} events for {nation_name}.")
            return valid_events

        except (json.JSONDecodeError, ValueError) as e: # Catch both parsing and validation errors
            print(f"Attempt {attempt + 1}: Failed to parse/validate AI output as JSON array for {nation_name}: {e}. Retrying...")
            # Print the sliced text that failed parsing
            print("Sliced text causing error:\n", raw_json_text)
            attempt += 1
            if attempt == max_attempts: break
            # print("Waiting 6 seconds before retrying...")
            # time.sleep(6) # Longer sleep after parse error

        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' fetching events for {nation_name} (Attempt {attempt + 1}/{max_attempts}): {rate_limit_error}")
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
            # Catch other potential API errors
            print(f"Attempt {attempt + 1}: An unexpected error occurred: {type(e).__name__} - {e}. Retrying...")
            attempt += 1
            if attempt == max_attempts: break
            # Use a slightly longer delay for general errors
            # print("Waiting 10 seconds before retrying...")
            # time.sleep(10)

    print(f"Max attempts reached for {nation_name}. Returning empty list.")
    return []


def save_aggregated_events(all_events: list, simulation_dir: str):
    """
    Saves the aggregated list of global event objects to a single JSON file.

    :param all_events: The final list of unique global event objects.
    :param simulation_dir: The main directory for the current simulation run
                           (e.g., "simulation_data/generated_timeline_1975").
    """
    if not all_events:
        print("No aggregated events to save.")
        return

    output_path = os.path.join(simulation_dir, "global_events.json")
    try:
        os.makedirs(simulation_dir, exist_ok=True) # Ensure directory exists
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_events, f, indent=2)
        print(f"Successfully saved {len(all_events)} aggregated events to {output_path}")
    except Exception as e:
        print(f"Error saving aggregated events file: {e}")


def save_events_as_json(events: list, nation_name: str, directory: str = "."):
    """
    Saves a list of event objects to a JSON file named after the nation.

    :param events: The list of event objects.
    :param nation_name: The name of the nation, used for the filename.
    :param directory: The directory to save the file in (defaults to current).
    """
    if not events:
        print(f"No events provided for {nation_name}, nothing to save.")
        return

    # Sanitize nation name for filename
    safe_nation_name = "".join(c if c.isalnum() or c in (' ', '_') else '_' for c in nation_name).replace(' ', '_')
    output_filename = f"{safe_nation_name}_events.json"
    output_path = os.path.join(directory, output_filename)

    try:
        os.makedirs(directory, exist_ok=True) # Ensure directory exists
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)
        print(f"Successfully saved {len(events)} events for {nation_name} to {output_path}")
    except Exception as e:
        print(f"Error saving events file for {nation_name}: {e}")

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


# Worker function for parallel execution
def fetch_events_for_nation_worker(model, nation_name, start_year, end_year):
    """Fetches events for a single nation."""
    print(f"Starting event fetch for {nation_name} ({start_year}-{end_year})...")
    nation_events = fetch_nation_events_brief(model, nation_name, start_year, end_year)
    print(f"Finished event fetch for {nation_name}, found {len(nation_events)} events.")
    return nation_name, nation_events # Return nation name along with events


def fetch_and_save_nations_events(nations = ["United States of America"], start_year = 1920, end_year = 1965, max_workers=10):
    """
    Fetches events for multiple nations in parallel, aggregates them, removes duplicates,
    and saves the final list to a single global_events.json file.

    :param nations: List of nation names.
    :param start_year: Start year for event fetching.
    :param end_year: End year for event fetching (also used for directory naming).
    :param max_workers: Maximum number of threads to use for parallel fetching.
    :return: The aggregated list of unique global event objects.
    """
    model = configure_genai() # Configure model once
    aggregated_events = {} # Use dict for deduplication based on a unique key
    all_nation_results = [] # To store results from threads

    print(f"\nStarting parallel event fetching for {len(nations)} nations using up to {max_workers} workers...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks for each nation
        future_to_nation = {executor.submit(fetch_events_for_nation_worker, model, name, start_year, end_year): name for name in nations}

        # Process completed futures
        for future in concurrent.futures.as_completed(future_to_nation):
            nation_name = future_to_nation[future]
            try:
                _, nation_events = future.result() # Unpack result (nation_name, events_list)
                all_nation_results.append(nation_events) # Collect lists of events
                print(f"Successfully collected results for {nation_name}.")
            except Exception as exc:
                print(f'!!! Thread for {nation_name} generated an exception: {exc}')
                # Optionally add placeholder or skip this nation's events

    print("\n--- Aggregating and Deduplicating Events ---")
    # Aggregate events after all threads are done
    for nation_events in all_nation_results:
        for event in nation_events:
            # Use standardizedEventName for deduplication if available, otherwise fallback
            event_data = event.get("eventData", {})
            standard_name = event_data.get("standardizedEventName")
            event_date = event_data.get("startDate", event.get("date", "UnknownDate")) # Keep date for uniqueness

            if standard_name:
                unique_key = f"{standard_name}" # Primarily use the standard name
            else:
                # Fallback to previous method if standard name is missing
                event_title = event_data.get("eventName", event.get("title", "UnknownTitle"))
                unique_key = f"{event_title}_{event_date}"
                print(f"Warning: Missing 'standardizedEventName' for event {event.get('eventId')}. Using fallback key: {unique_key}")

            if unique_key not in aggregated_events:
                aggregated_events[unique_key] = event
            else:
                # Event already exists, maybe merge participatingNations?
                existing_event = aggregated_events[unique_key]
                new_participants = set(event.get("participatingNations", []))
                existing_participants = set(existing_event.get("participatingNations", []))
                merged_participants = list(existing_participants.union(new_participants))
                existing_event["participatingNations"] = merged_participants
                aggregated_events[unique_key] = existing_event # Update with merged participants
                print(f"Merged participants for duplicate event: {unique_key}")

    # Convert dict back to list
    final_event_list = list(aggregated_events.values())

    # Define simulation directory path
    simulation_dir = os.path.join("simulation_data", f"generated_timeline_{end_year}")

    # Save the aggregated list
    save_aggregated_events(final_event_list, simulation_dir)

    return final_event_list

# If run as a script, trigger the test
if __name__ == "__main__":
    test_fetch_and_save_nation_events()
