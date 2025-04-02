#!/usr/bin/env python3

import os
import json
import re # For parsing retry delay
import time
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
import concurrent.futures # Added for parallel processing
from itertools import combinations # To generate pairs
# Import the relevance generation function from sentiment_initializer
from sentiment_initializer import generate_event_relevance, populate_relevant_events
from initializer_util import configure_genai  # Or however you normally import this

###############################################################################
#                 LOAD SCHEMAS (SENTIMENT & TRADE) FROM JSON FILES           #
###############################################################################

def load_schema_text(schema_path):
    """
    Loads a JSON schema file as raw text for embedding in the AI prompt.
    """
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file '{schema_path}' not found.")
    with open(schema_path, "r", encoding="utf-8") as f:
        return f.read()

###############################################################################
#                   FETCH COMBINED (SENTIMENT + TRADE) DATA                   #
###############################################################################

def fetch_combined_data_for_pair(nationA, nationB, year, relation_id,
                                 sentiment_schema_text, trade_schema_text, model):
    """
    Makes ONE AI call to get BOTH sentiment (relationship) data AND trade data
    in a single JSON. The AI must output JSON with two top-level keys:
      {
        "sentimentData": { ...one object matching the sentiment schema "items"... },
        "tradeData": { ...one object matching the trade schema "items"... }
      }

    We embed the two schemas in the prompt. Each returned piece is for the same
    two nations in that same year, but they differ in structure:
      - The "sentimentData" must correspond to the one relationship object
        (like the "items" shape in the sentiment schema).
      - The "tradeData" must correspond to one trade object
        (like the "items" shape in the trade schema).

    We'll parse the AI's output, returning (sentiment_obj, trade_obj) if valid.
    If any step fails, we retry up to a maximum number of attempts.
    """
    # Build the single prompt that merges both schemas and instructions, emphasizing detail
    prompt = f"""
We are modeling a detailed relationship and trade link between two nations: {nationA} and {nationB}, specifically for the year {year}.
Your goal is to generate historically plausible and detailed information reflecting their interactions during this period.

We have TWO JSON schemas that define the structure for the output:

1) **Sentiment/Relationship Schema** (structure for a single relationship object):
```json
{sentiment_schema_text}
```

2) **Trade Relation Schema** (structure for a single trade relationship object):
```json
{trade_schema_text}
```

**Instructions for Generation:**

You must output a SINGLE valid JSON object containing exactly two top-level keys: "sentimentData" and "tradeData". The value for each of these keys MUST be a JSON *object*, not an array.

1.  **sentimentData**:
    *   The value for this key must be a JSON *object* that strictly follows the Sentiment/Relationship Schema provided above.
    *   Fill in the fields with detailed and nuanced descriptions reflecting the diplomatic, economic, military, and ideological relationship between {nationA} and {nationB} in {year}. Be specific and provide context.
    *   **IMPORTANT: Set the `relevantEvents` field to an empty array `[]`.** We will populate this later.
    *   Ensure `nationA` is "{nationA}" and `nationB` is "{nationB}".

2.  **tradeData**:
    *   The value for this key must be a JSON *object* that strictly follows the Trade Relation Schema provided above.
    *   Provide a detailed `tradeSummary` (if present) describing the nature and key aspects of their trade relationship in {year}.
    *   **Populate arrays like `majorTradeGoods`, `exportsFromA`, `exportsFromB` (if present) with several specific examples of goods exchanged.** Aim for 3-5 examples per relevant array.
    *   **Populate the `tradeIssues` array (if present) with several specific examples of trade disputes, agreements, or notable factors relevant to {year}.** Aim for 2-4 relevant issues.
    *   Estimate `totalTradeVolume` plausibly for the era and nations involved.
    *   Ensure `relationId` is "{relation_id}", `year` is {year}, `nationA` is "{nationA}", and `nationB` is "{nationB}".

**Output Format:**
Provide *only* the final JSON object. Do not include any introductory text, explanations, apologies, or markdown code fences (```json ... ```). The output must start with `{{` and end with `}}`.

Example structure:
{{
  "sentimentData": {{ ... // detailed sentiment object here following schema ... }},
  "tradeData": {{ ... // detailed trade object here following schema ... }}
}}
    """.strip()

    max_attempts = 8
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        print(f"\n[AI] Attempt {attempt}/{max_attempts} to get combined sentiment+trade for {nationA}-{nationB} (year {year})...")

        try:
            response = model.generate_content(prompt)
            # Apply the requested slicing directly
            raw_json_text = response.text.strip()[7:-3]

            # Attempt to parse the extracted JSON string
            combined_obj = json.loads(raw_json_text)

            # Ensure it's actually a dictionary now
            if not isinstance(combined_obj, dict):
                raise ValueError("Parsed JSON is not a dictionary object.")

            # We expect top-level "sentimentData" and "tradeData"
            if "sentimentData" not in combined_obj or "tradeData" not in combined_obj:
                raise ValueError("Response missing 'sentimentData' or 'tradeData' at top-level.")

            # Attempt to get sentimentData, fallback to extracting from single-item list
            sentiment_val = combined_obj["sentimentData"]
            if isinstance(sentiment_val, list) and len(sentiment_val) == 1 and isinstance(sentiment_val[0], dict):
                print(f"  Warning: sentimentData for {nationA}-{nationB} was a single-item list, extracting object.")
                sentiment_obj = sentiment_val[0]
            elif isinstance(sentiment_val, dict):
                sentiment_obj = sentiment_val
            else:
                raise ValueError(f"sentimentData for {nationA}-{nationB} is neither a dictionary nor a single-item list of a dictionary.")

            # Attempt to get tradeData, fallback to extracting from single-item list
            trade_val = combined_obj["tradeData"]
            if isinstance(trade_val, list) and len(trade_val) == 1 and isinstance(trade_val[0], dict):
                print(f"  Warning: tradeData for {nationA}-{nationB} was a single-item list, extracting object.")
                trade_obj = trade_val[0]
            elif isinstance(trade_val, dict):
                trade_obj = trade_val
            else:
                raise ValueError(f"tradeData for {nationA}-{nationB} is neither a dictionary nor a single-item list of a dictionary.")

            # Optional further validation
            # if sentiment_obj.get("nationA") != nationA or trade_obj.get("nationA") != nationA:
            #     raise ValueError("Nation name mismatch after extraction.")

            return sentiment_obj, trade_obj

        except (json.JSONDecodeError, ValueError) as e: # Catch both parsing and validation errors
            print(f"  [ERROR] Parsing/Validation for {nationA}-{nationB} combined (Attempt {attempt}/{max_attempts}): {e}")
            print(f"  Raw AI output was:\n{raw_output}") # Show the problematic output
            if attempt == max_attempts:
                 print("  [FAILURE] Max attempts reached after parsing/validation error.")
                 break # Exit loop, will return fallback data
            # print("  Waiting 2 seconds before retrying...")
            # time.sleep(2)

        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"  [ERROR] Rate limit hit for model '{model_name}' (Attempt {attempt}/{max_attempts}): {rate_limit_error}")
            if attempt == max_attempts:
                 print(f"  [FAILURE] Max attempts reached for model '{model_name}' after rate limit error.")
                 break # Exit loop, will return fallback data

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
            # Catch other potential errors during generation
            print(f"  [ERROR] Unexpected error during generation (Attempt {attempt}/{max_attempts}): {type(e).__name__} - {e}")
            if attempt == max_attempts:
                 print("  [FAILURE] Max attempts reached after unexpected error.")
                 break # Exit loop, will return fallback data
            # print("  Waiting 5 seconds before retrying...")
            # time.sleep(5)

    # If all attempts fail, return fallback structures
    print("  [FAILURE] Reached max attempts. Returning fallback data.")
    fallback_sentiment = {
        "nationA": nationA,
        "nationB": nationB,
        "diplomaticRelations": "Neutral",
        "economicTrust": 50,
        "militaryTensions": 50,
        "ideologicalAlignment": "Neutral",
        "relevantEvents": []
    }
    fallback_trade = {
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
    return fallback_sentiment, fallback_trade

###############################################################################
#                   BUILD COMBINED DATA FOR ALL PAIRS (PARALLELIZED)          #
###############################################################################

def build_combined_relations(nations, year,
                             sentiment_schema_text,
                             trade_schema_text,
                             model, max_workers=10):
    """
    Generates combined sentiment and trade data for all unique pairs of nations in parallel.

    :param nations: List of nation names.
    :param year: The reference year.
    :param sentiment_schema_text: Sentiment schema text.
    :param trade_schema_text: Trade schema text.
    :param model: The configured AI model instance.
    :param max_workers: Maximum number of threads for parallel execution.
    :return: A tuple containing two lists: (list_of_sentiment_dicts, list_of_trade_dicts).
    """
    sentiment_relations = []
    trade_relations = []
    nation_pairs = list(combinations(nations, 2)) # Generate all unique pairs
    relation_id_counter = 1 # Counter for generating unique relation IDs

    print(f"\nStarting parallel combined sentiment/trade generation for {len(nation_pairs)} pairs using up to {max_workers} workers...")

    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks for each pair
        for nationA, nationB in nation_pairs:
            relation_id = f"rel-{relation_id_counter}"
            relation_id_counter += 1
            print(f"  Submitting task for combined data: {nationA} and {nationB} (ID: {relation_id})...")
            future = executor.submit(
                fetch_combined_data_for_pair,
                nationA,
                nationB,
                year,
                relation_id,
                sentiment_schema_text,
                trade_schema_text,
                model
            )
            futures.append(future)

        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            try:
                sentiment_obj, trade_obj = future.result() # Unpack the tuple
                if sentiment_obj and trade_obj: # Check if fallbacks weren't returned
                    sentiment_relations.append(sentiment_obj)
                    trade_relations.append(trade_obj)
                    print(f"  Collected combined data for {sentiment_obj.get('nationA', '?')}-{sentiment_obj.get('nationB', '?')}")
            except Exception as exc:
                # Log exceptions from threads if needed
                print(f'!!! Thread for combined data generation raised an exception: {exc}')

    print(f"\n--- Parallel Combined Data Generation Summary ---")
    print(f"Total sentiment relations generated: {len(sentiment_relations)}")
    print(f"Total trade relations generated: {len(trade_relations)}")
    # Could add more summary details if needed

    return sentiment_relations, trade_relations

###############################################################################
#                      SAVE SENTIMENT & TRADE FILES SEPARATELY                #
###############################################################################

def save_global_sentiment(sentiment_data, filename="global_sentiment.json"):
    """
    Saves the final array of sentiment relations to JSON.
    """
    if not sentiment_data:
        print("No sentiment data to save.")
        return
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(sentiment_data, f, indent=2)
    print(f"Saved {len(sentiment_data)} sentiment items to {filename}")

def save_trade_relations(trade_data, filename="global_trade.json"):
    """
    Saves the final array of trade relations to JSON.
    """
    if not trade_data:
        print("No trade data to save.")
        return
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(trade_data, f, indent=2)
    print(f"Saved {len(trade_data)} trade items to {filename}")

###############################################################################
#                                   MAIN                                      #
###############################################################################

def main():
    """
    Example usage: 
    We'll load the two schemas, pick a set of nations, do a single AI call 
    per pair, parse out the 'sentiment' vs. 'trade' data, and save them separately.
    """
    # 1) Configure the AI model
    global model
    model = configure_genai(temp=0.5, model="gemini-2.0-flash")

    # 2) Load the two schemas
    sentiment_schema_text = load_schema_text("global_subschemas/global_sentiment_schema.json")
    trade_schema_text = load_schema_text("global_subschemas/global_trade_schema.json")

    # 3) Example data
    nations = ["US", "UK", "USSR"]
    year = 1985

    # 4) Build combined data
    sentiment_list, trade_list = build_combined_relations(
        nations=nations,
        year=year,
        sentiment_schema_text=sentiment_schema_text,
        trade_schema_text=trade_schema_text,
        model=model
    )

    # 5) Save them into separate files
    save_global_sentiment(sentiment_list, "global_sentiment.json")
    save_trade_relations(trade_list, "global_trade.json")

def initialize_combined(nations: list, year: str, max_workers=10):
    """
    Initializes combined global sentiment and trade data in parallel and saves them.
    """
    global model # Ensure model is configured and accessible globally or passed down
    model = configure_genai(temp=0.5, model="gemini-2.0-flash") # Configure the model used by threads

    sentiment_schema_text = load_schema_text("global_subschemas/global_sentiment_schema.json")
    trade_schema_text = load_schema_text("global_subschemas/global_trade_schema.json")

    print(f"Initializing combined sentiment & trade for {len(nations)} nations (Year: {year})...")
    sentiment_list, trade_list = build_combined_relations(
        nations=nations,
        year=year,
        sentiment_schema_text=sentiment_schema_text,
        trade_schema_text=trade_schema_text,
        model=model,
        max_workers=max_workers
    )

    output_dir = f"simulation_data/generated_timeline_{year}/"
    os.makedirs(output_dir, exist_ok=True) # Ensure directory exists
    save_global_sentiment(sentiment_list, os.path.join(output_dir, "global_sentiment.json"))
    save_trade_relations(trade_list, os.path.join(output_dir, "global_trade.json"))

    return sentiment_list, trade_list


def initialize_combined(nations: list, year: str, max_workers=10):
    """
    Initializes combined global sentiment and trade data in parallel,
    populates relevant events in the sentiment data, and saves them.

    Requires global_events.json to exist in the same directory as the output files.
    """
    global model # Ensure model is configured and accessible globally or passed down
    model = configure_genai(temp=0.5, model="gemini-2.0-flash") # Configure the model used by threads
    relevance_model = configure_genai(temp=0.5, model="gemini-2.0-flash") # Separate model/config for relevance if desired

    sentiment_schema_text = load_schema_text("global_subschemas/global_sentiment_schema.json")
    trade_schema_text = load_schema_text("global_subschemas/global_trade_schema.json")

    print(f"Initializing combined sentiment & trade for {len(nations)} nations (Year: {year})...")
    # Step 1: Build relations with empty relevantEvents
    sentiment_list, trade_list = build_combined_relations(
        nations=nations,
        year=year,
        sentiment_schema_text=sentiment_schema_text,
        trade_schema_text=trade_schema_text,
        model=model,
        max_workers=max_workers
    )

    # --- Post-processing Step for Sentiment ---
    output_dir = f"simulation_data/generated_timeline_{year}/"
    os.makedirs(output_dir, exist_ok=True) # Ensure directory exists
    global_events_path = os.path.join(output_dir, "global_events.json")
    global_events = []
    if os.path.exists(global_events_path):
        try:
            with open(global_events_path, "r", encoding="utf-8") as f:
                global_events = json.load(f)
            print(f"Loaded {len(global_events)} global events for relevance check.")
            # Step 2: Populate relevant events using the loaded global events and relevance model
            populate_relevant_events(sentiment_list, global_events, relevance_model, max_workers)
        except Exception as e:
            print(f"Error loading or processing global events from {global_events_path}: {e}")
            print("Skipping population of relevantEvents.")
    else:
        print(f"Warning: Global events file not found at {global_events_path}. Cannot populate relevantEvents.")

    # Step 3: Save the updated sentiment and the trade data
    save_global_sentiment(sentiment_list, os.path.join(output_dir, "global_sentiment.json"))
    save_trade_relations(trade_list, os.path.join(output_dir, "global_trade.json"))

    return sentiment_list, trade_list

if __name__ == "__main__":
    # Example of calling the parallelized initialization
    example_nations = ["US", "UK", "USSR", "China", "France", "West Germany"]
    example_year = "1985"
    example_workers = 6 # Adjust based on system/API limits

    # Call the main initialization function
    initialize_combined(
        nations=example_nations,
        year=example_year,
        max_workers=example_workers
    )

    # Note: The original main() function is kept above but is no longer the primary entry point
    # if this script is run directly due to the __name__ == "__main__": block above.
    # You might want to remove or comment out the old main() if it's redundant.
