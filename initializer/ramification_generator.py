#!/usr/bin/env python3

"""
ramification_generator.py

This script demonstrates how to generate a structured list of "effects" from a list
of "ramifications" using an AI model, closely following the pattern used by
`fetch_nation_events_brief` (but here we name it `fetch_nation_effects_brief`).

Core Features:
- Loads and configures the Gemini (PaLM) API via `google.generativeai`.
- Gathers a list of "ramifications" (e.g., economic or political events).
- Prompts the AI model to generate effects in strictly valid JSON, adhering
  to strict domain separation and maximizing coverage of each domain's fields.
- Demonstrates domain-based splitting of "impactedFields" so that no effect
  crosses multiple domains.
- Offers a sample test function, `test_fetch_and_save_nation_effects`, showing
  how to feed data to the model, parse the JSON response, and optionally save
  each effect as a separate JSON file for further use.

The returned results are printed for verification and can also be saved or
processed further (as JSON).
"""

import sys
import os
import json
import re # For parsing retry delay
import time
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
from initializer_util import *
###############################################################################
#                           CONFIG & MODEL SETUP                              #
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
        "temperature": 0.7,  # Balanced randomness
        "top_p": 0.95,
        "top_k": 40
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
    )
    return model

###############################################################################
#                FUNCTION TO GENERATE EFFECTS FROM RAMIFICATIONS             #
###############################################################################

def split_effects_by_domain(effects):
    """
    Ensures that each effect only contains impacted fields from a single domain.
    If an effect contains fields from multiple domains, it is split into separate effects.

    :param effects: List of effect dictionaries as returned by the AI.
    :return: A new list of effects, with each effect restricted to a single domain.
    """

    # Define domains and valid field prefixes
    domains = {
        "Internal Affairs": "Internal Affairs",
        "External Affairs.diplomacy": "External Affairs.diplomacy",
        "External Affairs.government": "External Affairs.government",
        "External Affairs.military": "External Affairs.military",
        "External Affairs.technology": "External Affairs.technology"
    }

    processed_effects = []

    for effect in effects:
        effect_name = effect.get("effectName", "Unnamed Effect")
        description = effect.get("description", "")
        impacted_fields = effect.get("impactedFields", [])

        # Categorize fields by domain
        domain_fields = {domain: [] for domain in domains}

        for field in impacted_fields:
            matched = False
            for domain, prefix in domains.items():
                if field.startswith(prefix):  # Check if the field belongs to a known domain
                    domain_fields[domain].append(field)
                    matched = True
                    break
            if not matched:
                print(f"Warning: Field '{field}' does not match any known domain!")

        # Create separate effects per domain
        for domain, fields in domain_fields.items():
            if fields:  # If this domain has any fields, create a new effect
                new_effect = {
                    "effectName": f"{effect_name} ({domain})",
                    "description": description,
                    "impactedFields": fields
                }
                processed_effects.append(new_effect)

    return processed_effects


def fetch_nation_effects_brief(model, ramifications, nation_context, nation_schema):
    """
    Asks the AI model for a JSON array of "effects" on a nation, given:
     - a list of ramifications (with type, severity, description, etc.)
     - a paragraph of contextual information about the nation
     - a textual "nation schema" describing which fields or dimensions can be affected.

    The final output must be strictly valid JSON containing only an array of
    effect objects. Each effect object could look like:
    
      [
        {
          "effectName": "Name of effect",
          "description": "Short explanation of how it impacts the nation",
          "impactedFields": ["List", "Of", "Affected", "Schema Fields"]
        },
        ...
      ]
    
    Returns:
        A Python list of these effect dictionaries. Returns an empty list if
        parsing fails or if the AI does not produce the desired format.
    """

    # Build a prompt with instructions:
    # 1. Provide nation context & schema
    # 2. Provide the list of ramifications (as text)
    # 3. Request a valid JSON array of "effects"
    # 4. Each effect states "what changes" and "which parts of the nation schema" are impacted.
    
    # Convert the ramifications dicts to text for the prompt.
    # You could also provide them in a JSON format, but here we'll flatten them into lines.
    ramifications_text = ""
    for i, r in enumerate(ramifications):
        ram_type = r.get("ramificationType", "")
        severity = r.get("severity", "")
        desc = r.get("description", "")
        timeframe = r.get("timeframe", "Not specified")
        affected = ", ".join(r.get("affectedParties", [])) or "Not specified"
        
        ramifications_text += f"\nRAMIFICATION #{i+1}:\n" \
                              f"Type: {ram_type}\n" \
                              f"Severity: {severity}\n" \
                              f"Description: {desc}\n" \
                              f"Timeframe: {timeframe}\n" \
                              f"Affected Parties: {affected}\n"

    prompt = f"""
You are an expert scenario analyst.

Here is the current NATION CONTEXT:
{nation_context}

Here is the NATION SCHEMA, describing valid parts of the nation's status:
{nation_schema}

Now, consider the following RAMIFICATIONS:
{ramifications_text}

Task:
1. Generate a strictly valid JSON array of "effects" that result from the above ramifications.
2. Each effect must be concise, specifying:
   - "effectName": A short label for the effect.
   - "description": A brief explanation of how it impacts the nation.
   - "impactedFields": A list of which fields from the nation schema are affected.
   
Make sure:
- The final output is ONLY a JSON array of objects, with no extra text or keys.
- Each object includes exactly "effectName", "description", and "impactedFields".


    "impactedFields" Accuracy & Exhaustiveness:
        Each effect must reference only valid or plausible fields from the NATION SCHEMA.
        Ensure all affected fields for a given effect are included—do not omit any relevant fields.
        Be as comprehensive and exhaustive as possible when identifying impacted fields.

    Multiple Effects Per Ramification:
        Each ramification can produce multiple distinct effects rather than a single broad one.
        If an effect impacts different domains, it must be split into separate effects.

    Strict Domain Separation:
        Each effect must have its "impactedFields" limited to only one of the following major domains:
            Internal Affairs (all internal affairs can be grouped together)
            External Affairs.diplomacy
            External Affairs.government
            External Affairs.military
            External Affairs.technology
        No effect should mix fields from multiple domains.
        If an effect spans multiple domains, split it into two or more effects, each confined to a single domain.

    Example:
    If a political crisis affects both Internal Affairs (e.g., public trust, governance stability) and External Affairs.diplomacy (e.g., foreign relations, treaty obligations), then:
    Split into two separate effects:

        Effect 1 (Internal Affairs.): "Public trust in government declines, reducing domestic political stability."
        Effect 2 (External Affairs.diplomacy): "Foreign nations express concern, leading to reduced diplomatic cooperation."

### **Expanded Guidelines for Impacted Fields**  

1. **Maximize Field Coverage Per Effect (While Remaining Coherent):**  
   - Each effect should impact multiple related fields whenever logically appropriate.  
   - Do not limit effects to a single field unless absolutely necessary—include all relevant consequences.  
   - However, all fields within an effect must be meaningfully connected (i.e., they should naturally change together due to the same cause).  

2. **Group Related Fields Together:**  
   - An effect should include multiple impacted fields from the same domain (e.g., Internal Affairs, External Affairs.diplomacy, etc.).  
   - If multiple distinct consequences occur, list all applicable fields within that domain under the "impactedFields" array.  
   - Example: If a trade war affects both "exportRevenue" and "industrialOutput," list both fields together in the same effect, instead of creating separate ones.  

3. **Avoid Over-Simplification:**  
   - Do not generate single-field effects unless absolutely necessary.  
   - Instead, combine related economic, political, social, or military consequences into richer, multi-field effects.  
   - Example: Instead of just "economicGrowth", an economic downturn might also affect "employmentRate", "publicSentiment", and "taxRevenue".  

4. **Logical Field Expansion:**  
   - Consider secondary and tertiary effects when selecting impacted fields.  
   - Ask: "If this field is affected, what else in the nation would logically change as a result?"  
   - Example: If a government collapses:  
     - "governmentStability" (Direct effect)  
     - "foreignInvestmentConfidence" (Economic ripple effect)  
     - "militaryLoyaltyIndex" (If the military intervenes)  
     - "mediaFreedom" (Potential censorship or propaganda shift)  

5. **Enforce Domain Separation While Expanding Fields:**  
   - Each effect must belong to a single domain (e.g., Internal Affairs, External Affairs.military).  
   - If an effect crosses domains, split it into two separate effects, but ensure each one still contains multiple logically related fields.  

---

### **Example Before & After Applying These Rules**  

**Incorrect (Too Few Fields, Over-Simplified)**  
Effect Name: Economic Decline  
Description: A major trade partner imposes tariffs, reducing exports.  
Impacted Fields: ["exportRevenue"]  

**Problem:** Only one field is listed when logically, multiple aspects of the economy would be affected.  

---

**Correct (Expanded Field Coverage, Logically Related Fields)**  
Effect Name: Trade War Impact on Economy  
Description: A major trade partner imposes tariffs, leading to reduced exports, falling industrial production, and declining investor confidence.  
Impacted Fields: ["Internal Affairs.exportRevenue", "Internal Affairs.industrialOutput", "Internal Affairs.foreignInvestmentConfidence", "Internal Affairs.currencyStability"]  

**Why It Works:**  
- Multiple related fields are impacted by the same economic event.  
- Ensures broader coverage while keeping fields logically connected.  

---



Each effect must impact multiple relevant fields within a single domain, ensuring logical coherence. Avoid overly simple effects—always consider secondary and tertiary consequences when selecting fields. If a field changes, ask what else would logically shift alongside it. However, never mix fields from different domains in the same effect—split them instead.
    """

    # We'll implement a retry mechanism similar to your existing approach.
    attempt = 0
    max_attempts = 15
    while attempt < max_attempts:
        try:
            response = model.generate_content(prompt)
            raw_output = response.text.strip()[7:-3]  # The raw text from the AI
            print("\n--- AI RAW OUTPUT ---")
            print(raw_output)
            print("--- END AI RAW OUTPUT ---\n")

            # Try to parse the AI output as JSON
            parsed_effects = split_effects_by_domain(json.loads(raw_output))
            print(json.dumps(parsed_effects, indent=2))
            if not isinstance(parsed_effects, list):
                print(f"Attempt {attempt + 1}: AI did not return a JSON array. Retrying...")
                attempt += 1
                time.sleep(5)
                continue

            # Optional validation: confirm minimal keys in each effect
            validated_effects = []
            for eff in parsed_effects:
                if (
                    isinstance(eff, dict)
                    and all(k in eff for k in ["effectName", "description", "impactedFields"])
                ):
                    validated_effects.append(eff)
                else:
                    print(f"Warning: An effect is missing required keys or is not a dict:\n{eff}")

            return validated_effects

        except json.JSONDecodeError:
            print(f"Attempt {attempt + 1}: Failed to parse AI output as valid JSON. Retrying...")
            attempt += 1
            print(f"Attempt {attempt + 1}: Failed to parse AI output as valid JSON. Retrying...")
            attempt += 1
            if attempt == max_attempts: break
            # print("Waiting 5 seconds before retrying...")
            # time.sleep(5)
        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' fetching effects (Attempt {attempt + 1}/{max_attempts}): {rate_limit_error}")
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

    print("Max attempts reached. Returning empty list.")
    return []

###############################################################################
#                     OPTIONAL: SAVE EFFECTS TO JSON FILES                    #
###############################################################################

def save_effects_as_json(effects, nation_name, save_path="simulation_data/effects"):
    """
    Saves all effects in a single JSON file as an array.
    If a file already exists, it merges new effects with existing ones, avoiding duplicates.

    :param effects: List of effect dictionaries.
    :param nation_name: The name of the nation for which effects are generated.
    :param save_path: Directory where the JSON file will be saved.
    """
    if not effects:
        print(f"No effects to process for {nation_name}.")
        return

    os.makedirs(save_path, exist_ok=True)

    file_name = f"{nation_name}_effects.json"
    file_path = os.path.join(save_path, file_name)

    # Load existing effects if the file already exists
    existing_effects = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_effects = json.load(f)
                if not isinstance(existing_effects, list):
                    existing_effects = []
        except (json.JSONDecodeError, IOError):
            print(f"Warning: Failed to read existing effects from {file_path}. Overwriting file.")

    # Merge effects, ensuring no duplicates
    combined_effects = {json.dumps(effect, sort_keys=True) for effect in (existing_effects + effects)}
    merged_effects = [json.loads(effect) for effect in combined_effects]

    # Save the merged effects back to the file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(merged_effects, f, indent=2)

    print(f"Saved {len(merged_effects)} unique effects to: {file_path}")
    return merged_effects



def load_nation_schema(file_path="nation_schema_plain.txt"):
    """
    Loads the nation schema string from a plain text file.

    :param file_path: The path to the file containing the nation schema.
    :return: A string containing the nation schema.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"Error: {file_path} not found. Please create the file with the necessary schema information."
        )

    with open(file_path, "r", encoding="utf-8") as file:
        return file.read().strip()

###############################################################################
#                         TESTING / DEMO FUNCTION                             #
###############################################################################

def test_fetch_and_save_nation_effects():
    """
    Demonstrates usage of `fetch_nation_effects_brief` with sample data,
    and then saves the results as JSON files.
    """
    # 1. Configure the AI model
    model = configure_genai()

    sample_ramifications = [
    {
        "ramificationType": "Economic",
        "severity": "Moderate (Significant disruption, requiring policy changes or resource allocation)",
        "affectedParties": ["U.S. manufacturing sector", "Global supply chains", "Consumers"],
        "description": "The U.S.-China trade war escalates with increased tariffs on Chinese imports, leading to disruptions in global supply chains and rising costs for American manufacturers.",
        "timeframe": "Short-Term (2 weeks to 3 months)"
    },
    {
        "ramificationType": "Political",
        "severity": "High (Broad-scale impact, multiple sectors affected, long recovery needed)",
        "affectedParties": ["UK government", "EU member states", "British businesses"],
        "description": "The Brexit referendum results in the United Kingdom voting to leave the European Union, triggering political uncertainty and requiring extensive trade renegotiations.",
        "timeframe": "Medium-Term (6-12 months)"
    },
    {
        "ramificationType": "Social",
        "severity": "Severe (Extensive damage or upheaval, major intervention required)",
        "affectedParties": ["Healthcare systems", "Global travel industry", "General population"],
        "description": "The COVID-19 pandemic spreads worldwide, overwhelming healthcare systems, shutting down international travel, and causing widespread economic hardship.",
        "timeframe": "Extended Medium-Term (1-2 years, ongoing but reversible impact)"
    },
    {
        "ramificationType": "Environmental",
        "severity": "Critical (Nationwide or international crisis, potentially catastrophic)",
        "affectedParties": ["Amazon rainforest", "Brazilian economy", "Global climate activists"],
        "description": "Massive deforestation in the Amazon rainforest accelerates due to weak environmental regulations, leading to increased global concerns over climate change and biodiversity loss.",
        "timeframe": "Long-Term (2-5 years, lasting structural or policy shifts)"
    },
    {
        "ramificationType": "Military",
        "severity": "Unprecedented (Historic level of disruption, global ramifications)",
        "affectedParties": ["U.S. military", "Afghan civilians", "NATO allies"],
        "description": "The U.S. withdraws from Afghanistan after 20 years of military presence, leading to a rapid Taliban takeover and widespread humanitarian crises.",
        "timeframe": "Very Short-Term (1-2 weeks)"
    }
]

    nation_context_str = (
        "The United States is a global superpower with significant influence over world politics, "
        "economics, and military affairs. It has a strong but complex economy, with major dependencies "
        "on global trade, financial markets, and technological innovation. Politically, the country is "
        "deeply polarized, leading to frequent governmental deadlocks and public unrest over key issues. "
        "Socially, it has a diverse population with ongoing debates over healthcare, immigration, and social justice. "
        "In recent years, the nation has faced major crises, including trade conflicts, pandemics, and foreign policy challenges."
    )


    nation_schema_str = load_nation_schema()

    # 3. Fetch the effects from the AI
    effects = fetch_nation_effects_brief(
        model=model,
        ramifications=sample_ramifications,
        nation_context=nation_context_str,
        nation_schema=nation_schema_str
    )

    # 4. Display the parsed effects
    print(f"\nFetched {len(effects)} effects:")
    for eff in effects:
        print(json.dumps(eff, indent=2))

    # 5. Optionally save to JSON
    save_effects_as_json(effects, nation_name="NationY")

def fetch_and_save_nation_effects(ramifications, nation_name, nation_context, timeline):
    """
    A wrapper function that directly fetches the effects for a given nation's
    ramifications, prints them, and saves them to disk.
    """
    
    nation_schema = load_nation_schema()
    model = configure_genai()
    effects = fetch_nation_effects_brief(
        model,
        ramifications,
        nation_context,
        nation_schema
    )
    print(f"\nFetched {len(effects)} effects for {nation_name}:")
    for eff in effects:
        print(json.dumps(eff, indent=2))

    return save_effects_as_json(effects, nation_name, f"simulation_data/generated_timeline_{timeline}/{nation_name}")
    # return effects

# If run as a script, trigger the test
if __name__ == "__main__":
    test_fetch_and_save_nation_effects()
