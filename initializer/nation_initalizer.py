#!/usr/bin/env python3

import sys, os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(parent_dir)

from writers import low_level_writer

import os,time
import json
import re # For parsing retry delay
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
from typing import Dict
import concurrent.futures # Added for parallel processing
from initializer_util import *
###############################################################################
#                             1) Basic Setup                                  #
###############################################################################

def load_config():
    """
    Load API keys and other configurations from config.json.
    """
    config_path = "config.json"
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"{config_path} not found. Please create the file with the necessary configurations."
        )
    with open(config_path, "r") as file:
        return json.load(file)

def configure_genai():
    """
    Configure the generative AI model with API key and settings.
    """
    config = load_config()
    genai.configure(api_key=config["GEMINI_API_KEY"])

    generation_config = {
        "temperature": 0.8,  # Balanced randomness
        "top_p": 0.95,
        "top_k": 40
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
    )
    return model

###############################################################################
#                2) Generating Text for Each Schema Subfield                  #
###############################################################################

def generate_subfield_json_prompt(subfield: str, json_schema: dict,  context: str) -> str:
    """
    Create a prompt that instructs the AI to produce a JSON object for a particular subfield
    (e.g., 'government', 'military', etc.), strictly following the provided JSON schema,
    and incorporating the specified action and additional context.

    The output must be a fully valid JSON object matching the schema.
    """
    return f"""
    You are an expert in generating structured JSON data for a historical scenario.
    Your task is to produce a JSON object for the '{subfield}' section according to the following schema:

    {json.dumps(json_schema, indent=2)}

    Additional context: {context}

    Please output only the JSON object (no explanations or extra text) and ensure that all required
    fields are present and adhere exactly to the schema. Make sure to include the entirety of the enum string selected for a given field, and not just the first word from the given enum's string.
    If a part of the schema is not mentioned directly, get the time period from the additional context provided and find the historically correct value(s) for that part yourself.
    """


def generate_subfield_prompt(country_name: str, time_period: str, subfield: str) -> str:
    """
    Create a short prompt that asks the AI to produce a paragraph about
    a particular subfield (like 'government', 'military', or 'technology'),
    for a given country and time period.
    """
    return f"""
    Write a concise paragraph about the {subfield} of {country_name} during the {time_period}.
    Please include historically plausible details,
    focusing on how the {subfield} works for {country_name}, its key features, and any notable aspects relevant
    to that era. Capture a full, all-encompassing view of the {subfield} of the nation, and make sure everything is historically accurate for the time period of {time_period}.

    Do not produce JSON or bullet points; just a single paragraph of text.
    """

def fetch_paragraph_for_subfield(model, country_name: str, time_period: str, subfield: str) -> str:
    """
    Call the AI to get a single paragraph about this subfield for the
    specified country/time period. Retries up to 3 times if an error occurs.
    """
    max_retries = 30
    retry_delay = 5  # Wait time in seconds before retrying

    for attempt in range(max_retries):
        try:
            start_time = time.time()
            prompt = generate_subfield_prompt(country_name, time_period, subfield)
            response = model.generate_content(prompt)
            end_time = time.time() - start_time

            print(f"Write operation took {end_time:.2f}s")

            # if end_time <= 6:
                # time.sleep(6 - end_time)
                # print(f"Extra Wait: {6 - end_time:.2f}s")

            print(f"Adding subfield {subfield} for nation {country_name}")
            return response.text.strip()

        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' fetching paragraph for {subfield} (Attempt {attempt + 1}/{max_retries}): {rate_limit_error}")
            if attempt == max_retries - 1:
                 print(f"Maximum retry attempts reached for model '{model_name}' after rate limit. Skipping this request.")
                 return f"Error fetching data for {subfield} in {country_name} due to rate limit."

            # Try to parse retry delay
            current_retry_delay = 60 # Default delay
            error_message = str(rate_limit_error)
            match = re.search(r'retry_delay.*?seconds:\s*(\d+)', error_message, re.IGNORECASE)
            if hasattr(rate_limit_error, 'metadata'):
                 metadata = getattr(rate_limit_error, 'metadata', {})
                 if isinstance(metadata, dict) and 'retryInfo' in metadata and 'retryDelay' in metadata['retryInfo']:
                     delay_str = metadata['retryInfo']['retryDelay'].get('seconds', '0')
                     if delay_str.isdigit():
                         current_retry_delay = int(delay_str)
            elif match:
                 current_retry_delay = int(match.group(1))

            print(f"Retrying in {current_retry_delay} seconds... (Attempt {attempt + 2}/{max_retries})")
            # time.sleep(current_retry_delay)

        except Exception as e:
            print(f"Error occurred fetching paragraph for {subfield}: {type(e).__name__} - {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds... (Attempt {attempt + 2}/{max_retries})")
                # time.sleep(retry_delay) # Use the default retry_delay for general errors
            else:
                print("Maximum retry attempts reached after general error. Skipping this request.")
                return f"Error fetching data for {subfield} in {country_name}."

###############################################################################
#           3) High-Level Function to Fill Each Part with Paragraphs         #
###############################################################################

def fill_nation_data_with_paragraphs(model, country_name: str, time_period: str) -> Dict[str, str]:
    """
    For the given country, produce a dictionary containing paragraphs
    for each top-level subfield in the 'nation_schema'.

    For demonstration, we'll just handle these sections from `nation_schema`:
      - "government"
      - "military"
      - "technology" (under externalAffairs)
      - "diplomacy"
      - "crimeLawEnforcement"
      - "demographics"
      - "economicPolicies"
      - "education"
      - "energyAndResources"
      - "healthcare"
      - "infrastructure"

    The result is a dict like:
      {
         "government": "...some paragraph...",
         "military": "...",
         ...
      }
    """

    subfields = [
        "government",##
        "military",##
        "technology",##
        "diplomacy", ##
        "crimeLawEnforcement",
        "demographics",
        "economicPolicies",
        "education",
        "energyAndResources",
        "healthcare",
        "infrastructure"
    ]

    results = {}
    for sf in subfields:
        paragraph = fetch_paragraph_for_subfield(model, country_name, time_period, sf)
        print(f"{sf} - {paragraph}")
        results[sf] = paragraph

    return results
###############################################################################
#                         4) Putting It All Together                          #
###############################################################################
## INCREASE SIZE OF INTERNAL AFFAIRS SCHEMA, MAKE IT LIKE 2000 LINES

# Original main function (kept for reference, but not called by default)
def main():
    model = configure_genai()

    internal_subfields = [
        "crimeLawEnforcement",
        "demographics",
        "economicPolicies",
        "education",
        "energyAndResources",
        "healthcare",
        "infrastructure"
    ]

    # Example countries and time period
    countries = ["West Germany","East Germany", "Finland", "Soviet Union", "France", "United States of America", "United Kingdom", "Japan", "Hungary", "Turkey", "Canada", "Italy","Yugoslavia","Communist China","Taiwan (ROC)","Egypt","Poland","Spain","Portugal","Iran", "South Vietnam","North Vietnam", "South Korea", "North Korea", "Norway", "Sweden", "Saudi Arabia", "India","Pakistan", "Malaysia", "Indonesia", "South Africa", "Israel", "Singapore", "Burma", "Australia","Rhodesia"]
    time_period = "1972"

    # Store all nations' data
    all_nations_data = {}

    for country_name in countries:
        start_time = time.time()
        print(f"\nProcessing data for {country_name}...")

        # Create a directory for the country if it doesn't exist
        country_dir = os.path.join(f"simulation_data/generated_timeline_{time_period}/generated_nations", country_name)
        os.makedirs(country_dir, exist_ok=True)

        # Gather paragraphs for each subfield
        paragraphs_dict = fill_nation_data_with_paragraphs(model, country_name, time_period)
        all_nations_data[country_name] = paragraphs_dict

        # Store internal affairs information in one file
        nation_internal_info = ""

        for sf, para in paragraphs_dict.items():
            print(f"\n--- Generating JSON for {country_name}: {sf} ---")

            if sf in internal_subfields:
                # Accumulate internal affairs information
                nation_internal_info += f"\n{sf}\n{para}"
            else:
                # Map subfields to schemas
                schema_mapping = {
                    "diplomacy": "diplomacy_schema.json",
                    "government": "government_schema.json",
                    "technology": "technology_schema.json",
                    "military": "military_schema.json"
                }
                schema_filename = schema_mapping.get(sf)

                if schema_filename:
                    schema_filepath = os.path.join("nation_subschemas/external_affairs_subschemas", schema_filename)

                    # Load the relevant schema
                    with open(schema_filepath, "r", encoding="utf-8") as file:
                        json_schema = json.load(file)

                    # Generate structured data
                    structured_data = low_level_writer.produce_structured_data(
                        json_schema, generate_subfield_json_prompt(sf, json_schema, para), para
                    )

                    # Save the structured data as a JSON file
                    json_output_path = os.path.join(country_dir, f"{sf}.json")
                    with open(json_output_path, "w", encoding="utf-8") as json_file:
                        json.dump(structured_data, json_file, indent=2)

                    print(f"Saved {sf}.json for {country_name}")

        # Process and save internal affairs as a single JSON
        if nation_internal_info:
            internal_schema_path = os.path.join("nation_subschemas/internal_affairs_subschemas", "internal_affairs_schema.json")
            with open(internal_schema_path, "r", encoding="utf-8") as file:
                internal_json_schema = json.load(file)

            subfields_string = ",".join(internal_subfields)

            # Generate structured internal affairs data
            internal_affairs_data = low_level_writer.produce_structured_data(
                internal_json_schema, generate_subfield_json_prompt(subfields_string, internal_json_schema, nation_internal_info), nation_internal_info
            )

            # Save internal affairs JSON file
            internal_json_output_path = os.path.join(country_dir, "internal_affairs.json")
            with open(internal_json_output_path, "w", encoding="utf-8") as json_file:
                json.dump(internal_affairs_data, json_file, indent=2)

            print(f"Saved internal_affairs.json for {country_name}")
        endtime = time.time() - start_time
        print(f"{country_name} took {endtime:.2f}s")

    print("\nAll countries processed and JSON files saved successfully!")


# Worker function to process a single nation
def process_nation(model, country_name: str, time_period: str, internal_subfields: list, nations_dir: str):
    """
    Processes a single nation: fetches data, generates structured JSON, and saves the final file.
    This function is designed to be run in a separate thread.
    """
    start_time = time.time()
    print(f"Starting processing for {country_name}...")

    try:
        # Gather paragraphs for each subfield
        paragraphs_dict = fill_nation_data_with_paragraphs(model, country_name, time_period)

        # Store generated sub-schema data and accumulated internal info
        generated_sub_data = {}
        nation_internal_info = ""

        # Process paragraphs to generate structured data
        for sf, para in paragraphs_dict.items():
            print(f"--- Generating JSON for {country_name}: {sf} ---")

            if sf in internal_subfields:
                # Accumulate internal affairs information for later processing
                nation_internal_info += f"\n{sf}\n{para}"
            else:
                # Map external affairs subfields to schemas
                schema_mapping = {
                    "diplomacy": "diplomacy_schema.json",
                    "government": "government_schema.json",
                    "technology": "technology_schema.json",
                    "military": "military_schema.json"
                }
                schema_filename = schema_mapping.get(sf)

                if schema_filename:
                    schema_filepath = os.path.join("nation_subschemas/external_affairs_subschemas", schema_filename)
                    try:
                        with open(schema_filepath, "r", encoding="utf-8") as file:
                            json_schema = json.load(file)
                        # Generate structured data for this subfield
                        structured_data = low_level_writer.produce_structured_data(
                            json_schema, generate_subfield_json_prompt(sf, json_schema, para), para
                        )
                        generated_sub_data[sf] = structured_data # Store generated data
                    except FileNotFoundError:
                        print(f"Warning: Schema file not found for {sf} at {schema_filepath} for {country_name}")
                        generated_sub_data[sf] = {} # Add empty dict if schema missing
                    except Exception as e:
                         print(f"Error processing {sf} for {country_name}: {e}")
                         generated_sub_data[sf] = {}

        # Process accumulated internal affairs information
        if nation_internal_info:
            internal_schema_path = os.path.join("nation_subschemas/internal_affairs_subschemas", "internal_affairs_schema.json")
            try:
                with open(internal_schema_path, "r", encoding="utf-8") as file:
                    internal_json_schema = json.load(file)
                subfields_string = ",".join(internal_subfields)
                # Generate structured internal affairs data
                internal_affairs_data = low_level_writer.produce_structured_data(
                    internal_json_schema, generate_subfield_json_prompt(subfields_string, internal_json_schema, nation_internal_info), nation_internal_info
                )
                generated_sub_data["internalAffairs"] = internal_affairs_data # Store generated data
            except FileNotFoundError:
                 print(f"Warning: Internal affairs schema not found at {internal_schema_path} for {country_name}")
                 generated_sub_data["internalAffairs"] = {}
            except Exception as e:
                 print(f"Error processing internal affairs for {country_name}: {e}")
                 generated_sub_data["internalAffairs"] = {}
        else:
             generated_sub_data["internalAffairs"] = {} # Ensure key exists

        # --- Assemble the final nation object conforming to nation_schema.json ---
        nation_data = {}
        # Add basic required fields (placeholders/derived)
        nation_data["nationId"] = country_name.upper().replace(" ", "")[:5] # Simple derived ID
        nation_data["name"] = country_name
        nation_data["abbreviation"] = country_name[:3].upper() # Placeholder
        nation_data["capital"] = "Unknown" # Placeholder - Needs proper data source
        nation_data["GDP"] = "$1 billion" # Placeholder - Needs proper data source
        nation_data["currency"] = "Unknown" # Placeholder - Needs proper data source

        # Add external affairs data
        nation_data["externalAffairs"] = {
            "diplomacy": generated_sub_data.get("diplomacy", {}),
            "government": generated_sub_data.get("government", {}),
            "military": generated_sub_data.get("military", {}),
            "technology": generated_sub_data.get("technology", {})
        }
        # Add internal affairs data
        nation_data["internalAffairs"] = generated_sub_data.get("internalAffairs", {})

        # Add the new required nationwideImpacts array (must be present and empty initially)
        nation_data["nationwideImpacts"] = []

        # --- Save the unified nation JSON file ---
        # Save directly into the nations_dir, named after the country
        unified_nation_path = os.path.join(nations_dir, f"{country_name}.json")
        try:
            with open(unified_nation_path, "w", encoding="utf-8") as json_file:
                json.dump(nation_data, json_file, indent=2)
            print(f"Saved unified nation file: {unified_nation_path}")
        except Exception as e:
            print(f"Error saving unified nation file for {country_name}: {e}")

        endtime = time.time() - start_time
        print(f"Finished processing {country_name} in {endtime:.2f}s")
        return f"Successfully processed {country_name}"

    except Exception as e:
        print(f"!!! Critical error processing {country_name}: {type(e).__name__} - {e}")
        endtime = time.time() - start_time
        print(f"Failed processing {country_name} after {endtime:.2f}s")
        # Optionally re-raise or return an error indicator
        return f"Failed to process {country_name}: {e}"


def nation_init_main(
    countries: list = ["Germany", "Soviet Union"],
    time_period: str = "1965",
    max_workers: int = 10 # Number of nations to process in parallel
):
    """
    Initializes nation data in parallel and saves it in a structured format.
    Each simulation instance is stored under 'simulation_data/generated_timeline_<Time-Period>/nations/'

    :param countries: List of country names to initialize.
    :param time_period: The historical time period for the scenario.
    :param max_workers: Maximum number of threads to use for parallel processing.
    """
    model = configure_genai()

    internal_subfields = [
        "crimeLawEnforcement", # Keep this list definition here
        "demographics",
        "economicPolicies",
        "education",
        "energyAndResources",
        "healthcare",
        "infrastructure"
    ]

    # Define the directory structure for this simulation instance
    simulation_dir = os.path.join("simulation_data", f"generated_timeline_{time_period}")
    nations_dir = os.path.join(simulation_dir, "nations")
    os.makedirs(nations_dir, exist_ok=True)

    print(f"\nInitialized simulation directory: {simulation_dir}")
    print(f"Starting parallel processing for {len(countries)} nations using up to {max_workers} workers...")

    futures = []
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks for each country
        for country_name in countries:
            future = executor.submit(
                process_nation,
                model,
                country_name,
                time_period,
                internal_subfields,
                nations_dir
            )
            futures.append(future)

        # Wait for tasks to complete and collect results/handle errors
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result() # Get the return value from process_nation
                results.append(result)
                print(f"Thread finished: {result}")
            except Exception as exc:
                # This catches exceptions raised within the process_nation function
                print(f'!!! Thread generated an exception: {exc}')
                results.append(f"Error: {exc}") # Log the error

    print("\n--- Parallel Processing Summary ---")
    success_count = sum(1 for r in results if isinstance(r, str) and r.startswith("Successfully processed"))
    failure_count = len(results) - success_count
    print(f"Total nations processed: {len(results)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {failure_count}")
    if failure_count > 0:
        print("Failures:")
        for r in results:
            if isinstance(r, str) and r.startswith("Failed"):
                print(f"- {r}")

    print("\nNation initialization process completed.")


if __name__ == "__main__":
    # Example of how to call the parallelized function
    # Define your list of countries and the time period
    example_countries = ["West Germany","East Germany", "Finland", "Soviet Union", "France", "United States of America", "United Kingdom", "Japan", "Hungary", "Turkey", "Canada", "Italy","Yugoslavia","Communist China","Taiwan (ROC)","Egypt","Poland","Spain","Portugal","Iran", "South Vietnam","North Vietnam", "South Korea", "North Korea", "Norway", "Sweden", "Saudi Arabia", "India","Pakistan", "Malaysia", "Indonesia", "South Africa", "Israel", "Singapore", "Burma", "Australia","Rhodesia"]
    example_time_period = "1985"

    # Call the main initialization function
    nation_init_main(countries=example_countries, time_period=example_time_period, max_workers=150) # Adjust max_workers as needed

    # Note: The original main() function is kept above but is no longer the primary entry point
    # if this script is run directly due to the __name__ == "__main__": block above.
    # You might want to remove or comment out the old main() if it's redundant.
