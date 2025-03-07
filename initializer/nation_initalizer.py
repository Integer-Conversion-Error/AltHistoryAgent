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
        model_name="gemini-2.0-flash-exp",
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
    You are an expert in generating structured JSON data for an alternate history scenario.
    Your task is to produce a JSON object for the '{subfield}' section according to the following schema:
    
    {json.dumps(json_schema, indent=2)}
    
    Additional context: {context}
    
    Please output only the JSON object (no explanations or extra text) and ensure that all required
    fields are present and adhere exactly to the schema.
    """


def generate_subfield_prompt(country_name: str, time_period: str, subfield: str) -> str:
    """
    Create a short prompt that asks the AI to produce a paragraph about 
    a particular subfield (like 'government', 'military', or 'technology'),
    for a given country and time period.
    """
    return f"""
    Write a concise paragraph about the {subfield} of {country_name} during the {time_period}.
    Please include historically plausible or alternate-historical details (1970s era),
    focusing on how the {subfield} works, its key features, and any notable aspects relevant 
    to that era. 
    
    Do not produce JSON or bullet points; just a single paragraph of text.
    """

def fetch_paragraph_for_subfield(model, country_name: str, time_period: str, subfield: str) -> str:
    """
    Call the AI to get a single paragraph about this subfield for the 
    specified country/time period.
    """
    time.sleep(7)
    prompt = generate_subfield_prompt(country_name, time_period, subfield)
    response = model.generate_content(prompt)
    
    print(f"Adding subfield {subfield} for nation {country_name}")
    return response.text.strip()

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
        results[sf] = paragraph

    return results
###############################################################################
#                         4) Putting It All Together                          #
###############################################################################
def main():
    model = configure_genai()
    internal_subfields = ["crimeLawEnforcement",
        "demographics",
        "economicPolicies",
        "education",
        "energyAndResources",
        "healthcare",
        "infrastructure"]
    # Example countries and time period
    countries = ["Germany", "Soviet Russia"]
    time_period = "mid to late 1970s"
    nation_internal_info = ""
    # We'll store the final data in a structure: 
    # { country_name: { subfield1: paragraph, subfield2: paragraph, ... } }
    all_nations_data = {}

    for country_name in countries:
        # Gather paragraphs for each subfield
        paragraphs_dict = fill_nation_data_with_paragraphs(model, country_name, time_period)
        all_nations_data[country_name] = paragraphs_dict

    # Display results
    for c_name, subdict in all_nations_data.items():
        print(f"\n=== {c_name.upper()} ===")
        for sf, para in subdict.items():
            print(f"\n--- {sf.upper()} ---\n{para}\n")
            if sf in internal_subfields:
                nation_internal_info += "\n" + sf + "\n" + para
            else: 
                schemaName = {"diplomacy":"diplomacy_schema.json" ,"government":"government_schema.json","technology":"technology_schema.json","military":"military_schema.json"}
                schemaFilePath = r"nation_subschemas/external_affairs_subschemas/" + schemaName[sf]
                with open(schemaFilePath, "r", encoding="utf-8") as file:
                    json_schema = json.load(file)
                low_level_writer.produce_structured_data(json_schema,generate_subfield_json_prompt(sf,json_schema,para),para) ##nation/external_affairs_subschemas
        
        with open(r"nation_subschemas/internal_affairs_subschemas/internal_affairs_schema.json", "r", encoding="utf-8") as file:
            int_json_schema = json.load(file)
        subfields = internal_subfields[0]
        for field in internal_subfields[1:]:
            subfields += "," + field
        low_level_writer.produce_structured_data(int_json_schema,generate_subfield_json_prompt(subfields,int_json_schema,nation_internal_info),nation_internal_info)##nation/internal_affairs_schema.json

    # If you wanted, you could now store all_nations_data as JSON in a file.


if __name__ == "__main__":
    main()
