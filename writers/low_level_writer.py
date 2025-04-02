import os,time
import json
import re # For parsing retry delay
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
        model_name="gemini-2.0-flash-lite",
        generation_config=generation_config,
    )
    return model


def generate_object_prompt(json_schema: dict, action: str, context: str) -> str:
    """
    Generate a structured AI prompt to create a JSON object based on the schema.
    """
    return f"""
    You are an expert in generating structured data for an alternate history scenario. Your task is to:
    
    **1. Follow this JSON schema strictly:**
    {json.dumps(json_schema, indent=2)}

    **2. Create a JSON object that matches this schema exactly.**
    
    **3. Action to perform:**
    {action}

    **4. Additional context:**
    {context}

    **5. Rules to follow:**
    - Generate a fully valid JSON object.
    - Ensure all required fields are present and logically consistent.
    - Use historically plausible or well-reasoned details where necessary. 
    - **Do not explain your response. Only output the JSON object.**
    """


def generate_json_object(model, json_schema, action, context):
    """
    Use AI to generate a JSON object following the schema.
    """
    max_retries = 5 # Allow more retries for this potentially complex generation
    base_retry_delay = 5 # Default delay for general errors

    for attempt in range(max_retries):
        try:
            start_time = time.time()
            prompt = generate_object_prompt(json_schema, action, context)
            response = model.generate_content(prompt)
            # Apply the requested slicing directly
            raw_json_text = response.text.strip()[7:-3]

            generated_json = json.loads(raw_json_text)
            end_time = time.time() - start_time
            print(f"Low-Level Write operation took {end_time:.2f}s (Attempt {attempt + 1}/{max_retries})")

            # Optional: Add a small delay if needed, e.g., to respect stricter rate limits
            # if end_time <= 2:
            #     time.sleep(2.05 - end_time)
            #     print(f"Extra Wait (+50ms): {2.05 - end_time:.2f}s")

            return generated_json # Success

        except json.JSONDecodeError as json_err:
            print(f"Error: AI did not return valid JSON after slicing (Attempt {attempt + 1}/{max_retries}). Error: {json_err}")
            # Print the sliced text that failed parsing
            print("Sliced text causing error:\n", raw_json_text)
            if attempt == max_retries - 1:
                print("Max retries reached after JSON decode error.")
                return None
            # print(f"Waiting {base_retry_delay} seconds before retrying...")
            # time.sleep(base_retry_delay)

        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' (Attempt {attempt + 1}/{max_retries}): {rate_limit_error}")
            if attempt == max_retries - 1:
                print(f"Max retries reached for model '{model_name}' after rate limit error.")
                return None

            # Try to parse retry delay
            retry_delay = 60 # Default delay for rate limits
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
            print(f"Unexpected error during low-level generation (Attempt {attempt + 1}/{max_retries}): {type(e).__name__} - {e}")
            if attempt == max_retries - 1:
                print("Max retries reached after unexpected error.")
                return None
            # print(f"Waiting {base_retry_delay} seconds before retrying...")
            # time.sleep(base_retry_delay)

    # If loop finishes without returning, it means all retries failed
    print("Failed to generate valid JSON object after all retries.")
    return None


def produce_structured_data(json_schema: dict, action: str, context: str):
    """
    Single function that:
      1) Configures the gemini model.
      2) Generates a JSON object (strictly following the given schema)
         based on the provided action and context.
      3) Returns that JSON object (or None if invalid).
    """
    # 1. Configure the AI model
    model = configure_genai()

    # 2. Generate the JSON object
    return generate_json_object(model, json_schema, action, context)

def main():
    """
    Main function to generate a JSON object using AI.
    """
    # 1. Load the AI model
    model = configure_genai()

    # 2. Load JSON Schema from file (default: 'schema.json')
    json_schema_path = "global_subschemas/global_trade_schema.json"

    if not os.path.exists(json_schema_path):
        print(f"Error: {json_schema_path} not found.")
        return

    try:
        with open(json_schema_path, "r", encoding="utf-8") as file:
            json_schema = json.load(file)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON schema format. Error: {e}")
        return

    # 3. Define the action and context
    action = "Generate a historical trade agreement between the Arab Muslim League (AML) and Germany in the 1970s."

    context = (
    "In the 1970s, both the Arab Muslim League (AML) and Germany stood as dominant economic and technological powers, increasingly collaborating to counterbalance Allied Bloc influence. "
    
    "### **Arab Muslim League (AML) Overview (1970s):** "
    "- **Economic Powerhouse:** With a GDP exceeding $2.5 trillion, the AML dominated global energy markets, supplying over 60%% of the world's crude oil. "
    "The AML’s currency, the Dinar, gained international traction, particularly among European nations seeking to reduce reliance on the U.S. dollar. "
    "- **Diplomacy & Military:** The AML strategically used oil as a geopolitical tool, enforcing embargoes on hostile nations while deepening ties with Germany and non-Allied nations. "
    "AML’s military was heavily modernized, boasting advanced missile systems, naval expansion, and a growing aerospace sector. "
    "- **Technological Growth:** Investment in computing, telecommunications, and space programs placed the AML at the forefront of non-Western technological advancement. "
    "AML’s industrial projects, including large-scale infrastructure and energy networks, were fueled by German engineering and industrial machinery. "

    "### **Germany Overview (1970s):** "
    "- **Economic & Industrial Leader:** Germany’s economy, valued at over $3 trillion, was driven by advanced manufacturing, precision engineering, and cutting-edge computing. "
    "Despite post-war rebuilding, Germany had become the world’s second-largest industrial exporter, supplying automobiles, heavy machinery, and electronic systems. "
    "- **Diplomatic Strategy:** As a leading power in the European economic sphere, Germany sought to avoid full dependency on the Allied Bloc while maintaining strategic neutrality. "
    "Deepening ties with the AML allowed Germany to secure energy independence, reinforcing its economic sovereignty. "
    "- **Military & Space Development:** While maintaining a formidable military, Germany prioritized technological supremacy, particularly in aerospace and missile development. "
    "Collaboration with the AML extended into lunar colonization efforts, pushing both nations toward a new phase of space dominance. "
    "- **Energy Dependence & Trade Needs:** With limited domestic oil reserves, Germany heavily relied on AML petroleum to fuel its industrial economy. "
    "In return, Germany supplied the AML with precision-manufactured goods, advanced computing systems, and engineering expertise critical for AML’s rapid industrialization. "

    "### **Trade Agreement Context:** "
    "By the 1970s, AML-German economic relations had matured into a strategic partnership. "
    "AML guaranteed stable, long-term oil and gas supplies to Germany, insulating it from Allied economic pressures. "
    "Germany reciprocated with high-end industrial equipment, vehicles, and computing systems, ensuring AML’s continued technological advancement. "
    "The trade agreement should reflect these mutually beneficial exchanges, AML’s energy leverage, and Germany’s industrial and technological superiority."
    )



    # 4. Generate the JSON object
    generated_json = generate_json_object(model, json_schema, action, context)

    if generated_json:
        print("\n--- Generated JSON Object ---")
        print(json.dumps(generated_json, indent=2))

        # Optionally, save to a file
        with open("generated_object.json", "w", encoding="utf-8") as file:
            json.dump(generated_json, file, indent=2)


if __name__ == "__main__":
    main()
