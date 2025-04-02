import json
import os
import re # For parsing retry delay
import time
from google.api_core import exceptions as google_exceptions # Import google exceptions
from initializer_util import configure_genai, load_schema_text, save_json

def initialize_global_economy(nations: list, reference_year: str, output_path: str):
    """
    Generates global economy data using an AI model based on the provided schema,
    nations, and reference year.

    Args:
        nations: A list of nation names involved in the simulation.
        reference_year: The starting year for the simulation (e.g., "1975").
        output_path: The full path where the generated global_economy.json should be saved.
    """
    print(f"\n--- Generating Global Economy Data for {reference_year} ---")
    schema_file = "global_economy_schema.json"
    model_name = "gemini-2.0-pro-exp-02-05" # As requested by user

    try:
        # 1. Load the schema text
        schema_text = load_schema_text(schema_file)

        # 2. Configure the AI model
        model = configure_genai(temp=0.7, model=model_name) # Slightly higher temp for more creative economic details

        # 3. Construct the prompt
        # Assign schema text directly, removing backticks to avoid potential linter confusion
        schema_definition_for_prompt = schema_text

        prompt = f"""
Generate a plausible global economic overview for the year {reference_year}, focusing on the interactions and general state relevant to the following nations: {', '.join(nations)}.

Adhere strictly to the JSON schema provided below when generating the data.

**JSON Schema Definition:**
--- START SCHEMA ---
{schema_definition_for_prompt}
--- END SCHEMA ---

**Output Requirements:**
- Provide **ONLY** the JSON object containing the generated economic data.
- The JSON object must perfectly match the structure defined in the schema above.
- **DO NOT** include the schema definition itself in your response.
- **DO NOT** include any introductory text, explanations, apologies, or markdown formatting such as code fences.
- Your entire response should start with `{{` and end with `}}`.

Ensure the generated data reflects plausible global economic conditions and relationships for {reference_year} considering the nations: {', '.join(nations)}. Focus on details like major economic blocs, trade patterns, and market sentiments relevant to that era.
"""

        # 4. Generate content using the AI model
        print(f"Calling AI model ({model_name}) to generate global economy data...")
        # Add retries for potential API issues
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                # Accessing the text content correctly based on Gemini API structure
                if hasattr(response, 'text'):
                    generated_text = response.text
                elif hasattr(response, 'parts') and response.parts:
                     # Handle potential streaming or multi-part response if applicable
                     generated_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                else:
                     # Fallback or error handling if the structure is unexpected
                     print("Warning: Unexpected response structure from AI.")
                     generated_text = str(response) # Or handle as error

                print("AI response received.")
                # Apply the requested slicing directly
                raw_json_text = generated_text.strip()[7:-3]

                # 5. Parse the generated JSON
                economy_data = json.loads(raw_json_text)
                print("Successfully parsed generated JSON.")

                # 6. Save the generated data
                save_json(economy_data, output_path)
                print(f"Successfully generated and saved global economy data to {output_path}")
                return economy_data # Return the generated data

            except json.JSONDecodeError as json_err:
                print(f"Error: Failed to parse AI response as JSON after slicing (Attempt {attempt + 1}/{max_retries}). Error: {json_err}")
                # Print the sliced text that failed parsing
                print("Sliced text causing error:\n", raw_json_text)
                if attempt == max_retries - 1:
                    raise Exception("Failed to generate valid JSON for global economy after multiple retries.") from json_err
                # Wait a bit before retrying JSON parsing errors
                # print("Waiting 2 seconds before retrying...")
                # time.sleep(2)
            except google_exceptions.ResourceExhausted as rate_limit_error:
                model_name_used = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
                print(f"Rate limit hit for model '{model_name_used}' (Attempt {attempt + 1}/{max_retries}): {rate_limit_error}")
                if attempt == max_retries - 1:
                    raise Exception(f"Rate limited on final attempt for model '{model_name_used}': {rate_limit_error}") from rate_limit_error

                # Try to parse retry delay from error metadata or message
                retry_delay = 60 # Default delay for rate limits
                error_message = str(rate_limit_error)
                match = re.search(r'retry_delay.*?seconds:\s*(\d+)', error_message, re.IGNORECASE)
                # Also check common metadata patterns if available (example, adjust if needed)
                if hasattr(rate_limit_error, 'metadata'):
                    metadata = getattr(rate_limit_error, 'metadata', {})
                    # Example check - adjust based on actual metadata structure if known
                    if isinstance(metadata, dict) and 'retryInfo' in metadata and 'retryDelay' in metadata['retryInfo']:
                        delay_str = metadata['retryInfo']['retryDelay'].get('seconds', '0')
                        if delay_str.isdigit():
                            retry_delay = int(delay_str)

                # Fallback to regex search on message if metadata didn't provide it
                elif match:
                    retry_delay = int(match.group(1))

                # print(f"Waiting for {retry_delay} seconds due to rate limit...")
                # time.sleep(retry_delay)

            except Exception as e:
                # Handle other potential errors during generation
                print(f"Error during AI generation (Attempt {attempt + 1}/{max_retries}): {type(e).__name__} - {e}")
                if attempt == max_retries - 1:
                    raise Exception(f"Failed to generate global economy data after multiple retries due to: {e}") from e
                # Wait longer for general errors before retrying
                # print("Waiting 5 seconds before retrying...")
                # time.sleep(5)

    except FileNotFoundError as e:
        print(f"Error: Schema file '{schema_file}' not found. Cannot generate global economy data.")
        raise e
    except Exception as e:
        print(f"An unexpected error occurred during global economy generation: {e}")
        # Optionally save placeholder data or re-raise
        raise e

# Example usage (for testing purposes)
if __name__ == "__main__":
    test_nations = ["USA", "USSR", "West Germany", "Japan"]
    test_year = "1985"
    test_output_dir = "simulation_data/test_economy_output"
    os.makedirs(test_output_dir, exist_ok=True)
    test_output_path = os.path.join(test_output_dir, "global_economy.json")
    initialize_global_economy(test_nations, test_year, test_output_path)
