import os
import json
import re # For parsing retry delay
import time # For sleep
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions

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


def generate_json_object(model, json_schema, action, context):
    """
    Use AI to generate a JSON object following the schema.
    """
    prompt = "" # Placeholder - This function seems incomplete or unused based on the empty prompt
    # If this function were to be used, the prompt generation needs to be implemented.
    # Assuming it would be similar to other generators:
    # prompt = generate_object_prompt(json_schema, action, context)

    max_retries = 3
    base_retry_delay = 5

    for attempt in range(max_retries):
        try:
            # If the prompt is empty, this will likely fail or return nothing useful.
            # This needs to be addressed if the function is intended to be used.
            if not prompt:
                 print("Error: Prompt is empty in generate_json_object. Cannot call AI.")
                 return None

            response = model.generate_content(prompt)
            text = response.text.strip()

            # Clean potential markdown
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            generated_json = json.loads(text)
            return generated_json # Success

        except json.JSONDecodeError as e:
            print(f"Error: AI did not return valid JSON (Attempt {attempt + 1}/{max_retries}).\nDetails: {e}\nAI Output:\n{text}")
            if attempt == max_retries - 1: break
            # print(f"Waiting {base_retry_delay} seconds before retrying...")
            # time.sleep(base_retry_delay)
        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' (Attempt {attempt + 1}/{max_retries}): {rate_limit_error}")
            if attempt == max_retries - 1:
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
            print(f"Unexpected error during JSON generation (Attempt {attempt + 1}/{max_retries}): {type(e).__name__} - {e}")
            if attempt == max_retries - 1: break
            # print(f"Waiting {base_retry_delay} seconds before retrying...")
            # time.sleep(base_retry_delay)

    # If loop finishes without returning
    print("Failed to generate valid JSON object after all retries.")
    return None



def add_item(json_data, json_path, new_item):
    """
    Adds a new item to a JSON array at the specified path.
    """
    target = navigate_json_path(json_data, json_path)
    if isinstance(target, list):
        target.append(new_item)
        return True
    return False

def remove_item(json_data, json_path, item_identifier):
    """
    Removes an item from a JSON array at the specified path.
    The item_identifier should be a dictionary representing key-value pairs to match.
    """
    target = navigate_json_path(json_data, json_path)
    if isinstance(target, list):
        initial_length = len(target)
        target[:] = [item for item in target if not all(item.get(k) == v for k, v in item_identifier.items())]
        return len(target) < initial_length  # True if item was removed
    return False

def update_item(json_data, json_path, item_identifier, updated_values):
    """
    Updates an item in a JSON array at the specified path.
    The item_identifier should be a dictionary representing key-value pairs to match.
    The updated_values dictionary contains the fields to update.
    """
    target = navigate_json_path(json_data, json_path)
    if isinstance(target, list):
        updated = False
        for item in target:
            if all(item.get(k) == v for k, v in item_identifier.items()):
                item.update(updated_values)
                updated = True
        return updated
    return False

def find_item(json_data, json_path, item_identifier):
    """
    Finds an item in a JSON array at the specified path.
    The item_identifier should be a dictionary representing key-value pairs to match.
    """
    target = navigate_json_path(json_data, json_path)
    if isinstance(target, list):
        return [item for item in target if all(item.get(k) == v for k, v in item_identifier.items())]
    return []

def navigate_json_path(json_data, json_path):
    """
    Navigates a JSON object to the specified path.
    Returns the target JSON array or object.
    """
    if not json_path:
        return json_data
    keys = json_path.split(".")
    target = json_data
    for key in keys:
        if isinstance(target, dict) and key in target:
            target = target[key]
        else:
            return None  # Path does not exist
    return target

def manage_json_queries(json_data, json_path=None, action="find", item=None, item_identifier=None, updated_values=None):
    """
    Manages JSON queries including add, remove, update, and find.
    
    Parameters:
        json_data (dict or list): The JSON object or array.
        json_path (str, optional): The path to the JSON array (dot-separated for nested structures).
        action (str): The action to perform ("add", "remove", "update", "find").
        item (dict, optional): The new item to add (only for "add" action).
        item_identifier (dict, optional): The key-value pair(s) identifying an item (for "remove", "update", "find").
        updated_values (dict, optional): The values to update (only for "update" action).

    Returns:
        Depends on the action:
        - "add": Returns True if added successfully.
        - "remove": Returns True if removed successfully.
        - "update": Returns True if updated successfully.
        - "find": Returns a list of matching items.
    """
    if action == "add" and item:
        return add_item(json_data, json_path, item)
    elif action == "remove" and item_identifier:
        return remove_item(json_data, json_path, item_identifier)
    elif action == "update" and item_identifier and updated_values:
        return update_item(json_data, json_path, item_identifier, updated_values)
    elif action == "find" and item_identifier:
        return find_item(json_data, json_path, item_identifier)
    else:
        raise ValueError("Invalid action or missing required parameters.")
    
    
    
def search_json(json_data, search_value, search_key=None):
    """
    Searches for any occurrences of a given value in a specified key (or all keys) 
    within a nested JSON object or array.

    Parameters:
        json_data (dict or list): The JSON object or array to search.
        search_value (str/int/float/bool): The value to search for.
        search_key (str, optional): The key to search within. If None, searches all keys.

    Returns:
        list: A list of full JSON objects containing the matching value.
    """
    results = []

    def recursive_search(data):
        if isinstance(data, dict):  # If it's a dictionary
            # Check if the specific key contains the search value
            if search_key:
                if search_key in data and data[search_key] == search_value:
                    results.append(data)
            else:
                # Search all keys
                if search_value in data.values():
                    results.append(data)

            # Recursively search within all dictionary values
            for value in data.values():
                recursive_search(value)

        elif isinstance(data, list):  # If it's a list, iterate through elements
            for item in data:
                recursive_search(item)

    recursive_search(json_data)
    return results



## Find what events are due to transpire due to current global status + user input
    ## Generate high-level actions based on this (e.g. adding conflict event, creating strategic interest, etc.)
    ## Check across all schemas to see if anything needs to be updated.
## See about what to do with high-level actions
## Decided required context (?)
## Get all context  (or just required context?)
    ## Get JSON elements by keyword (e.g nation name, nation in region, etc.) DONE
## Seperate paragraph form context to different sections of schemas. 
    ## Also seperate based on nations
    
    
## Notes: 
    ## Avoid situations where the entire JSON data is being fed into the AI and is asked to change some part and return the new part. (Maybe direct them using a reasoning model though.)
        ## Handle DB operations outside genAI api. DONE
    ## Learn to query objects based on some key (e.g. based on nation name). DONE
    ## Maybe add narration of certain items?
