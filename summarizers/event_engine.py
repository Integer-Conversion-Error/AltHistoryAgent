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
import json
import datetime
import uuid
import time
import google.generativeai as genai

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


def configure_genai():
    """
    Configure the generative AI model with the loaded API key and recommended generation settings.
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
    Build a structured AI prompt for generating a JSON object given a particular schema.

    :param json_schema: A dictionary defining the JSON schema to follow.
    :param action: Brief text explaining the event creation or escalation.
    :param context: Additional context describing the scenario.
    :return: A string prompt that instructs the AI to output valid JSON only.
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
    Calls the generative AI to produce a JSON object conforming to the provided schema.

    :param model: The generative AI model (gemini-2.0-flash-exp).
    :param json_schema: The JSON schema dict to enforce.
    :param action: The event creation or escalation context.
    :param context: Additional scenario context for the AI.
    :return: Parsed Python dict if successful, else None.
    """
    prompt = generate_object_prompt(json_schema, action, context)
    response = model.generate_content(prompt)

    try:
        # The AI might add extra text, we attempt a naive extraction.
        # If the entire text is wrapped with potential lines, you may need more robust extraction logic.
        text = response.text.strip()

        # Some of your code tries to do text[7:-3]. Adjust if the AI response doesn't have bracketed lines
        # For now, we do a direct attempt:
        generated_json = json.loads(text)
        return generated_json
    except json.JSONDecodeError:
        print("Error: AI did not return valid JSON.\nAI Output:\n", response.text)
        return None


###############################################################################
#                       2) CONDITION ENGINE & AI MERGE                        #
###############################################################################

class EventEngine:
    """
    The EventEngine checks the global_state for conditions that trigger new events.
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
        self.global_state = global_state
        self.pending_events = []  # List[dict], new events to insert in the update phase
        self.time_step = datetime.datetime.strptime(global_state["current_date"], "%Y-%m-%d")  # Current sim time

        # Configure the generative AI model for possible event creation.
        self.model = configure_genai()

    def evaluate_conditions(self):
        """
        Evaluate all world conditions and queue up new events in pending_events if triggered.
        """
        self.check_conflicts()
        self.check_economic_events()
        self.check_generic_events()
        self.check_humanitarian_crises()
        self.check_natural_disasters()
        self.check_political_events()
        self.check_political_violence()
        self.check_scientific_discoveries()
        # If you have other condition checks, add them here:
        # e.g. check_social_unrest(), check_diplomatic_crises(), etc.

    # --------------------------------------------------------------------------
    # Condition checks: Each searches global_state for triggers.
    # If triggered, we either directly create an event or use the AI to fill details.
    # The event is appended to self.pending_events. Then at update_json_schemas,
    # we integrate them with the relevant sub-schema.
    # --------------------------------------------------------------------------

    def check_conflicts(self):
        """
        Check if an active conflict (e.g., war) has escalated to certain thresholds
        or if new conflicts arise.
        """
        conflicts_data = self.global_state.get("conflicts", {})
        activeWars = conflicts_data.get("activeWars", [])

        for war in activeWars:
            # Example: escalate if casualties are huge or if it's multi-year with no resolution
            if war["status"] == "Ongoing" and war["casualties"]["military"] > 10000:
                # Potential AI approach to elaborate an escalation
                action = "Escalate conflict due to high military casualties"
                context = (
                    f"The war named {war['conflictName']} now exceeds 10k military casualties. "
                    f"Status is {war['status']}, started on {war['startDate']}."
                )
                # Possibly generate an event referencing conflicts_schema or generic event
                # For demonstration, we show a simple manual event:
                event_obj = {
                    "eventId": str(uuid.uuid4()),
                    "name": f"Escalation in {war['conflictName']}",
                    "date": self.time_step.strftime("%Y-%m-%d"),
                    "type": "Conflict",
                    "location": {"country": war["belligerents"]["sideA"][0]},
                    "causes": ["Excessive casualties", "Unresolved hostilities"],
                    "impact": [
                        {
                            "category": "Military",
                            "details": {
                                "description": "Conflict worsens significantly.",
                                "affectedEntities": war["belligerents"]["sideA"] + war["belligerents"]["sideB"]
                            }
                        }
                    ],
                    "longTermEffects": ["Potential for regional destabilization", "Increased global scrutiny"]
                }
                self.pending_events.append(event_obj)

    def check_economic_events(self):
        """
        Example check: If a nation's GDP growth is below a threshold, spawn a crisis event.
        """
        for nation in self.global_state.get("nations", []):
            gdp_growth = nation.get("economicIndicators", {}).get("gdpGrowthRate", 0)
            if gdp_growth < -3.0:
                # Attempt an AI-based event creation referencing economic_events_schema
                try:
                    with open("global_subschemas/event_subschemas/economic_events_schema.json", "r", encoding="utf-8") as file:
                        econ_schema = json.load(file)
                except (FileNotFoundError, json.JSONDecodeError):
                    print("Warning: Could not load economic_events_schema.json. Using fallback event creation.")
                    econ_schema = None

                if econ_schema:
                    action = "Create an economic downturn event"
                    context = (
                        f"{nation['name']} experiences severe negative GDP growth of {gdp_growth}%. "
                        f"This triggers a possible economic crisis with rising unemployment."
                    )
                    new_event = generate_json_object(self.model, econ_schema, action, context)
                    if new_event:
                        # Adjust fields to match your structure
                        new_event["eventId"] = str(uuid.uuid4())
                        new_event.setdefault("name", f"Economic Crisis in {nation['name']}")
                        new_event["date"] = self.time_step.strftime("%Y-%m-%d")
                        self.pending_events.append(new_event)

    def check_generic_events(self):
        """
        If you track user-specified or system-logged globalEvents with conditions,
        you might replicate or mutate them here.
        """
        # Example: We look for an old event with a date older than 2 years
        # that might cause a follow-up event.aaaa
        pass

    def check_humanitarian_crises(self):
        """
        If there's a big refugee count or large scale famine in 'humanitarianCrises',
        we can spawn new events or escalate them.
        """
        for crisis in self.global_state.get("humanitarianCrises", []):
            if crisis["severityLevel"] in ["International", "Global"] and crisis["refugeeCount"] > 100000:
                # Possibly create or escalate a new crisis event
                pass

    def check_natural_disasters(self):
        """
        If a natural disaster is extremely large magnitude, we might spawn a new event or update existing ones.
        """
        for disaster in self.global_state.get("naturalDisasters", []):
            if disaster["magnitude"] > 7.5:
                # e.g., escalation or new data
                pass

    def check_political_events(self):
        """
        Evaluate 'politicalEvents' to see if a revolution or major election triggers a new scenario.
        """
        for pol_event in self.global_state.get("politicalEvents", []):
            if pol_event["type"] == "Revolution" and "Ongoing" not in pol_event.get("longTermEffects", []):
                # possibly spawn follow-up events
                pass

    def check_political_violence(self):
        """
        If there's an assassination or terror attack with high fatalities, might cause a new event.
        """
        for violence in self.global_state.get("politicalViolence", []):
            if violence["casualties"]["fatalities"] > 50:
                # spawn a crisis or major condemnation event
                pass

    def check_scientific_discoveries(self):
        """
        If there's a 'Revolutionary' impact discovery, spawn a big event that changes the game.
        """
        for discovery in self.global_state.get("scientificDiscoveries", []):
            if discovery["impactLevel"] == "Revolutionary":
                # Possibly spawn a 'Global Science Breakthrough' event
                pass

    ############################################################################
    #                        3) USER INPUT & TIME ADVANCE                      #
    ############################################################################

    def process_user_input(self, user_input: str):
        """
        Allows the user to override or remove certain new events, e.g., 'prevent war'.
        In a real system, you'd parse user commands more robustly.

        :param user_input: The text command from the user.
        """
        if "prevent war" in user_input.lower():
            self.pending_events = [ev for ev in self.pending_events if ev.get("type", "").lower() != "conflict"]
        # Additional commands can remove or alter other types of events.

    def advance_time(self, days=30):
        """
        Moves simulation time forward by a specified number of days
        and updates the global state's current_date accordingly.

        :param days: How many days to move forward.
        """
        self.time_step += datetime.timedelta(days=days)
        self.global_state["current_date"] = self.time_step.strftime("%Y-%m-%d")

    ############################################################################
    #                        4) UPDATE JSON SCHEMAS                             #
    ############################################################################

    def update_json_schemas(self):
        """
        After we've queued up new events in pending_events, integrate them
        into the relevant sub-schemas (e.g. conflicts, politicalEvents).
        """
        for ev in self.pending_events:
            ev_type = ev.get("type", "").lower()

            # For each recognized type, place event in the correct sub-schema.
            # Adjust logic as needed for your codebase.
            if ev_type in ["conflict", "war"]:
                self._merge_conflict_event(ev)

            elif ev_type in ["market crash", "recession", "financial boom", "economic event"]:
                self._merge_economic_event(ev)

            elif ev_type == "humanitarian crisis":
                self._merge_humanitarian_event(ev)

            elif ev_type == "natural disaster":
                self._merge_natural_disaster(ev)

            elif ev_type == "political event":
                self.global_state["politicalEvents"].append(ev)

            elif ev_type in ["political violence", "assassination", "terrorist attack"]:
                self.global_state["politicalViolence"].append(ev)

            elif ev_type == "scientific discovery":
                self.global_state["scientificDiscoveries"].append(ev)

            else:
                # Fallback: treat as generic event
                self.global_state["globalEvents"].append(ev)

    def _merge_conflict_event(self, ev: dict):
        """
        Helper function to handle new conflict events, merging them into the 'conflicts' structure.
        """
        # Insert into 'activeWars' or 'borderSkirmishes' or 'proxyWars' based on internal logic
        war = {
            "conflictName": ev.get("name", "Unnamed Conflict"),
            "startDate": ev["date"],
            "status": "Ongoing",
            "belligerents": {
                "sideA": ["Undefined"],
                "sideB": ["Undefined"]
            },
            "casualties": {"military": 0, "civilian": 0},
            "territorialChanges": []
        }
        self.global_state["conflicts"]["activeWars"].append(war)

    def _merge_economic_event(self, ev: dict):
        """
        Helper function to handle economic events, storing them in globalEconomy or a separate structure.
        """
        self.global_state["globalEconomy"].append(ev)

    def _merge_humanitarian_event(self, ev: dict):
        """
        For a new humanitarian crisis event, add it to the 'humanitarianCrises' array.
        """
        crisis = {
            "crisisId": ev["eventId"],
            "crisisName": ev.get("name", "Humanitarian Crisis"),
            "startDate": ev["date"],
            "affectedRegions": [ev.get("location", {}).get("country", "Unknown")],
            "severityLevel": "International",
            "cause": "unknown",
            "casualties": {"deaths": 0, "injuries": 0},
            "refugeeCount": 0,
            "longTermEffects": ev.get("longTermEffects", [])
        }
        self.global_state["humanitarianCrises"].append(crisis)

    def _merge_natural_disaster(self, ev: dict):
        """
        For a new natural disaster event, store in 'naturalDisasters'.
        """
        disaster = {
            "disasterType": ev.get("name", "Unnamed Disaster"),
            "location": ev.get("location", {}).get("country", "Unknown"),
            "date": ev["date"],
            "magnitude": 0.0,
            "casualties": 0,
            "economicDamage": "$0 billion",
            "affectedPopulation": 0,
            "disasterResponse": {
                "evacuations": 0,
                "aidProvided": "$0 million",
                "internationalAssistance": False
            },
            "environmentalImpact": {
                "co2Released": 0,
                "habitatDestruction": "Minor",
                "waterContamination": False
            }
        }
        self.global_state["naturalDisasters"].append(disaster)

    def summarize_changes(self) -> str:
        """
        Build a short textual summary of the newly triggered events.
        :return: A multi-line string with date, name, and type for each new event.
        """
        if not self.pending_events:
            return "No new events triggered this step."
        lines = []
        for ev in self.pending_events:
            lines.append(f"{ev['date']}: {ev.get('name', 'Unnamed')} - {ev.get('type', 'Unknown')}")
        return "\n".join(lines)
    
    
    
    def apply_ramifications(self):
        """
        After new events have been merged into the global state, 
        apply any ramifications to the nations or global context.

        For example, if an event has a 'ramifications' array or if your code
        stores ramifications in eventData. Then we can place them into 
        'nation_effects' or directly modify each nation's stats.
        """
        # Example approach: loop over newly added events in globalEvents (or other sub-schemas)
        # and check if they contain a 'ramifications' key.
        # Then, for each ramification, apply to the relevant nation or data structure.
        new_global_events = self._get_newly_merged_events("globalEvents")
        
        for ev in new_global_events:
            # If the event includes a 'ramifications' field:
            ramifications = ev.get("ramifications", [])
            if not ramifications:
                continue
            
            # For each ramification, determine which nation or sector is affected
            for ram in ramifications:
                # Example structure: 
                # {
                #   "ramificationType": "Economic",
                #   "severity": "Moderate",
                #   "affectedParties": ["Germany"],
                #   "description": "...",
                #   "timeframe": "Short-Term"
                # }
                affected_nations = ram.get("affectedParties", [])
                for nation_name in affected_nations:
                    # Optionally store in a new 'nation_effects' array or 
                    # directly update the nation's data in self.global_state.
                    self._record_nation_effect(nation_name, ev, ram)

    def _record_nation_effect(self, nation_name: str, event_obj: dict, ram: dict):
        """
        Internal method to record or apply a single ramification
        for a specific nation (like storing in a 'nation_effects' or altering 
        the nation's data).
        """
        # Find the nation in self.global_state["nations"]
        for nation in self.global_state.get("nations", []):
            if nation.get("name", "").lower() == nation_name.lower():
                # Example: We might store a new 'effects' array
                if "effects" not in nation:
                    nation["effects"] = []
                
                # Append a simplified record
                effect_record = {
                    "originEventId": event_obj["eventId"],
                    "ramificationType": ram.get("ramificationType", "Other"),
                    "severity": ram.get("severity", "Low"),
                    "description": ram.get("description", ""),
                    "timeframe": ram.get("timeframe", "Short-Term"),
                    "isActive": True,
                    "startDate": self.time_step.strftime("%Y-%m-%d")
                }
                # Possibly store more details from the event or ramification.
                nation["effects"].append(effect_record)
                # break if only one match is desired
                break


    def _get_newly_merged_events(self, key_name: str) -> list:
        """
        Helper method: after 'update_json_schemas', if we want to track or apply
        further logic to newly inserted events, we can look them up here.

        This approach might require you to store old length references before 
        insertion, or you can keep track in pending_events. For demonstration:
        we cross-reference pending_events that ended up in the globalState sub-schema.
        """
        results = []
        new_ev_ids = {ev["eventId"] for ev in self.pending_events}
        
        for ev in self.global_state.get(key_name, []):
            if ev.get("eventId") in new_ev_ids:
                results.append(ev)
        return results

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
        self.evaluate_conditions()

        if user_input:
            self.process_user_input(user_input)

        # Merge new events into sub-schemas
        self.update_json_schemas()

        # Summarize
        summary = self.summarize_changes()

        # (NEW) After merging events, apply ramifications if any
        self.apply_ramifications()

        # Advance time
        self.advance_time(days=30)

        # Clear the pending events so next step is clean
        self.pending_events.clear()

        return summary


###############################################################################
#                         EXAMPLE USAGE & MAIN                                #
###############################################################################

if __name__ == "__main__":
    """
    If you run event_engine.py directly, here's a minimal usage example.
    A real scenario might load global_state from file or share it with time_engine.py.
    """

    # Example skeleton global_state
    global_state = {
        "current_date": "1975-01-01",
        "nations": [
            {
                "name": "Example Nation",
                "military_tensions": 85,
                "economicIndicators": {"gdpGrowthRate": -4.0},
                "domesticStability": 50
            }
        ],
        "conflicts": {
            "activeWars": [
                {
                    "conflictName": "Eastern Border Conflict",
                    "startDate": "1974-06-10",
                    "endDate": None,
                    "status": "Ongoing",
                    "belligerents": {
                        "sideA": ["Example Nation"],
                        "sideB": ["Another Nation"]
                    },
                    "casualties": {"military": 12000, "civilian": 500},
                    "territorialChanges": []
                }
            ],
            "borderSkirmishes": [],
            "internalUnrest": [],
            "proxyWars": []
        },
        "globalEconomy": [],
        "globalEvents": [],
        "humanitarianCrises": [],
        "naturalDisasters": [],
        "politicalEvents": [],
        "politicalViolence": [],
        "scientificDiscoveries": []
    }

    # Instantiate the engine and run a step:
    engine = EventEngine(global_state)

    # Single simulation step with user input "prevent war"
    summary_output = engine.run_simulation_step(user_input="prevent war")
    print("=== Simulation Step Summary ===")
    print(summary_output)

    # The updated global_state now includes new events
    print("\n=== Updated Global State ===")
    print(json.dumps(global_state, indent=2))
