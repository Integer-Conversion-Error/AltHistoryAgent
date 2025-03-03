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


# Schema for the summarization output
flattenedSchema = {
    "title": "SummarizeJSON",
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "title": "A concise summary of the given JSON input."
        }
    },
    "required": ["summary"]
}


def get_schema_details(data, schema_name):
    """
    Retrieves the summary and example of a given schema by name.
    
    Parameters:
        data (dict): The JSON data containing the schemas.
        schema_name (str): The name of the schema to search for.
    
    Returns:
        dict: A dictionary containing 'summary' and 'example', or None if not found.
    """
    schema = next((schema for schema in data["schemas"] if schema["name"] == schema_name), None)
    
    if schema:
        return {"summary": schema.get("summary", "No summary available"), 
                "example": schema.get("example", "No example available")}
    return None

allSchemas = {
  "schemas": [
    {
        "name": "Global Economy",
        "summary": "- **Global GDP**: A string with a leading dollar sign, optional decimal, and 'billion' or 'trillion' suffix (e.g., '$80 trillion').\n- **Stock Market Trends**: Numeric values for major global stock indexes, including:\n    - DowJones\n    - Nasdaq\n    - ShanghaiComposite\n    - EuroStoxx\n- **Major Trade Disputes**: A list of significant international trade disputes.\n- **Global Inflation Rate**: The approximate global inflation rate (a non-negative number representing a percentage).",
        "example": "Global GDP stands at $80 trillion, with the DowJones at 30000, Nasdaq at 14000, ShanghaiComposite at 3500, EuroStoxx at 4000, major trade disputes over tech exports, and a global inflation rate of 3.2%."
    },
    {
        "name": "Global Event",
        "summary": "- **Event Name**: Provide the official or recognized name of the event (e.g., 'Hurricane Alpha').\n- **Date** (YYYY-MM-DD): When the event took place.\n- **Event Type**: The type of event (e.g., 'Natural Disaster', 'Pandemic', 'Conflict').\n- **Location**: Include at least the country. If region or coordinates are given, mention them briefly.\n- **Causes**: The primary triggers or factors that led to the event.\n- **Impact**: A breakdown of affected categories (people, economy, environment, etc.) and relevant quantitative data (e.g., number of affected entities, financial loss).\n- **International Response**: How different nations reacted or assisted.\n- **Long-Term Effects**: Potential or observed lasting changes or consequences following the event.",
        "example": "H5N3 Avian Flu Outbreak (2025-04-01), a pandemic event in Southeast Asia, triggered by a new virus strain, causing severe supply-chain disruptions; impacted 10 million birds, prompted neighboring nations to impose travel restrictions, and is expected to cause long-term ecological imbalances."
    },
    {
        "name": "Conflicts",
        "summary": "- **Active Wars**: List of ongoing, resolved, or ceasefire-status wars, including:\n    - Conflict name\n    - Start date\n    - Status (Ongoing, Ceasefire, Resolved)\n    - Belligerents on each side\n    - Casualty estimates (military & civilian)\n    - Territorial changes if any.\n- **Border Skirmishes**: Minor or severe conflicts along national borders, including:\n    - Nations involved\n    - Severity (Minor, Moderate, Severe)\n    - Casualty count\n    - Current status (Ongoing, Resolved).\n- **Internal Unrest**: Domestic movements causing instability, including:\n    - Movement name\n    - Start date\n    - Cause & affected regions\n    - Government response (Suppressed, Negotiated, Ongoing)\n    - Casualties.\n- **Proxy Wars**: Conflicts influenced by major external powers, including:\n    - Primary backers (nations supporting each side)\n    - Type of support (Military Aid, Economic Aid, Covert Ops, Full Intervention).",
        "example": "The Eurasian Conflict (2022-present), ongoing war between the Eastern Federation and the Central European Coalition; estimated 150,000 military casualties and 400,000 civilian deaths; recent territorial gains by the Federation in the Baltic region; international negotiations stalled despite pressure from neutral nations."
    },
    {
        "name": "Global Sentiment",
        "summary": "- **Nation A & Nation B**: The two countries whose relations are being analyzed.\n- **Diplomatic Relations**: The current state of diplomacy between the nations (Allied, Friendly, Neutral, Tense, Hostile).\n- **Economic Trust**: A percentage (0-100) reflecting confidence in trade and financial cooperation.\n- **Military Tensions**: A percentage (0-100) indicating the level of military hostility or risk of conflict.\n- **Historical Conflicts**: List of past wars, disputes, or crises that have shaped their relationship.\n- **Ideological Alignment**: The degree to which both nations share political or social ideologies (Identical, Similar, Neutral, Divergent, Opposed).\n- **Recent Incidents**: Specific diplomatic, economic, or military events influencing current sentiment, including the name, date, and severity of each incident.",
        "example": "Relations between Nation A and Nation B are currently tense, with economic trust at 45% and military tensions at 70%. Their ideological alignment is divergent, with past conflicts including the Border Crisis of 1987. A recent incident, the 'Trade Sanctions Dispute' on 2024-05-14, had a moderate impact on diplomatic stability."
    },
    {
        "name": "International Organizations",
        "summary": "- **Name & Abbreviation**: Full name and short abbreviation of the organization.\n- **Formation Date**: The date the organization was officially established.\n- **Headquarters**: The city or country where the organization's main office is located.\n- **Member States**: List of countries that are part of the organization.\n- **Organization Type**: The main focus of the organization (Military, Economic, Political, Scientific, Humanitarian).\n- **Primary Objectives**: The key goals and functions the organization seeks to achieve.\n- **Influence Score**: A numerical value (0-100) reflecting the organization's global impact.\n- **Funding Sources**: The organization's annual budget and major financial contributors.\n- **Major Decisions**: Significant policy actions or resolutions, including the decision name, date, and impact summary.",
        "example": "The Global Security Alliance (GSA), a military coalition formed on 1998-07-14, headquartered in Geneva, consists of 32 member states. It aims to coordinate international defense strategies and maintain global stability, with an influence score of 85. Its $150 billion budget is primarily funded by the United States, Germany, and Japan. A major decision in 2023, 'Operation Sentinel,' reinforced security in the Pacific region, deterring hostile actions."
    },
        {
    "name": "Scientific Discoveries",
    "summary": "- **Discovery Name**: The official name or title of the scientific breakthrough.\n- **Date**: The date when the discovery was made or officially announced.\n- **Field**: The area of science the discovery belongs to (Physics, Medicine, Space, AI, Energy).\n- **Impact Level**: The significance of the discovery, categorized as Minor, Moderate, or Revolutionary.\n- **Contributing Nations**: Countries involved in the research or funding of the discovery.",
    "example": "The Quantum Entanglement Communicator (2027-09-15), a revolutionary discovery in Physics, enables faster-than-light encrypted communication. Developed through joint research by the United States, China, and Germany, it has the potential to redefine global cybersecurity and space exploration."
    },
        {
    "name": "Global Strategic Interests",
    "summary": "- **Interest Name**: A brief label for the strategic interest.\n- **Region**: The geographic area where the interest is located (e.g., Persian Gulf, Arctic Circle).\n- **Resource Type**: The primary asset associated with the location (e.g., oil fields, rare earth metals, shipping lane).\n- **Importance Level**: The priority level assigned to the interest (Low, Moderate, High, Critical).\n- **Controlling Entities**: Nations, corporations, or groups currently administering the interest.\n- **Rival Claims**: Other entities or nations that dispute or seek control over this interest.\n- **Strategic Value**: Explanation of why the location or resource is important (e.g., major trade route, military significance).\n- **Potential Conflicts**: Possible geopolitical or economic disputes related to this interest.\n- **Economic Value**: The estimated financial worth of the asset (e.g., $300 billion).\n- **Environmental Concerns**: Potential ecological impact or sustainability issues associated with the interest.",
    "example": "The Arctic Shipping Lanes, a critical strategic interest in the Arctic Circle, provide a vital trade route as ice caps recede. Controlled by Russia and Canada, but disputed by the United States and European Union, the lanes hold an estimated $500 billion in trade value annually. Rising geopolitical tensions and environmental concerns over melting ice caps have fueled diplomatic conflicts."
    },
        {
    "name": "Global Treaties",
    "summary": "- **Name**: The official name of the treaty.\n- **Signing Date**: The date when the treaty was formally signed.\n- **Status**: The current state of the treaty (Active, Violated, Expired).\n- **Nations Involved**: The countries that are parties to the treaty.\n- **Treaty Type**: The primary focus of the treaty (Peace, Economic, Military, Climate, Nuclear).",
    "example": "The Pacific Stability Accord, a military treaty signed on 2010-06-15, remains active with participation from the United States, Japan, and Australia. It aims to maintain regional security and ensure mutual defense commitments."
    },
        {
    "name": "Notable Historical Figures",
    "summary": "- **Full Name**: The complete name of the historical figure.\n- **Aliases**: Alternative names or titles the figure was known by.\n- **Birth Date & Death Date**: The date of birth and, if applicable, the date of death.\n- **Nationality**: The country or region the figure was primarily associated with.\n- **Political Affiliation**: The political party or ideology the individual supported.\n- **Role**: Their primary function in history (e.g., Head of State, Military Leader, Scientist, Revolutionary, etc.).\n- **Major Contributions**: Key achievements, discoveries, or actions that defined their legacy.\n- **Associated Events**: Important historical events they played a role in.\n- **Public Perception**: How they were viewed by the public (e.g., Revered, Controversial, Feared, Unknown, etc.).\n- **Personal Thoughts**: Documented reflections, diaries, or statements providing insight into their thoughts and motivations.\n- **Quotes**: Famous statements or writings attributed to them.\n- **Legacy**: The long-term impact of their actions (e.g., World-changing, Significant, Forgotten).",
    "example": "Alexander Ivanov (1912-1985), a controversial revolutionary and dissident from the Eastern Federation, played a pivotal role in the 1954 People's Uprising. Known for his radical speeches and strategic maneuvers, he was both feared and admired. His legacy remains significant, with many viewing him as a visionary while others see him as a destabilizing force in history."
    }
  ]
}



def generate_summarization_prompt(json_data: dict, summary_item) -> str:
    """
    Create a prompt that asks the model to summarize alternate history JSON data
    in well-structured plaintext without explaining divergences from real history.
    """
    schema = get_schema_details(allSchemas, summary_item)

    return f"""
    You are an expert in analyzing and summarizing historical events from an alternate timeline. Your task is to:
    
    1. Examine the following JSON data, which contains details about historical events:
       {json.dumps(json_data, indent=2).replace('{', '{{').replace('}', '}}')}
    
    2. Write a **concise, structured summary** of the events **exactly as presented** in the data.
    
    3. The summary should be **brief and to the point**, covering:
       {schema["summary"]}

    4. Use a **factual and neutral tone** without adding external context or historical interpretation.

    5. Do not explain how this event differs from real-world history. **Only summarize the information explicitly given in the data.**

    6. Format the summary as a **single, readable sentence per event**, following this structure:
       - _Example:_ **{schema["example"]}**

    7. If multiple events are provided, summarize each one separately in the same format.

    8. Do not format the response in JSON. **Write everything in natural plaintext.**
    
    Begin your summary below:
    """


def configure_genai():
    """
    Configure the generative AI model with API key and settings.
    """
    config = load_config()
    genai.configure(api_key=config["GEMINI_API_KEY"])

    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 40
    }

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash-exp",
        generation_config=generation_config,
    )
    return model


def initialize_summarization_session(model, json_data, schema_type):
    """
    Initialize a "summarization session" with the generative model
    using an initial system prompt approach.
    """
    summarization_session = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"System prompt: {generate_summarization_prompt(json_data, schema_type)} "
                            f"Respond 'Understood.' if you got it."
                        )
                    }
                ],
            },
            {
                "role": "model",
                "parts": [{"text": "Understood."}],
            },
        ]
    )
    return summarization_session


def perform_summarization(summarization_session, json_data, schema_type):
    """
    Automatically generates the summary without user input.
    """
    # Send the summarization request
    response = summarization_session.send_message(generate_summarization_prompt(json_data, schema_type))

    # Display the model's response
    print("\n--- Generated Summary ---")
    print(response.text)
    return response.text


def main():
    """
    Main function to execute the JSON Summarizer.
    """
    # 1. Load config and configure generative AI
    model = configure_genai()

    # 2. Read JSON data from a file (defaults to 'input.json')
    json_file_path = "summarizers/test_summarize.json"

    if not os.path.exists(json_file_path):
        print(f"Error: {json_file_path} not found. Please place a valid JSON file in the directory.")
        return

    try:
        with open(json_file_path, "r", encoding="utf-8") as file:
            json_data = json.load(file)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON format in {json_file_path}. Error: {e}")
        return
    except Exception as e:
        print(f"Error reading {json_file_path}: {e}")
        return

    # 3. Initialize summarization session
    schema_type = "Global Event"
    summarization_session = initialize_summarization_session(model, json_data, schema_type)

    # 4. Generate and display the summary
    perform_summarization(summarization_session, json_data, schema_type)


if __name__ == "__main__":
    main()