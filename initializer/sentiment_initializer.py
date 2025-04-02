#!/usr/bin/env python3

import os
import json
import re # For parsing retry delay
import time
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
import concurrent.futures # Added for parallel processing
from itertools import combinations # To generate pairs
from initializer_util import *

#GET RELEVANT EVENTS WITH A QUERYING METHOD, DON'T LEAVE IT UP TO AI

###############################################################################
#                        ASKING THE AI FOR ONE RELATION                       #
###############################################################################

def fetch_relation_from_ai(nationA, nationB, model, time_period):
    """
    Polls the AI model to obtain a single JSON object representing
    the relationship between nationA and nationB, following the schema,
    but with an empty relevantEvents array.

    Returns a dictionary. If parsing fails, it retries a few times before giving up.
    """
    prompt = f"""
You are given two nations: {nationA} and {nationB}. You will generate their relations between one another, at a given point in time: {time_period}.
Generate a strictly valid JSON object (no extra keys) matching this schema:

Required fields:
1. "nationA" (string): should be exactly "{nationA}".
2. "nationB" (string): should be exactly "{nationB}".
3. "diplomaticRelations" (enum): one of ["Allied","Friendly","Neutral","Tense","Hostile"].
4. "economicTrust" (number 0-100).
5. "militaryTensions" (number 0-100).
6. "ideologicalAlignment" (enum): one of ["Identical","Similar","Neutral","Divergent","Opposed"].
7. "relevantEvents": MUST be an empty array `[]`. This will be populated later.

Please provide ONLY the JSON object as the final output, with no extra commentary or markdown formatting.
    """

    attempt = 0
    max_attempts = 15
    while attempt < max_attempts:
        raw_output = "" # Initialize raw_output here to avoid UnboundLocalError
        try:
            response = model.generate_content(prompt)

            # Check for safety blocks or empty parts before accessing text
            if not response.parts:
                 finish_reason = getattr(response.candidates[0], 'finish_reason', None) if response.candidates else None
                 if finish_reason == 4: # SAFETY
                     print(f"  [SAFETY] AI response blocked for relation {nationA}-{nationB}. Skipping attempt {attempt+1}.")
                     attempt += 1
                     # time.sleep(1)
                     continue
                 else:
                     raise ValueError(f"AI response has no valid parts (finish_reason={finish_reason}).")

            raw_output = response.text.strip()
            # Apply slicing to remove potential fences
            raw_json_text = raw_output[7:-3] if raw_output.startswith("```json") else raw_output

            # Attempt to parse the extracted JSON string
            relation_dict = json.loads(raw_json_text)

            # Ensure it's actually a dictionary now
            if not isinstance(relation_dict, dict):
                raise ValueError("Parsed JSON is not a dictionary object.")

            # Validate required fields
            required_keys = ["nationA", "nationB", "diplomaticRelations", "economicTrust", "militaryTensions", "ideologicalAlignment"]
            if not all(key in relation_dict for key in required_keys):
                 # Check if relevantEvents is missing and add it if so
                 if "relevantEvents" not in relation_dict:
                     relation_dict["relevantEvents"] = []
                 # Re-check if all required keys (including relevantEvents now) are present
                 if not all(key in relation_dict for key in required_keys + ["relevantEvents"]):
                     raise ValueError(f"Missing required keys in the JSON object for {nationA}-{nationB}.")

            # Ensure relevantEvents is an empty list as requested by the prompt
            if relation_dict.get("relevantEvents") != []:
                print(f"Warning: AI included events for {nationA}-{nationB} despite prompt. Resetting to [].")
                relation_dict["relevantEvents"] = []

            return relation_dict

        except (json.JSONDecodeError, ValueError) as e: # Catch both parsing and validation errors
            print(f"Failed to parse/validate AI output as valid JSON object for {nationA}-{nationB} (Attempt {attempt+1}/{max_attempts}): {e}")
            if raw_output: print(f"Raw AI output was:\n{raw_output}")
            attempt += 1
            if attempt == max_attempts: break
            # print("Waiting 2 seconds before retrying...")
            # time.sleep(2)

        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' (Attempt {attempt+1}/{max_attempts}): {rate_limit_error}")
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
            print(f"Encountered unexpected error {type(e).__name__}: {e}. Retrying (attempt {attempt+1}/{max_attempts})...")
            attempt += 1
            if attempt == max_attempts: break
            # print("Waiting 5 seconds before retrying...")
            # time.sleep(5) # Use a longer delay for general errors

    # If all attempts fail, return a fallback object or None
    print(f"Max attempts reached for {nationA}-{nationB}. Returning a fallback object.")
    return {
        "nationA": nationA,
        "nationB": nationB,
        "diplomaticRelations": "Neutral",
        "economicTrust": 50,
        "militaryTensions": 50,
        "ideologicalAlignment": "Neutral",
        "relevantEvents": [] # Ensure fallback also has empty list
    }

def generate_event_relevance(model, nationA, nationB, event):
    """
    Asks the AI to describe the relevance of a specific event to the
    relationship between nationA and nationB.

    :param model: Configured AI model.
    :param nationA: Name of the first nation.
    :param nationB: Name of the second nation.
    :param event: The global event dictionary.
    :return: A dictionary like {"impactOnRelations": "...", "notes": "..."} or None on failure.
    """
    event_desc = event.get("eventData", {}).get("description", event.get("eventData", {}).get("eventName", event.get("eventId", "Unknown Event")))
    event_type = event.get("eventType", "Unknown")
    event_date = event.get("eventData", {}).get("startDate", "Unknown Date")

    prompt = f"""
Context:
- Nation A: {nationA}
- Nation B: {nationB}
- Event Type: {event_type}
- Event Date: {event_date}
- Event Description: {event_desc}

Task:
Analyze the provided event and describe its relevance specifically to the relationship between {nationA} and {nationB}.

Output ONLY a valid JSON object with the following fields:
- "impactOnRelations": (enum) Choose the most appropriate impact level from ["Minimal", "Moderate", "Severe", "Transformational"].
- "notes": (string) A brief (1-2 sentence) explanation of *why* this event is relevant to the relationship between {nationA} and {nationB}. Focus specifically on their interaction or shared context within the event.

Example Output:
{{
  "impactOnRelations": "Moderate",
  "notes": "This trade dispute increased economic friction between the two nations, leading to retaliatory tariffs."
}}

Do not include any extra text or markdown formatting.
    """

    max_attempts = 5
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        raw_output = ""
        try:
            response = model.generate_content(prompt)

            # Check for safety blocks before accessing text
            if not response.parts:
                 finish_reason = getattr(response.candidates[0], 'finish_reason', None) if response.candidates else None
                 if finish_reason == 4: # SAFETY
                     print(f"  [SAFETY] AI response blocked for event relevance ({nationA}-{nationB}, Event: {event.get('eventId')}). Skipping attempt {attempt}.")
                     # time.sleep(1)
                     continue
                 else:
                     raise ValueError(f"AI response has no valid parts (finish_reason={finish_reason}).")

            raw_output = response.text.strip()
            # Apply slicing to remove potential fences
            raw_json_text = raw_output[7:-3] if raw_output.startswith("```json") else raw_output

            relevance_data = json.loads(raw_json_text)

            if isinstance(relevance_data, dict) and "impactOnRelations" in relevance_data and "notes" in relevance_data:
                # Basic validation passed
                return relevance_data
            else:
                raise ValueError("Generated JSON missing required keys 'impactOnRelations' or 'notes'.")

        except (json.JSONDecodeError, ValueError) as e:
            print(f"  [ERROR] Failed to parse/validate event relevance for {nationA}-{nationB} (Event: {event.get('eventId')}, Attempt {attempt}/{max_attempts}): {e}")
            if raw_output: print(f"  Raw AI output was:\n{raw_output}")
            if attempt == max_attempts: break
            # print("  Waiting 2 seconds before retrying...")
            # time.sleep(2)
        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model')
            print(f"  [ERROR] Rate limit hit for model '{model_name}' generating event relevance (Attempt {attempt}/{max_attempts}): {rate_limit_error}")
            if attempt == max_attempts: break
            # Simplified retry delay logic for brevity
            # print("  Waiting 60 seconds due to rate limit...")
            # time.sleep(60)
        except Exception as e:
            print(f"  [ERROR] Unexpected error generating event relevance (Attempt {attempt}/{max_attempts}): {type(e).__name__} - {e}")
            if attempt == max_attempts: break
            # print("  Waiting 5 seconds before retrying...")
            # time.sleep(5)

    print(f"  [FAILURE] Max attempts reached for event relevance generation ({nationA}-{nationB}, Event: {event.get('eventId')}). Returning None.")
    return None


###############################################################################
#                      MAIN SCRIPT: BUILDING THE RELATIONS (PARALLELIZED)     #
###############################################################################

def build_global_sentiment(nations, time_period, model, max_workers=10):
    """
    Generates global sentiment data for all unique pairs of nations in parallel.

    :param nations: List of nation names.
    :param time_period: The reference year/period.
    :param model: The configured AI model instance.
    :param max_workers: Maximum number of threads for parallel execution.
    :return: A list of sentiment relation dictionaries.
    """
    relations = []
    nation_pairs = list(combinations(nations, 2)) # Generate all unique pairs

    print(f"\nStarting parallel sentiment generation for {len(nation_pairs)} pairs using up to {max_workers} workers...")

    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks for each pair
        for nationA, nationB in nation_pairs:
            print(f"  Submitting task for relation: {nationA} and {nationB}...")
            future = executor.submit(
                fetch_relation_from_ai,
                nationA,
                nationB,
                model,
                time_period
            )
            futures.append(future)

        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            try:
                relation_data = future.result()
                if relation_data: # Check if fallback wasn't returned or AI failed completely
                    relations.append(relation_data)
                    print(f"  Collected sentiment data for {relation_data.get('nationA', '?')}-{relation_data.get('nationB', '?')}")
            except Exception as exc:
                # Log exceptions from threads if needed
                print(f'!!! Thread for sentiment generation raised an exception: {exc}')

    print(f"\n--- Parallel Sentiment Generation Summary ---")
    print(f"Total relations generated: {len(relations)}")
    # Could add more summary details if needed

    return relations

def populate_relevant_events(sentiment_relations: list, global_events: list, model, max_workers=10):
    """
    Populates the 'relevantEvents' field for each sentiment relation by finding
    matching global events and using AI to determine relevance.

    :param sentiment_relations: List of sentiment relation dictionaries (will be modified in-place).
    :param global_events: List of global event dictionaries.
    :param model: Configured AI model instance.
    :param max_workers: Max workers for parallel AI calls for relevance.
    """
    print(f"\n--- Populating Relevant Events for {len(sentiment_relations)} Sentiment Relations ---")
    if not global_events:
        print("Warning: No global events provided to populate relevantEvents.")
        return

    tasks = []
    # Prepare tasks: (sentiment_relation_index, nationA, nationB, matching_event)
    for i, relation in enumerate(sentiment_relations):
        nationA = relation.get("nationA")
        nationB = relation.get("nationB")
        if not nationA or not nationB:
            continue

        # Find events where both nations participated
        for event in global_events:
            participants = event.get("participatingNations", [])
            if isinstance(participants, list) and nationA in participants and nationB in participants:
                # Add task to generate relevance for this event-pair combination
                tasks.append({
                    "index": i,
                    "nationA": nationA,
                    "nationB": nationB,
                    "event": event
                })

    print(f"Found {len(tasks)} potential relevant event links to analyze with AI...")

    results_map = {} # Store results: {index: [relevant_event_entry, ...]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(generate_event_relevance, model, task["nationA"], task["nationB"], task["event"]): task
            for task in tasks
        }

        for future in concurrent.futures.as_completed(future_to_task):
            task = future_to_task[future]
            index = task["index"]
            event = task["event"]
            try:
                relevance_data = future.result()
                if relevance_data:
                    # Construct the entry for the relevantEvents array
                    relevant_event_entry = {
                        "eventId": event.get("eventId"),
                        "date": event.get("eventData", {}).get("startDate", "Unknown Date"),
                        "impactOnRelations": relevance_data.get("impactOnRelations"),
                        "notes": relevance_data.get("notes")
                    }
                    if index not in results_map:
                        results_map[index] = []
                    results_map[index].append(relevant_event_entry)
                    print(f"  Generated relevance for Event {event.get('eventId')} for relation index {index}")

            except Exception as exc:
                print(f"!!! Thread for event relevance (Index: {index}, Event: {event.get('eventId')}) generated an exception: {exc}")

    # Update the original sentiment relations list
    print("\n--- Updating Sentiment Relations with Relevant Events ---")
    for index, relevant_event_list in results_map.items():
        if index < len(sentiment_relations):
            # Ensure the relevantEvents key exists and is a list
            if "relevantEvents" not in sentiment_relations[index] or not isinstance(sentiment_relations[index]["relevantEvents"], list):
                 sentiment_relations[index]["relevantEvents"] = [] # Initialize/reset if needed
            sentiment_relations[index]["relevantEvents"].extend(relevant_event_list)
            print(f"  Added {len(relevant_event_list)} relevant events to relation index {index}.")
        else:
            print(f"Warning: Index {index} out of bounds for sentiment_relations list.")

    print("--- Finished Populating Relevant Events ---")


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

    # 2) Build the "global sentiment" relations array (now returns with empty relevantEvents)
    relations = build_global_sentiment(nations, "1985", model) # Pass model explicitly

    # 3) Post-processing: Load global events and populate relevantEvents
    #    (This part needs the path to global_events.json)
    #    Example:
    #    output_dir = "simulation_data/generated_timeline_1985"
    #    global_events_path = os.path.join(output_dir, "global_events.json")
    #    if os.path.exists(global_events_path):
    #        with open(global_events_path, "r", encoding="utf-8") as f:
    #            global_events = json.load(f)
    #        populate_relevant_events(relations, global_events, model) # Pass model
    #    else:
    #        print(f"Warning: {global_events_path} not found. Cannot populate relevant events.")

    # 4) Display or save the final relations
    for relation in relations:
        print(json.dumps(relation, indent=2))
    # save_global_sentiment(relations, filename="global_sentiment.json")


def initialize_sentiment(nations: list, filename: str, time_period: str, max_workers=10):
    """
    Initializes global sentiment data in parallel, populates relevant events, and saves it.

    Requires global_events.json to exist in the same directory as the output file.
    """
    global model # Ensure model is configured and accessible globally or passed down
    model = configure_genai(temp=0.7, model="gemini-2.0-flash") # Configure the model used by threads
    relevance_model = configure_genai(temp=0.5, model="gemini-2.0-flash") # Separate model/config for relevance if desired

    print(f"\n--- Initializing Global Sentiment for {len(nations)} nations (Year: {time_period}) ---")
    # Step 1: Build relations with empty relevantEvents
    relations = build_global_sentiment(
        nations=nations,
        time_period=time_period,
        model=model, # Pass the main model
        max_workers=max_workers
    )

    # --- Post-processing Step ---
    # Load global events (assuming it's saved in the same directory as the output sentiment file)
    output_dir = os.path.dirname(filename)
    global_events_path = os.path.join(output_dir, "global_events.json")
    global_events = []
    if os.path.exists(global_events_path):
        try:
            with open(global_events_path, "r", encoding="utf-8") as f:
                global_events = json.load(f)
            print(f"Loaded {len(global_events)} global events for relevance check.")
            # Step 2: Populate relevant events using the loaded global events and relevance model
            populate_relevant_events(relations, global_events, relevance_model, max_workers)
        except Exception as e:
            print(f"Error loading or processing global events from {global_events_path}: {e}")
            print("Skipping population of relevantEvents.")
    else:
        print(f"Warning: Global events file not found at {global_events_path}. Cannot populate relevantEvents.")


    # Step 3: Save the updated relations (with populated relevantEvents)
    save_global_sentiment(relations, filename)
    return relations

if __name__ == "__main__":
    # Example of calling the parallelized initialization
    example_nations = ["US", "UK", "USSR", "India", "China", "France"]
    example_year = "1985"
    example_workers = 6 # Adjust based on system/API limits
    output_file = f"simulation_data/generated_timeline_{example_year}/global_sentiment.json"

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Call the main initialization function
    initialize_sentiment(
        nations=example_nations,
        filename=output_file,
        time_period=example_year,
        max_workers=example_workers
    )

    # Note: The original main() function is kept above but is no longer the primary entry point
    # if this script is run directly due to the __name__ == "__main__": block above.
    # You might want to remove or comment out the old main() if it's redundant.
