import os
import json
import time
import google.generativeai as genai

## from intializer_util import *
def load_config():
    """
    Load API keys and other configurations from config.json.
    You need a file named 'config.json' in the same directory, e.g.:
    {
        "GEMINI_API_KEY": "<your-key-here>"
    }
    """
    config_path = "config.json"
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"{config_path} not found. Please create the file with the necessary configurations."
        )
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)

def configure_genai(temp = 0.6,model = "gemini-2.0-flash-exp"):
    """
    Configure the generative AI model with API key and settings.
    """
    config = load_config()
    genai.configure(api_key=config["GEMINI_API_KEY"])

    generation_config = {
        "temperature": temp,    # Balanced randomness
        "top_p": 0.95,
        "top_k": 40
    }

    model = genai.GenerativeModel(
        model_name=model,  # or whichever model you've configured
        generation_config=generation_config
    )
    return model

def load_schema_text(schema_file="notable_characters_schema.json"):
    """
    Reads the entire JSON schema from a file as text, so it can be
    embedded directly in the AI prompt.
    """
    schema_file = "global_subschemas/" + schema_file
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"Schema file '{schema_file}' not found.")

    with open(schema_file, "r", encoding="utf-8") as f:
        return f.read()  # Return the raw JSON text (not parsed)
    
    
def save_json(json_data, filename="notable_characters.json"):
    """
    Saves the final array of characters to a single JSON file.
    Ensures the directory structure exists before saving.
    """
    if not json_data:
        print("No characters to save.")
        return
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # Save the JSON file
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)
    print(f"Saved to {filename}")