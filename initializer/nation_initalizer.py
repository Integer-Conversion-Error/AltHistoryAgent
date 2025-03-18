#!/usr/bin/env python3

import sys, os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(parent_dir)

from writers import low_level_writer

import os,time
import json
import google.generativeai as genai
from typing import Dict
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
        model_name="gemini-2.0-flash-thinking-exp-01-21",
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

            if end_time <= 6:
                time.sleep(6 - end_time)
                print(f"Extra Wait: {6 - end_time:.2f}s")

            print(f"Adding subfield {subfield} for nation {country_name}")
            return response.text.strip()

        except Exception as e:
            print(f"Error occurred: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds... (Attempt {attempt + 2}/{max_retries})")
                time.sleep(retry_delay)
            else:
                print("Maximum retry attempts reached. Skipping this request.")
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
    
    #countries = ["United States of America", "Soviet Union", "United Kingdom"]
    time_period = "1975"


    
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


        

    # If you wanted, you could now store all_nations_data as JSON in a file.



def nation_init_main(
    countries: list = ["Germany", "Soviet Union"],
    time_period: str = "1965"
):
    """
    Initializes nation data and saves it in a structured format within the simulation_data folder.
    Each simulation instance is stored under 'simulation_data/Simulation_<Time-Period>/nations/<Country>/'
    
    :param countries: List of country names to initialize.
    :param time_period: The historical time period for the scenario.
    """
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

    # Define the directory structure for this simulation instance
    simulation_dir = os.path.join("simulation_data", f"generated_timeline_{time_period}")
    nations_dir = os.path.join(simulation_dir, "nations")
    os.makedirs(nations_dir, exist_ok=True)

    print(f"\nInitialized simulation directory: {simulation_dir}")

    # Store all nations' data
    all_nations_data = {}

    for country_name in countries:
        start_time = time.time()
        print(f"\nProcessing data for {country_name}...")

        # Create a directory for the country within the simulation instance
        country_dir = os.path.join(nations_dir, country_name)
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



        

    # If you wanted, you could now store all_nations_data as JSON in a file.


if __name__ == "__main__":
    main()
