import os
import json
import google.generativeai as genai

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


def generate_json_object(model, json_schema, action, context):
    """
    Use AI to generate a JSON object following the schema.
    """
    prompt = ""#generate_object_prompt(json_schema, action, context)
    response = model.generate_content(prompt)

    try:
        generated_json = json.loads(response.text[7:-3])
        return generated_json
    except json.JSONDecodeError:
        print("Error: AI did not return valid JSON.")
        print(response)
        return None

## Find what events are due to transpire due to current global status + user input
    ## Generate high-level actions based on this (e.g. adding conflict event, creating strategic interest, etc.)
    ## Check across all schemas to see if anything needs to be updated.
## See about what to do with high-level actions
## Decided required context (?)
## Get all context  (or just required context?)
    ## Get JSON elements by keyword (e.g nation name, nation in region, etc.)
## Seperate paragraph form context to different sections of schemas. 
    ## Also seperate based on nations
    
    
## Notes: 
    ## Avoid situations where the entire JSON data is being fed into the AI and is asked to change some part and return the new part. Handle DB operations outside genAI api. (Maybe direct them using a reasoning model though.)
    ## Learn to query objects based on some key (e.g. based on nation name).
    ## Maybe add narration of certain items?