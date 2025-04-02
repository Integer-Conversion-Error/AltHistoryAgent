#!/usr/bin/env python3
"""
event_engine.py

Handles condition checking, event creation, and event schema updates
within an alternate history scenario. Integrates with the broader simulation:
- Evaluates the global_state to see if new events or escalations should occur.
- Optionally uses AI to fill in details for newly triggered events.
- Adds triggered events to pending_events.
- Once per simulation step, merges pending_events into the relevant JSON sub-schemas
  (e.g. conflicts, naturalDisasters, politicalEvents, etc.).
- Allows user input to override or remove certain event types.
"""

import os
import os
import json
import datetime
import uuid
import re # For parsing retry delay
import time
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # Import google exceptions
# Import necessary modules for new functionality
from summarizers.lazy_nation_summarizer import load_and_summarize_nation
from writers.generate_event import generate_global_event_json # Assuming we adapt this
# Or potentially: from writers.low_level_writer import produce_structured_data

###############################################################################
#                           1) CONFIG & MODEL SETUP                           #
###############################################################################

def load_config():
    """
    Load API keys and other configurations from config.json.
    This file must include at least {"GEMINI_API_KEY": "<your_key>"}.
    """
    config_path = "config.json"
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"{config_path} not found. Please create the file with the necessary configurations."
        )
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


# Modified configure_genai to accept model name and temp
def configure_genai(model="gemini-2.0-flash", temp=0.8):
    """
    Configure the generative AI model with the loaded API key and recommended generation settings.
    Allows specifying model name and temperature.
    """
    config = load_config()
    genai.configure(api_key=config["GEMINI_API_KEY"])

    generation_config = {
        "temperature": temp,
        "top_p": 0.95,
        "top_k": 40
    }

    model_instance = genai.GenerativeModel(
        model_name=model,
        generation_config=generation_config,
    )
    return model_instance


def generate_object_prompt(json_schema: dict, action: str, context: str) -> str:
    """
    Build a structured AI prompt for generating a JSON object given a particular schema.

    :param json_schema: A dictionary defining the JSON schema to follow.
    :param action: Brief text explaining the event creation or escalation.
    :param context: Additional context describing the scenario.
    :return: A string prompt that instructs the AI to output valid JSON only.
    """
    # Ensure json_schema is serializable, handle potential issues if needed
    try:
        schema_str = json.dumps(json_schema, indent=2)
    except TypeError:
        schema_str = "{ \"error\": \"Schema not serializable\" }"

    return f"""
    You are an expert in generating structured data for an alternate history scenario. Your task is to:
    
    **1. Follow this JSON schema strictly:**
    {schema_str}

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
    Calls the generative AI to produce a JSON object conforming to the provided schema.

    :param model: The generative AI model instance.
    :param json_schema: The JSON schema dict to enforce.
    :param action: The event creation or escalation context.
    :param context: Additional scenario context for the AI.
    :return: Parsed Python dict if successful, else None.
    """
    prompt = generate_object_prompt(json_schema, action, context)
    max_retries = 5 # Allow retries
    base_retry_delay = 5 # Default delay for general errors

    for attempt in range(max_retries):
        try:
            # Increased timeout might be needed for complex generations
            response = model.generate_content(prompt, request_options={'timeout': 120})
            # Apply the requested slicing directly
            # Ensure response.text exists and is long enough before slicing
            if response.text and len(response.text) > 10: # 7 for ```json\n and 3 for \n```
                 raw_json_text = response.text.strip()[7:-3]
            else:
                 raw_json_text = response.text.strip() # Fallback if format is unexpected
                 print("Warning: AI response format might be unexpected. Attempting direct parse.")

            generated_json = json.loads(raw_json_text)
            return generated_json # Success

        except json.JSONDecodeError as e:
            print(f"Error: AI did not return valid JSON object after slicing (Attempt {attempt + 1}/{max_retries}).\nDetails: {e}")
            # Print the sliced text that failed parsing
            print("Sliced text causing error:\n", raw_json_text)
            if attempt == max_retries - 1: break
            # print(f"Waiting {base_retry_delay} seconds before retrying...")
            # time.sleep(base_retry_delay)
        except google_exceptions.ResourceExhausted as rate_limit_error:
            model_name = getattr(model, 'model_name', 'Unknown Model') # Get model name safely
            print(f"Rate limit hit for model '{model_name}' generating JSON object (Attempt {attempt + 1}/{max_retries}): {rate_limit_error}")
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
            print(f"Error during AI generation or parsing (Attempt {attempt + 1}/{max_retries}): {type(e).__name__} - {e}")
            # Consider logging the prompt here for debugging
            # print(f"Prompt causing error:\n{prompt}")
            if attempt == max_retries - 1: break
            # print(f"Waiting {base_retry_delay} seconds before retrying...")
            # time.sleep(base_retry_delay)

    # If loop finishes without returning
    print("Failed to generate valid JSON object after all retries.")
    return None


###############################################################################
#                       2) CONDITION ENGINE & AI MERGE                        #
###############################################################################

class EventEngine:
    """
    The EventEngine checks the global_state for conditions that trigger new events,
    can load state from a directory, and allows searching for events by participant.
    It can also integrate user input to remove or alter pending events.
    Then it merges pending events into the correct sub-schemas, referencing your
    loaded or existing file structure (global_subschemas, etc.).
    """

    def __init__(self, global_state: dict):
        """
        Initialize the EventEngine with the current simulation's global state.

        :param global_state: A dictionary containing keys like 'current_date',
                              'nations', 'conflicts', 'globalEconomy', etc.
        """
        if not isinstance(global_state, dict):
            raise TypeError("global_state must be a dictionary.")

        self.global_state = global_state
        self._validate_and_prepare_state() # Call helper to ensure structure

        self.pending_events = []  # List[dict], new global events to insert in the update phase
        try:
            self.time_step = datetime.datetime.strptime(global_state["current_date"], "%Y-%m-%d")  # Current sim time
        except (KeyError, ValueError) as e:
             print(f"Warning: Could not parse current_date '{global_state.get('current_date')}'. Using current system date. Error: {e}")
             self.time_step = datetime.datetime.now()
             self.global_state["current_date"] = self.time_step.strftime("%Y-%m-%d")


        # Configure the primary AI model (can be overridden in specific calls if needed)
        self.model = configure_genai() # Default model
        # Load schemas needed for AI generation prompts
        self._load_ramification_schema()
        # Load global event schema for user-prompted events
        self._load_global_event_schema()

    @classmethod
    def from_directory(cls, simulation_dir_path: str):
        """
        Class method to initialize EventEngine by loading global_state.json
        from a specified simulation directory.

        :param simulation_dir_path: Path to the simulation directory
                                    (e.g., "simulation_data/generated_timeline_1985").
        :return: An instance of EventEngine.
        :raises FileNotFoundError: If global_state.json is not found.
        :raises json.JSONDecodeError: If global_state.json is invalid.
        """
        global_state_path = os.path.join(simulation_dir_path, "global_state.json")
        print(f"Attempting to load global state from: {global_state_path}")
        if not os.path.exists(global_state_path):
            raise FileNotFoundError(f"Global state file not found at {global_state_path}")

        try:
            with open(global_state_path, "r", encoding="utf-8") as f:
                global_state = json.load(f)
            print("Global state loaded successfully.")
            return cls(global_state) # Call the regular __init__ with loaded data
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from {global_state_path}: {e}")
            raise e
        except Exception as e:
            print(f"An unexpected error occurred loading global state: {e}")
            raise e

    def _validate_and_prepare_state(self):
        """Helper method to ensure required keys and structures exist in global_state."""
        print("Validating and preparing global state structure...")
        # Ensure necessary lists/dicts exist
        required_top_level_keys = [
            "current_date", "nations", "globalEvents", "effects", "ramifications",
            "conflicts", "globalEconomy", "globalSentiment", "globalTrade",
            "notableCharacters", "organizations", "strategicInterests"
        ]
        for key in required_top_level_keys:
            if key not in self.global_state:
                print(f"Warning: Missing top-level key '{key}' in global_state. Initializing default.")
                # Initialize with appropriate default type
                if key.endswith("s") or key in ["globalSentiment", "globalTrade", "globalEvents", "effects", "ramifications"]:
                    self.global_state[key] = []
                else:
                    self.global_state[key] = {} # Default to dict for others like nations, globalEconomy

        # Ensure nations is a dict keyed by nationId
        nations_data = self.global_state.get("nations", {})
        if isinstance(nations_data, list):
             print("Converting nations list to dict...")
             try:
                 # Attempt to use nationId first, fallback to name if nationId is missing
                 nations_dict = {}
                 for n in nations_data:
                     nation_key = n.get("nationId") or n.get("name")
                     if nation_key:
                         nations_dict[nation_key] = n
                     else:
                         print(f"Warning: Nation object missing both 'nationId' and 'name': {n}")
                 self.global_state["nations"] = nations_dict
                 nations_data = nations_dict # Update local reference
             except Exception as e:
                 print(f"Error converting nations list to dict: {e}. Nations data might be malformed.")
                 self.global_state["nations"] = {} # Reset to empty dict on error
                 nations_data = {}

        # Ensure nationwideImpacts list exists within each nation object
        if isinstance(nations_data, dict):
            for nation_id, nation_data in nations_data.items():
                if isinstance(nation_data, dict):
                    nation_data.setdefault("nationwideImpacts", [])
                else:
                    print(f"Warning: Nation data for '{nation_id}' is not a dictionary. Skipping nationwideImpacts check.")
        else:
             print("Warning: 'nations' key does not contain a dictionary. Cannot ensure nationwideImpacts.")

        # Ensure conflicts structure exists
        conflicts_data = self.global_state.setdefault("conflicts", {})
        if isinstance(conflicts_data, dict):
            conflicts_data.setdefault("activeWars", [])
            conflicts_data.setdefault("borderSkirmishes", [])
            conflicts_data.setdefault("internalUnrest", [])
            conflicts_data.setdefault("proxyWars", [])
        else:
            print("Warning: 'conflicts' key is not a dictionary. Resetting to default structure.")
            self.global_state["conflicts"] = {"activeWars": [], "borderSkirmishes": [], "internalUnrest": [], "proxyWars": []}

    def _load_global_event_schema(self):
        """Loads the global event schema needed for AI generation."""
        # Assuming the schema is at the root level relative to where this runs
        # Adjust path if necessary
        schema_path = "global_subschemas/global_event_schema.json"
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                self.global_event_schema = json.load(f)
                # If it's an array schema, store the item schema
                if self.global_event_schema.get("type") == "array" and "items" in self.global_event_schema:
                    self.global_event_item_schema = self.global_event_schema["items"]
                else:
                    self.global_event_item_schema = self.global_event_schema # Assume it's the object schema
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load {schema_path}. AI generation of user events might fail. Error: {e}")
            self.global_event_schema = None
            self.global_event_item_schema = None


    def _load_ramification_schema(self):
        """Loads the ramification schema needed for AI generation."""
        try:
            with open("nation_subschemas/internal_affairs_subschemas/ramification_schema.json", "r", encoding="utf-8") as f:
                full_schema = json.load(f)
                self.ramification_object_schema = {
                    k: v for k, v in full_schema.get("properties", {}).items()
                    if k in ["targetPath", "operation", "value", "description"]
                }
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load ramification_schema.json. AI generation of ramifications might fail. Error: {e}")
            self.ramification_object_schema = None

    # --- Core Engine Logic ---

    def evaluate_conditions(self):
        """
        Evaluate all world conditions and queue up new events in pending_events if triggered.
        """
        self.check_conflicts()
        self.check_economic_events()
        # ... other checks ...

    def check_conflicts(self):
        """ Check for conflict escalations. """
        conflicts_data = self.global_state.get("conflicts", {})
        activeWars = conflicts_data.get("activeWars", [])
        for war in activeWars:
             # Ensure casualties data exists and is numeric
            casualties = war.get("casualties", {})
            mil_casualties = casualties.get("military", 0)
            if not isinstance(mil_casualties, (int, float)): mil_casualties = 0

            if war.get("status") == "Ongoing" and mil_casualties > 10000:
                event_id = str(uuid.uuid4())
                participants = war.get("belligerents", {}).get("sideA", []) + war.get("belligerents", {}).get("sideB", [])
                event_data = {
                    "conflictName": war.get('conflictName', 'Unnamed Conflict'),
                    "description": f"Significant escalation in {war.get('conflictName', 'Unnamed Conflict')} due to high casualties.",
                    "belligerents": war.get("belligerents", {"sideA": [], "sideB": []}),
                    "status": "Escalated",
                    "startDate": self.time_step.strftime("%Y-%m-%d"),
                }
                global_event = {
                    "eventId": event_id, "eventType": "Conflict", "eventData": event_data,
                    "parentEventId": war.get("eventId"), "childEventIds": [], "siblingEventIds": [],
                    "participatingNations": participants,
                    "ramifications": [
                         {"ramificationType": "Military", "severity": "High", "affectedParties": participants, "description": "Conflict intensity increases.", "timeframe": "Short-Term"},
                         {"ramificationType": "Political", "severity": "Moderate", "affectedParties": participants, "description": "Increased political pressure.", "timeframe": "Medium-Term"}
                    ]
                }
                self.pending_events.append(global_event)

    def check_economic_events(self):
        """ Check for economic downturns. """
        for nation_id, nation_obj in self.global_state.get("nations", {}).items():
            nation_name = nation_obj.get("name", nation_id)
            # Safely access nested economic indicators
            economic_indicators = nation_obj.get("internalAffairs", {}).get("economicIndicators", {})
            gdp_growth = economic_indicators.get("gdpGrowthRate", 0)
            if isinstance(gdp_growth, (int, float)) and gdp_growth < -0.03: # Check if numeric and below threshold (-3%)
                event_id = str(uuid.uuid4())
                event_data = {
                    "eventName": f"Economic Downturn in {nation_name}",
                    "description": f"Severe economic contraction triggered by GDP growth falling to {gdp_growth:.2%}.",
                    "economicIndicators": {"gdpGrowthRate": gdp_growth, "unemploymentRate": "Rising"}, # Assuming unemployment rises
                    "affectedSectors": ["Multiple", "Finance", "Industry"],
                    "governmentResponse": "Pending",
                    "startDate": self.time_step.strftime("%Y-%m-%d")
                }
                global_event = {
                    "eventId": event_id, "eventType": "Economic Event", "eventData": event_data,
                    "parentEventId": None, "childEventIds": [], "siblingEventIds": [],
                    "participatingNations": [nation_id],
                    "ramifications": [
                        {"ramificationType": "Economic", "severity": "High", "affectedParties": [nation_id], "description": "Risk of recession, increased unemployment.", "timeframe": "Medium-Term"},
                        {"ramificationType": "Political", "severity": "Moderate", "affectedParties": [nation_id], "description": "Government faces pressure.", "timeframe": "Medium-Term"}
                    ]
                }
                self.pending_events.append(global_event)

    # --- Other check_... methods would go here ---

    def process_user_input(self, user_input: str):
        """ Handle user commands to modify pending events. """
        if "prevent war" in user_input.lower():
            self.pending_events = [ev for ev in self.pending_events if ev.get("eventType") != "Conflict"]

    def advance_time(self, days=30):
        """ Advance simulation time. """
        self.time_step += datetime.timedelta(days=days)
        self.global_state["current_date"] = self.time_step.strftime("%Y-%m-%d")

    def update_json_schemas(self):
        """ Add pending events to the main globalEvents list. """
        if self.pending_events:
            self.global_state["globalEvents"].extend(self.pending_events)

    def summarize_changes(self) -> str:
        """ Summarize newly added events. """
        if not self.pending_events:
            return "No new events triggered this step."
        lines = []
        for ev in self.pending_events:
             ev_data = ev.get("eventData", {})
             name = ev_data.get("eventName", ev_data.get("conflictName", ev.get("eventId")))
             date = ev_data.get("startDate", self.time_step.strftime("%Y-%m-%d"))
             lines.append(f"{date}: {name} - {ev.get('eventType', 'Unknown')}")
        return "\n".join(lines)

    def apply_ramifications(self):
        """ Generate the Impact -> Effect -> Ramification chain. """
        if not self.pending_events: return # Skip if no new events

        # Use a temporary list to avoid modifying list while iterating if needed elsewhere
        events_to_process = list(self.pending_events)

        for global_event in events_to_process:
            event_id = global_event.get("eventId", "unknown_event")
            participating_nation_ids = global_event.get("participatingNations", [])
            if not participating_nation_ids: continue

            for nation_id in participating_nation_ids:
                nation_obj = self._get_nation_data(nation_id) # Use updated getter
                if not nation_obj:
                    print(f"Warning: Could not find nation '{nation_id}' for event '{event_id}'.")
                    continue

                # --- 1. Generate NationwideImpact ---
                impact_trigger_date = self.time_step
                impact_desc = f"Nation involved in/affected by: {global_event.get('eventData',{}).get('eventName', event_id)}"
                nationwide_impact = self._create_nationwide_impact(nation_id, event_id, impact_trigger_date, impact_desc)
                # Ensure the list exists before appending
                nation_obj.setdefault("nationwideImpacts", []).append(nationwide_impact)


                # --- 2. Generate Effect(s) ---
                generated_effect_ids = []
                for ge_ram in global_event.get("ramifications", []):
                    effect = self._create_effect(nation_id, nationwide_impact["impactId"], ge_ram)
                    if effect:
                        self.global_state["effects"].append(effect)
                        generated_effect_ids.append(effect["effectId"])

                        # --- 3. Generate Ramification(s) ---
                        generated_ramification_ids = []
                        # Generate ramification using AI
                        ramification = self._create_ramification_with_ai(
                            nation_id, effect["effectId"], ge_ram
                        )
                        if ramification:
                             self.global_state["ramifications"].append(ramification)
                             generated_ramification_ids.append(ramification["ramificationId"])

                        # Update Effect with its Ramification IDs
                        effect["ramificationIds"] = generated_ramification_ids
                        # Update the effect in the central list
                        for i, e in enumerate(self.global_state["effects"]):
                             if e["effectId"] == effect["effectId"]:
                                 self.global_state["effects"][i] = effect
                                 break

                # Update NationwideImpact with its Effect IDs
                nationwide_impact["effectIds"] = generated_effect_ids
                # Update the impact in the nation's list
                impacts_list = nation_obj.get("nationwideImpacts", [])
                for i, imp in enumerate(impacts_list):
                     if imp["impactId"] == nationwide_impact["impactId"]:
                         impacts_list[i] = nationwide_impact
                         break

    # Renamed from _find_nation_by_id and potentially enhanced
    def _get_nation_data(self, identifier: str) -> dict | None:
        """
        Finds and returns the full nation data object from global_state['nations']
        using either the nation's name or its ID.

        :param identifier: The name or ID of the nation.
        :return: The nation's data dictionary, or None if not found.
        """
        nations_dict = self.global_state.get("nations", {})
        if not isinstance(nations_dict, dict):
            print("Warning: global_state['nations'] is not a dictionary. Cannot retrieve nation data.")
            return None

        # Try direct lookup by identifier (assuming it might be ID)
        if identifier in nations_dict:
            return nations_dict[identifier]

        # If not found by ID, iterate and check by name
        for nation_data in nations_dict.values():
            if isinstance(nation_data, dict) and nation_data.get("name") == identifier:
                return nation_data

        # If still not found
        print(f"Warning: Nation '{identifier}' not found by ID or name.")
        return None

    # NEW: Helper to get organization data by name
    def _get_organization_data_by_name(self, org_name: str) -> dict | None:
        """
        Finds and returns the full organization data object from global_state['organizations']
        by matching the organization's name.

        :param org_name: The name of the organization.
        :return: The organization's data dictionary, or None if not found.
        """
        orgs_list = self.global_state.get("organizations", [])
        if not isinstance(orgs_list, list):
            print("Warning: global_state['organizations'] is not a list. Cannot retrieve organization data.")
            return None

        for org_data in orgs_list:
            if isinstance(org_data, dict) and org_data.get("name") == org_name:
                return org_data

        print(f"Warning: Organization '{org_name}' not found.")
        return None


    def _create_nationwide_impact(self, nation_id: str, global_event_id: str, trigger_date: datetime.datetime, description: str) -> dict:
        """ Creates a NationwideImpact object. """
        impact_id = str(uuid.uuid4())
        return {
            "impactId": impact_id, "nationId": nation_id, "originGlobalEventId": global_event_id,
            "impactTriggerDate": trigger_date.strftime("%Y-%m-%d"), "description": description,
            "effectIds": [], "isActive": True, "estimatedEndDate": None
        }

    def _create_effect(self, nation_id: str, impact_id: str, global_ramification: dict) -> dict | None:
        """ Generates an Effect object based on a global ramification context. """
        if not global_ramification: return None
        effect_id = str(uuid.uuid4())
        effect_type_map = {
            "Political": "Political Shift", "Economic": "Economic Change", "Social": "Social Upheaval",
            "Technological": "Technological Advancement", "Military": "Military Posture Change",
            "Diplomatic": "Diplomatic Realignment", "Environmental": "Environmental Consequence",
            "Cultural": "Cultural Trend", "Humanitarian": "Resource Strain", "Legal": "Political Shift", "Other": "Other"
        }
        severity_map = {
            "Minimal": "Minimal", "Low": "Low", "Moderate": "Moderate", "High": "High",
            "Severe": "Severe", "Critical": "Critical", "Unprecedented": "Transformative"
        }
        return {
            "effectId": effect_id, "originImpactId": impact_id, "nationId": nation_id,
            "effectType": effect_type_map.get(global_ramification.get("ramificationType", "Other"), "Other"),
            "description": f"Broad effect: {global_ramification.get('description', 'General consequence')}",
            "severity": severity_map.get(global_ramification.get("severity", "Low"), "Low"),
            "startDate": self.time_step.strftime("%Y-%m-%d"), "isActive": True, "estimatedEndDate": None,
            "ramificationIds": [], "nationalMemoryImpact": "Moderately Remembered"
        }

    def _create_ramification_with_ai(self, nation_id: str, effect_id: str, global_ramification: dict) -> dict | None:
        """
        Generates a specific Ramification object using an AI model based on an Effect
        and the context from the originating global event's general ramification.
        Returns an object conforming to ramification_schema.json, or None if generation fails.
        """
        if not global_ramification or not self.ramification_object_schema:
            print("Warning: Missing global ramification context or ramification schema for AI generation.")
            return None

        # --- Prepare Context for AI ---
        nation_obj = self._get_nation_data(nation_id) # Use updated getter
        if not nation_obj:
             print(f"Warning: Cannot find nation {nation_id} to provide context for ramification generation.")
             nation_context_summary = "Nation context unavailable."
        else:
             # Create a brief summary of the nation's current state for context
             stability = nation_obj.get("internalAffairs", {}).get("stability", "N/A")
             # Safely access nested economic indicators
             economic_indicators = nation_obj.get("internalAffairs", {}).get("economicIndicators", {})
             gdp_growth = economic_indicators.get("gdpGrowthRate", "N/A")
             readiness = nation_obj.get("externalAffairs", {}).get("military", {}).get("readiness", "N/A")
             nation_context_summary = f"Current State of {nation_obj.get('name', nation_id)}: Stability={stability}, GDP Growth={gdp_growth}, Military Readiness={readiness}."

        ram_type = global_ramification.get("ramificationType", "Unknown")
        severity = global_ramification.get("severity", "Low")
        context_description = global_ramification.get('description', 'No description provided.')

        # --- Build the AI Prompt ---
        action = f"Generate the specific state change (ramification) details for nation {nation_id}."
        # Tuned prompt with more context, clearer instructions, and examples
        context = f"""
Context:
- Nation: {nation_id} ({nation_obj.get('name', 'N/A') if nation_obj else 'N/A'})
- Current Nation Summary: {nation_context_summary}
- Originating Effect Type: '{ram_type}'
- Originating Effect Severity: '{severity}'
- Originating Effect Description: '{context_description}'

Task: Determine the single most likely and specific state change ramification resulting from this effect. Provide the output as a JSON object containing: 'targetPath', 'operation', 'value', and 'description'.

Instructions:
1.  **targetPath:** Specify the exact path within the simulation's global state using dot notation. Examples: 'nations.USA.internalAffairs.stability', 'nations.USSR.externalAffairs.military.readiness', 'globalEconomy.globalInflationRate', 'nations.UK.economicIndicators.unemploymentRate'. Choose the most relevant path based on the effect type and description. Assume 'nations' is a dictionary keyed by nationId (e.g., 'nations.USA', not 'nations[0]').
2.  **operation:** Choose the most appropriate operation from the enum: ["set", "add", "subtract", "multiply", "divide"]. Use 'add'/'subtract' for numerical changes, 'set' for replacing values or setting flags. Avoid list operations ('remove_item', 'update_item') for this generation task.
3.  **value:** Determine a plausible value for the change. Consider the 'severity':
    - Minimal/Low: Small change (e.g., +/- 1-3 stability, +/- 0.001-0.005 GDP growth rate).
    - Moderate: Noticeable change (e.g., +/- 5-10 stability, +/- 0.01 GDP growth rate).
    - High/Severe: Significant change (e.g., +/- 15-25 stability, +/- 0.02-0.05 GDP growth rate).
    - Critical/Transformative: Major change (e.g., +/- 30+ stability, +/- 0.05+ GDP growth rate).
    The value type must match the target path (e.g., number for stability [0-100 scale likely], float for gdpGrowthRate [e.g., -0.02 for -2%], boolean for a flag like 'inDefault').
4.  **description:** Write a brief, specific description of this ramification (e.g., "Decrease stability by 10 points due to political unrest", "Set economic growth rate to -0.02 due to recession").

Example 1 (Political):
- Context: Nation=USA, Stability=60, Effect Type=Political, Severity=High, Description='Government faces pressure...'
- Output JSON: {{"targetPath": "nations.USA.internalAffairs.stability", "operation": "subtract", "value": 15, "description": "Decrease stability significantly due to high political pressure."}}

Example 2 (Economic):
- Context: Nation=UK, GDP Growth=0.01, Effect Type=Economic, Severity=Severe, Description='Risk of recession...'
- Output JSON: {{"targetPath": "nations.UK.economicIndicators.gdpGrowthRate", "operation": "set", "value": -0.03, "description": "Set GDP growth rate to -3% reflecting severe recession risk."}}

Example 3 (Military):
- Context: Nation=USSR, Readiness=70, Effect Type=Military, Severity=Moderate, Description='Increased border tensions...'
- Output JSON: {{"targetPath": "nations.USSR.externalAffairs.military.readiness", "operation": "add", "value": 10, "description": "Increase military readiness moderately due to border tensions."}}

Now, generate the JSON for the provided context. Output ONLY the JSON object.
        """

        # Define the target schema for the AI (just the core fields it needs to generate)
        target_ai_schema = {
            "targetPath": self.ramification_object_schema.get("targetPath", {}),
            "operation": self.ramification_object_schema.get("operation", {}),
            "value": self.ramification_object_schema.get("value", {}),
            "description": self.ramification_object_schema.get("description", {})
        }

        # Configure model specifically for this task (using pro, potentially lower temp for structure)
        # Ensure configure_genai can accept model and temp arguments
        pro_model = configure_genai(model="gemini-2.0-pro-exp-02-05", temp=0.4) # Lower temp for more deterministic output

        # --- Call AI and Process Result ---
        ai_generated_data = generate_json_object(
            model=pro_model,
            json_schema=target_ai_schema,
            action=action,
            context=context
        )

        if ai_generated_data and "targetPath" in ai_generated_data and "operation" in ai_generated_data and "value" in ai_generated_data:
            ramification_id = str(uuid.uuid4())
            # Determine execution time (e.g., immediate or delayed based on timeframe)
            # For simplicity, execute immediately in this example
            execution_time = self.time_step

            # Assemble the full ramification object
            full_ramification = {
                "ramificationId": ramification_id,
                "originEffectId": effect_id,
                "nationId": nation_id,
                "description": ai_generated_data.get("description", f"AI generated ramification for effect {effect_id}"),
                "targetPath": ai_generated_data["targetPath"],
                "operation": ai_generated_data["operation"],
                "value": ai_generated_data["value"],
                "valueIdentifier": None, # AI unlikely to determine this, handle in executor if needed
                "executionTime": execution_time.strftime("%Y-%m-%dT%H:%M:%S"), # ISO format
                "status": "pending",
                "failureReason": None
            }
            # Optional: Add validation against the full ramification schema here
            print(f"AI generated ramification: {full_ramification['description']} targeting {full_ramification['targetPath']}")
            return full_ramification
        else:
            print(f"Warning: AI failed to generate valid ramification details for effect {effect_id}. AI Output: {ai_generated_data}")
            return None

    ############################################################################
    #                        5) SIMULATION STEP                                 #
    ############################################################################

    def run_simulation_step(self, user_input="") -> str:
        """
        Perform a full simulation step:
        1. Evaluate conditions -> queue up events
        2. Process user input -> remove or alter pending events
        3. Update global state with new events
        4. Summarize newly created events
        5. (ADDED) Apply ramifications to nations or global structures
        6. Advance time
        7. Clear pending events
        8. Return summary
        """
        print(f"\n--- Running Simulation Step: {self.global_state['current_date']} ---")
        self.evaluate_conditions()

        if user_input:
            self.process_user_input(user_input)

        # Merge new events into globalEvents list
        self.update_json_schemas()

        # Summarize newly added global events
        summary = self.summarize_changes()
        print("\n--- Event Generation Summary ---")
        print(summary if summary else "No new global events generated.")


        # (NEW) Generate Impacts, Effects, and AI-driven Ramifications
        print("\n--- Generating Consequences (Impacts -> Effects -> Ramifications) ---")
        self.apply_ramifications()

        # Advance time for the next step
        self.advance_time(days=30) # Assuming fixed 30-day steps for now

        # Clear the pending events list for the next cycle
        self.pending_events.clear()

        # Return summary of events added in this step
        return summary

    # --- New Search Functionality ---
    def find_events_for_nation(self, nation_name_or_id: str) -> list:
        """
        Searches the globalEvents list for events involving a specific nation.

        :param nation_name_or_id: The name or ID of the nation to search for.
        :return: A list of global event dictionaries where the nation is listed
                 in 'participatingNations'.
        """
        matching_events = []
        all_events = self.global_state.get("globalEvents", [])
        if not isinstance(all_events, list):
            print("Warning: globalEvents is not a list. Cannot search.")
            return []

        for event in all_events:
            participants = event.get("participatingNations", [])
            if isinstance(participants, list) and nation_name_or_id in participants:
                matching_events.append(event)

        print(f"Found {len(matching_events)} events involving '{nation_name_or_id}'.")
        return matching_events

    # --- NEW: User Prompt Event Generation ---

    def _extract_entities_with_ai(self, user_prompt: str, known_nations: list, known_orgs: list) -> dict:
        """
        Uses an AI model to extract relevant entities (nations, orgs, regions, event type)
        from the user's prompt.
        """
        print("Attempting AI-driven entity extraction...")
        # Use a potentially faster/cheaper model for this classification task
        extraction_model = configure_genai(model="gemini-2.0-flash", temp=0.2)

        # Prepare known entities for the prompt
        nations_list_str = ", ".join(known_nations) if known_nations else "None provided"
        orgs_list_str = ", ".join(known_orgs) if known_orgs else "None provided"

        # Define the desired JSON output structure for the AI
        output_schema = {
            "type": "object",
            "properties": {
                "identified_nations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of nation names/IDs identified in the prompt that match the known nations list. Consider common aliases and acronyms (e.g., USA, USSR, UK, PRC, ROC)."
                },
                "identified_organizations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of organization names identified in the prompt that match the known organizations list."
                },
                "identified_regions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of geographical regions mentioned (e.g., 'Middle East', 'Europe', 'Southeast Asia')."
                },
                "suggested_event_type": {
                    "type": ["string", "null"],
                    "enum": ["Conflict", "Economic Event", "Political Event", "Scientific Discovery", "Natural Disaster", "Humanitarian Crisis", "Political Violence", "Generic Event", None],
                    "description": "The most likely event type based on the prompt, or null if unclear."
                }
            },
            "required": ["identified_nations", "identified_organizations", "identified_regions", "suggested_event_type"]
        }

        prompt = f"""
Analyze the following user prompt and extract the relevant entities based on the provided lists and general knowledge.

User Prompt: "{user_prompt}"

Known Nations: [{nations_list_str}]
Known Organizations: [{orgs_list_str}]

Task: Identify the nations, organizations, geographical regions mentioned or clearly implied in the prompt. Also, suggest the most likely event type. Match identified nations and organizations against the known lists provided. **Consider common aliases and acronyms for nations (e.g., USA for United States of America, USSR for Soviet Union, UK for United Kingdom, PRC for People's Republic of China, ROC for Republic of China).**

Output ONLY a valid JSON object strictly following this schema:
{json.dumps(output_schema, indent=2)}

Instructions:
- **Crucially:** If you identify a nation by an alias or acronym (e.g., "USA", "USSR", "PRC", "ROC", "UK"), you MUST return the corresponding canonical identifier found in the 'Known Nations' list (e.g., return "United States of America" or "USA" if that's the key in the list, not the alias used in the prompt unless the alias itself is the key). Only include nations in 'identified_nations' if they or their aliases appear in the 'Known Nations' list.
- Only include organizations in 'identified_organizations' if they appear in the 'Known Organizations' list.
- List any geographical regions mentioned under 'identified_regions'.
- Select the most appropriate 'suggested_event_type' from the enum provided in the schema, or use null if none seems correct.
- If no entities of a certain type are found, return an empty list for that key (e.g., "identified_regions": []).
- Do not include any explanations or surrounding text.
        """

        # Use generate_json_object for retries and parsing
        # Note: generate_json_object expects 'action' and 'context', we'll adapt
        action_placeholder = "Extract entities from user prompt"
        context_placeholder = f"Known Nations: {nations_list_str}\nKnown Orgs: {orgs_list_str}"

        ai_result = generate_json_object(
            model=extraction_model,
            json_schema=output_schema,
            action=action_placeholder,
            context=prompt # Pass the full prompt as context here
        )

        if ai_result and isinstance(ai_result, dict):
            # Basic validation of the result structure
            default_result = {
                "identified_nations": [], "identified_organizations": [],
                "identified_regions": [], "suggested_event_type": None
            }
            # Ensure all keys exist, defaulting to empty lists/None
            for key, default_val in default_result.items():
                ai_result.setdefault(key, default_val)
            print(f"AI Entity Extraction Result: {ai_result}")
            return ai_result
        else:
            print("Warning: AI entity extraction failed or returned invalid format. Falling back to empty entities.")
            return {
                "identified_nations": [], "identified_organizations": [],
                "identified_regions": [], "suggested_event_type": None
            }


    def _extract_entities_from_prompt(self, user_prompt: str) -> dict:
        """
        Extracts entities from the user prompt using an AI helper function.
        Maps the AI result to the format expected by _build_context_for_user_event.
        """
        # Get known entities from the current state
        # Extract both IDs and names if available, as AI might match on either
        known_nations = list(self.global_state.get("nations", {}).keys())
        known_nation_names = [n.get("name") for n in self.global_state.get("nations", {}).values() if n.get("name")]
        all_known_nation_identifiers = list(set(known_nations + known_nation_names)) # Combine IDs and names

        known_orgs = [org.get("name") for org in self.global_state.get("organizations", []) if org.get("name")]

        # Call the AI extraction helper with combined identifiers
        ai_extracted_data = self._extract_entities_with_ai(user_prompt, all_known_nation_identifiers, known_orgs)

        # Map the AI result to the desired output format, ensuring lists are returned
        # Prioritize returning the canonical ID/key used in the nations dictionary if possible
        mapped_nations = []
        for identified_nation in ai_extracted_data.get("identified_nations", []):
             nation_obj = self._get_nation_data(identified_nation) # Try finding by ID or name
             if nation_obj:
                 # Prefer ID if available, else use the name that was matched
                 nation_key = nation_obj.get("nationId") or nation_obj.get("name")
                 if nation_key and nation_key not in mapped_nations:
                      mapped_nations.append(nation_key)
             elif identified_nation not in mapped_nations: # Add the identifier if lookup failed but not already added
                  mapped_nations.append(identified_nation)


        entities = {
            "nations": mapped_nations[:2] if isinstance(mapped_nations, list) else [], # Limit primary nations
            "organizations": ai_extracted_data.get("identified_organizations", []) if isinstance(ai_extracted_data.get("identified_organizations"), list) else [],
            "regions": ai_extracted_data.get("identified_regions", []) if isinstance(ai_extracted_data.get("identified_regions"), list) else [],
            "event_type": ai_extracted_data.get("suggested_event_type") # Can be None or string
        }

        print(f"Mapped AI entities for context building: {entities}")
        return entities

    def _build_context_for_user_event(self, user_prompt: str) -> str:
        """
        Gathers and synthesizes context based on the user prompt and global state,
        following the refined plan.
        """
        print("Building context for user event...")
        context_parts = []
        current_date_str = self.global_state.get("current_date", "Unknown Date")
        context_parts.append(f"## Current Simulation Date: {current_date_str}\n")

        # --- 1. Analyze Prompt ---
        extracted_entities = self._extract_entities_from_prompt(user_prompt)
        primary_nations = extracted_entities.get("nations", []) # These are likely names or IDs
        mentioned_orgs = extracted_entities.get("organizations", [])

        # --- 2. Global Context ---
        context_parts.append("## Global Overview:")
        # Economy
        economy = self.global_state.get("globalEconomy", {})
        gdp = economy.get("globalGDP", "N/A")
        inflation = economy.get("globalInflationRate", "N/A")
        context_parts.append(f"- Economy: Global GDP {gdp}, Inflation {inflation}%.")
        # Conflicts
        active_wars = self.global_state.get("conflicts", {}).get("activeWars", [])
        if active_wars:
            context_parts.append("- Major Conflicts:")
            for war in active_wars[:3]: # Limit for brevity
                context_parts.append(f"  - {war.get('conflictName', 'Unnamed War')} ({war.get('status', 'Unknown')})")
        # Strategic Interests (Improved filtering attempt)
        interests = self.global_state.get("strategicInterests", [])
        relevant_interests = []
        # Basic filtering: check if primary nations are involved as controlling/rival entities
        for theatre in interests: # Assuming interests is the list of theatres
             for interest in theatre.get("strategicInterests", []):
                 controlling = interest.get("controllingEntities", [])
                 rivals = interest.get("rivalClaims", [])
                 involved_entities = set(controlling + rivals)
                 if any(nation in involved_entities for nation in primary_nations):
                     relevant_interests.append(f"  - {interest.get('interestName', 'Unnamed')} ({interest.get('region', 'Unknown')}) - Importance: {interest.get('importanceLevel', 'N/A')}")
                     if len(relevant_interests) >= 3: break # Limit for brevity
             if len(relevant_interests) >= 3: break
        if relevant_interests:
             context_parts.append("- Relevant Strategic Interests:")
             context_parts.extend(relevant_interests)

        # Recent Events (Last 3 involving primary nations) - Use _find_nation_by_id logic if needed
        recent_events_str = []
        count = 0
        for event in reversed(self.global_state.get("globalEvents", [])):
            if count >= 3: break
            participants = event.get("participatingNations", [])
            if any(nation in participants for nation in primary_nations):
                 event_name = event.get("eventData", {}).get("standardizedEventName", event.get("eventId"))
                 recent_events_str.append(f"  - {event_name}")
                 count += 1
        if recent_events_str:
             context_parts.append("- Recent Relevant Events:")
             context_parts.extend(recent_events_str)
        context_parts.append("\n")


        # --- 3. Primary Nation Context ---
        context_parts.append("## Primary Nation Status:")
        current_year = current_date_str.split('-')[0] if current_date_str != "Unknown Date" else "UnknownYear"
        for nation_identifier in primary_nations: # Could be name or ID
            nation_obj = self._get_nation_data(nation_identifier) # Use helper to find object
            if nation_obj:
                nation_name = nation_obj.get("name", nation_identifier) # Prefer name if available
                nation_id = nation_obj.get("nationId", nation_identifier) # Prefer ID if available
                context_parts.append(f"### {nation_name} ({nation_id}):")
                # Add full nation object as JSON string
                try:
                    nation_json_str = json.dumps(nation_obj, indent=2)
                    context_parts.append(f"- Full Data:\n```json\n{nation_json_str}\n```")
                except TypeError:
                    context_parts.append("- Full Data: (Error serializing nation object)")

                # Diplomatic Stance (towards other primary nation if applicable)
                other_primary_id = next((n_id for n_id in primary_nations if n_id != nation_identifier), None)
                if other_primary_id:
                    # Find sentiment using nation IDs/names
                    # Add type check for 's'
                    sentiment = next((s for s in self.global_state.get("globalSentiment", [])
                                      if isinstance(s, dict) and \
                                         ((s.get("nationA") == nation_identifier and s.get("nationB") == other_primary_id) or \
                                          (s.get("nationA") == other_primary_id and s.get("nationB") == nation_identifier))), None)
                    if sentiment:
                        context_parts.append(f"- Relations with {other_primary_id}: {sentiment.get('diplomaticRelations', 'N/A')}")

                # Key Figures (Simplified: first leader found matching nation name)
                char = next((c for c in self.global_state.get("notableCharacters", [])
                             if isinstance(c, dict) and c.get("nationality") == nation_name and ("Leader" in c.get("role", "") or "Head of State" in c.get("role", ""))), None)
                if char:
                    context_parts.append(f"- Key Figure: {char.get('fullName', 'Unknown')} ({char.get('role', 'Unknown')})")

            else:
                context_parts.append(f"### {nation_identifier}: Data not found.")
        context_parts.append("\n")


        # --- 4. Organization & Stakeholder Context ---
        context_parts.append("## Organizational Context:")
        relevant_orgs = []
        # Add explicitly mentioned orgs
        relevant_orgs.extend(mentioned_orgs)
        # TODO: Add logic to find relevant orgs based on nations/region if not explicitly mentioned

        stakeholder_nations = set()
        if relevant_orgs: # Only proceed if orgs were mentioned or identified
            context_parts.append("- Relevant Organizations:")
            for org_name in relevant_orgs:
                org_data = self._get_organization_data_by_name(org_name) # Use helper
                if org_data:
                    context_parts.append(f"  - {org_name}: Objective - {org_data.get('primaryObjectives', ['N/A'])[0]}, Influence - {org_data.get('influenceScore', 'N/A')}")
                    # Identify key members (excluding primary nations already covered)
                    members = [m for m in org_data.get("memberStates", []) if m not in primary_nations]
                    stakeholder_nations.update(members[:3]) # Limit stakeholders for brevity
                else:
                    context_parts.append(f"  - {org_name}: Data not found.")

        if stakeholder_nations:
            context_parts.append("- Key Stakeholder Nation Stances (towards primary nations):")
            for stakeholder in stakeholder_nations:
                stances = []
                for primary_id in primary_nations:
                    # Find sentiment using stakeholder name and primary nation ID/name
                    # Add type check for 's'
                    sentiment = next((s for s in self.global_state.get("globalSentiment", [])
                                      if isinstance(s, dict) and \
                                         ((s.get("nationA") == stakeholder and s.get("nationB") == primary_id) or \
                                          (s.get("nationA") == primary_id and s.get("nationB") == stakeholder))), None)
                    if sentiment:
                        stances.append(f"{primary_id}: {sentiment.get('diplomaticRelations', 'N/A')}")
                if stances:
                    context_parts.append(f"  - {stakeholder}: ({'; '.join(stances)})")
        context_parts.append("\n")


        # --- 5. Synthesize ---
        final_context = "\n".join(context_parts)
        # --- DEBUG PRINT ---
        print("\n" + "="*20 + " CONTEXT FOR EVENT GENERATION " + "="*20)
        print(final_context)
        print("="*60 + "\n")
        # --- END DEBUG PRINT ---
        return final_context


    def generate_event_from_prompt(self, user_prompt: str):
        """
        Generates a single global event based on a user prompt and derived context,
        then adds it to the pending_events list.
        """
        print(f"\n--- Generating Event from User Prompt: '{user_prompt}' ---")
        if not self.global_event_item_schema:
            print("Error: Global event item schema not loaded. Cannot generate event.")
            return

        # 1. Build Context
        context = self._build_context_for_user_event(user_prompt)

        # 2. Prepare for AI Call
        # Use a specific model/temp if desired for this task
        event_gen_model = configure_genai(model="gemini-2.0-flash", temp=0.7) # Example config

        # Adapt the prompt generation - using a simpler action description
        action = f"Generate a single global event based on the user request: '{user_prompt}' considering the provided context."

        # 3. Call AI to Generate Event Object
        # Using generate_json_object from this file
        generated_event_obj = generate_json_object(
            model=event_gen_model,
            json_schema=self.global_event_item_schema, # Use the item schema
            action=action, # Pass the refined action
            context=context # Pass the synthesized context
        )

        # 4. Validate and Add to Pending
        if generated_event_obj and isinstance(generated_event_obj, dict):
            # Basic validation (add more checks as needed)
            if "eventId" in generated_event_obj and "eventType" in generated_event_obj:
                print(f"Successfully generated event: {generated_event_obj.get('eventId')}")
                # Ensure essential fields like participatingNations are present if needed by schema
                generated_event_obj.setdefault("participatingNations", [])
                generated_event_obj.setdefault("ramifications", [])
                # Add to pending events
                self.pending_events.append(generated_event_obj)
            else:
                print("Error: Generated event object is missing required fields (eventId, eventType).")
        else:
            print("Error: Failed to generate a valid event object from the AI.")

    # --- End NEW ---


###############################################################################
#                         EXAMPLE USAGE & MAIN                                #
###############################################################################

if __name__ == "__main__":
    """
    Example usage demonstrating initializing from a directory and generating
    an event from a user prompt.
    """
    # --- Configuration ---
    # Specify the simulation directory containing global_state.json
    # Make sure this directory and file exist from a previous initialization run.
    simulation_directory = "simulation_data/generated_timeline_1975" # Example year

    # Example user prompt for event generation
    user_event_prompt = "Generate a political event where the USA and USSR sign a new arms control treaty."

    # --- Execution ---
    try:
        # 1. Initialize EventEngine from the specified directory
        print(f"--- Initializing Event Engine from: {simulation_directory} ---")
        engine = EventEngine.from_directory(simulation_directory)
        print(f"Engine initialized. Current simulation date: {engine.global_state.get('current_date')}")

        # 2. Generate an event based on the user prompt
        # This will build context and call the AI
        engine.generate_event_from_prompt(user_event_prompt)

        # 3. Check pending events (the newly generated one should be here)
        print("\n--- Pending Events After User Prompt Generation ---")
        if engine.pending_events:
            print(json.dumps(engine.pending_events, indent=2))
        else:
            print("No events were added to pending_events (generation might have failed).")

        # 4. Optionally, run a simulation step to process the pending event
        # print("\n--- Running a Simulation Step to Process Pending Event ---")
        # step_summary = engine.run_simulation_step()
        # print("\n--- Simulation Step Summary ---")
        # print(step_summary)

        # 5. Optionally, save the updated state (if a step was run)
        # updated_state_path = os.path.join(simulation_directory, "global_state_after_user_event.json")
        # with open(updated_state_path, "w", encoding="utf-8") as f:
        #     json.dump(engine.global_state, f, indent=2)
        # print(f"\nSaved potentially updated state to {updated_state_path}")

    except FileNotFoundError as e:
        print(f"\nError: Could not find simulation data directory or global_state.json.")
        print(f"Please ensure '{simulation_directory}' exists and contains 'global_state.json'.")
        print(f"Details: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred during the example run:")
        print(f"{type(e).__name__}: {e}")
