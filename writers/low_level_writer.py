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


def generate_object_prompt(json_schema: dict, action: str, context: str) -> str:
    """
    Generate a structured AI prompt to create a JSON object based on the schema.
    """
    return f"""
    You are an expert in generating structured data for an alternate history scenario. Your task is to:
    
    **1. Follow this JSON schema strictly:**
    {json.dumps(json_schema, indent=2).replace('{', '{{').replace('}', '}}')}

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
    prompt = generate_object_prompt(json_schema, action, context)
    response = model.generate_content(prompt)

    try:
        generated_json = json.loads(response.text[7:-3])
        return generated_json
    except json.JSONDecodeError:
        print("Error: AI did not return valid JSON.")
        print(response)
        return None


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
