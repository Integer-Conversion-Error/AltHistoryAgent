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
    prompt = generate_object_prompt(json_schema, action, context)
    response = model.generate_content(prompt)

    # Attempt to parse JSON from the AI's response
    try:
        # The AI might return extra text. Here we assume the response is bracketed
        # or at least contains JSON data. We'll do a naive parse attempt:
        text = response.text
        text = text[7:-3]
        # You may need a more robust approach for extracting JSON from the response.
        
        # Attempt a direct json.loads on the entire text:
        generated_json = json.loads(text)
        return generated_json
    except json.JSONDecodeError:
        print("Error: AI did not return valid JSON.\nAI Output:\n", response.text)
        return None


###############################################################################
#                       2) CONDITION ENGINE & AI MERGE                        #
###############################################################################

class EventEngine:
    def __init__(self, global_state):
        """
        Initialize the condition engine with the current global state.
        """
        self.global_state = global_state
        self.pending_events = []  # List of events that will be triggered
        self.time_step = datetime.datetime.strptime(global_state["current_date"], "%Y-%m-%d")  # Track simulation time

        # Configure the generative AI model
        self.model = configure_genai()

    def evaluate_conditions(self):
        """
        Evaluate all world conditions and determine which events should be triggered.
        """
        self.check_conflicts()
        self.check_economic_events()
        self.check_generic_events()
        self.check_humanitarian_crises()
        self.check_natural_disasters()
        self.check_political_events()
        self.check_political_violence()
        self.check_scientific_discoveries()

    ############################################################################
    # Each 'check_' function looks for conditions in the global_state that
    # warrant generating a new event object. If triggered, we either build it
    # manually or call the generative AI to fill in details.
    ############################################################################

    def check_conflicts(self):
        """
        Check if a war, border skirmish, or proxy war should escalate.
        """
        conflicts_data = self.global_state["conflicts"]  # Must match the "conflicts_schema.json"
        # Example condition: any active war with > 10k military casualties triggers a new event.
        for war in conflicts_data["activeWars"]:
            if war["status"] == "Ongoing" and war["casualties"]["military"] > 10000:
                # Potential to ask AI to elaborate on an escalation.
                # We have conflicts_schema. If we want a new conflict object, we do:
                # AI approach: generate a new "activeWars" item
                action = "Create an escalation of this conflict"
                context = f"The war named {war['conflictName']} has reached high casualties. Military casualties exceed 10k."
                # We'll pass the conflicts schema if we want a new conflict entry:
                # But let's assume we want a 'generic_global_event' for the escalation
                # to store in 'globalEvents'.
                
                # This is optional. For demonstration, we'll do a direct event creation:
                event_obj = {
                    "eventId": str(uuid.uuid4()),
                    "name": f"Escalation in {war['conflictName']}",
                    "date": self.time_step.strftime("%Y-%m-%d"),
                    "type": "Conflict",
                    "location": {"country": war["belligerents"]["sideA"][0]},
                    "causes": ["Heavy casualties"],
                    "impact": [
                        {
                            "category": "Military",
                            "details": {
                                "description": "Conflict worsens",
                                "affectedEntities": war["belligerents"]["sideA"] + war["belligerents"]["sideB"]
                            }
                        }
                    ],
                    "longTermEffects": ["Potential regional destabilization"]
                }
                self.pending_events.append(event_obj)

    def check_economic_events(self):
        """
        Detect financial crashes, booms, or recessions.
        """
        for nation in self.global_state["nations"]:
            if nation["economicIndicators"]["gdpGrowthRate"] < -3.0:
                # We'll attempt an AI approach for generating an 'economic event' object
                with open("global_subschemas/event_subschemas/economic_events_schema.json", "r") as file:
                    economic_schema = json.load(file)

                action = "Create a new economic crisis event"
                context = (
                    f"Nations' GDP growth is {nation['economicIndicators']['gdpGrowthRate']}%. "
                    f"Severe downturn in {nation['name']}."
                )
                new_event = generate_json_object(self.model, economic_schema, action, context)
                if new_event:
                    # Adjust or finalize certain fields if needed
                    new_event["eventId"] = str(uuid.uuid4())
                    new_event["name"] = new_event.get("name", f"Economic Crisis in {nation['name']}")
                    new_event["date"] = self.time_step.strftime("%Y-%m-%d")
                    self.pending_events.append(new_event)

    def check_generic_events(self):
        """
        Check for any user-specified or system-tracked generic events.
        """
        for event in self.global_state["globalEvents"]:
            # If there's some condition or time check, we might replicate or modify them
            pass

    def check_humanitarian_crises(self):
        """
        Detect major crises from the 'humanitarianCrises' array.
        """
        for crisis in self.global_state["humanitarianCrises"]:
            if crisis["severityLevel"] in ["International", "Global"] and crisis["refugeeCount"] > 100000:
                # Possibly create or escalate a new crisis event
                pass  # Implementation example or AI approach is similar

    def check_natural_disasters(self):
        """
        Check for large-scale disasters from 'naturalDisasters'.
        """
        for disaster in self.global_state["naturalDisasters"]:
            if disaster["magnitude"] > 7.5:
                # Possibly create an event or update
                pass

    def check_political_events(self):
        """
        Evaluate 'politicalEvents' for something that might trigger new events.
        """
        for ev in self.global_state["politicalEvents"]:
            if ev["type"] in ["Revolution", "Coup d'État"] and "Ongoing" not in ev.get("longTermEffects", []):
                pass

    def check_political_violence(self):
        """
        Evaluate 'politicalViolence' for high-fatality attacks.
        """
        for violence in self.global_state["politicalViolence"]:
            if violence["casualties"]["fatalities"] > 50:
                pass

    def check_scientific_discoveries(self):
        """
        Identify major 'Revolutionary' breakthroughs and produce events or changes.
        """
        for discovery in self.global_state["scientificDiscoveries"]:
            if discovery["impactLevel"] == "Revolutionary":
                pass  # Possibly spawn new events

    ############################################################################
    #                        3) USER INPUT & TIME ADVANCE                      #
    ############################################################################

    def process_user_input(self, user_input):
        """
        Integrate user modifications into the simulation.
        """
        # If user wants to prevent war:
        if "prevent war" in user_input.lower():
            self.pending_events = [ev for ev in self.pending_events if ev.get("type") != "Conflict"]

    def advance_time(self, days=30):
        """
        Move the simulation forward in time.
        """
        self.time_step += datetime.timedelta(days=days)
        self.global_state["current_date"] = self.time_step.strftime("%Y-%m-%d")

    ############################################################################
    #                        4) UPDATE JSON SCHEMAS                             #
    ############################################################################

    def update_json_schemas(self):
        """
        Apply triggered events to the relevant JSON schemas.
        """
        for ev in self.pending_events:
            ev_type = ev.get("type", "")
            # Conflict -> conflicts_schema
            if ev_type.lower() in ["conflict", "war"]:
                # Insert it into 'activeWars' or 'proxyWars' based on some logic
                self.global_state["conflicts"]["activeWars"].append({
                    "conflictName": ev["name"],
                    "startDate": ev["date"],
                    "status": "Ongoing",
                    "belligerents": {
                        "sideA": ["Undefined"],
                        "sideB": ["Undefined"]
                    },
                    "casualties": {"military": 0, "civilian": 0},
                    "territorialChanges": []
                })
            
            elif ev_type.lower() in ["market crash", "recession", "financial boom"]:
                # Insert into global economy
                self.global_state["globalEconomy"].append(ev)
            
            elif ev_type.lower() == "humanitarian crisis":
                self.global_state["humanitarianCrises"].append({
                    "crisisId": ev["eventId"],
                    "crisisName": ev["name"],
                    "startDate": ev["date"],
                    "affectedRegions": [ev.get("location", {}).get("country", "Unknown")],
                    "severityLevel": "International",
                    "cause": "unknown",
                    "casualties": {"deaths": 0, "injuries": 0},
                    "refugeeCount": 0,
                    "longTermEffects": ev.get("longTermEffects", [])
                })
            
            elif ev_type.lower() == "natural disaster":
                self.global_state["naturalDisasters"].append({
                    "disasterType": ev["name"],
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
                })
            
            elif ev_type.lower() == "political event":
                self.global_state["politicalEvents"].append(ev)
            
            elif ev_type.lower() == "political violence":
                self.global_state["politicalViolence"].append(ev)
            
            elif ev_type.lower() == "scientific discovery":
                # Insert into 'scientificDiscoveries'
                self.global_state["scientificDiscoveries"].append(ev)
            
            else:
                # Fallback: treat as generic event
                self.global_state["globalEvents"].append(ev)

    def summarize_changes(self):
        """
        Generate a high-level summary of the new events.
        """
        if not self.pending_events:
            return "No new events triggered this step."
        lines = []
        for ev in self.pending_events:
            lines.append(f"{ev['date']}: {ev['name']} - {ev.get('type', 'Unknown')}")
        return "\n".join(lines)

    ############################################################################
    #                        5) SIMULATION STEP                                 #
    ############################################################################

    def run_simulation_step(self, user_input=""):
        """
        Perform a full simulation step:
        - Evaluate conditions
        - Process user input
        - Update global state
        - Advance time
        - Return summary of what happened
        """
        self.evaluate_conditions()
        if user_input:
            self.process_user_input(user_input)
        self.update_json_schemas()
        summary = self.summarize_changes()
        self.advance_time()
        self.pending_events.clear()
        return summary

###############################################################################
#                         EXAMPLE USAGE & MAIN                                #
###############################################################################

if __name__ == "__main__":
    # Example global state (minimal)
    global_state = {
        "current_date": "1975-01-01",
        "nations": [
            {
                "name": "Germany",
                "military_tensions": 85,
                "economicIndicators": {
                    "gdpGrowthRate": -4.0,
                    "unemploymentRate": 8.5,
                    "inflationRate": 7.2
                },
                "domesticStability": 50,
                "politicalSystem": "Federal Republic",
                "resources": {
                    "foodSupply": 85,
                    "rawMaterials": 60
                }
            },
            {
                "name": "USA",
                "military_tensions": 40,
                "economicIndicators": {
                    "gdpGrowthRate": 2.5,
                    "unemploymentRate": 4.2,
                    "inflationRate": 5.0
                },
                "domesticStability": 80,
                "politicalSystem": "Constitutional Federal Republic",
                "resources": {
                    "foodSupply": 95,
                    "rawMaterials": 80
                }
            },
            {
                "name": "Soviet Remnants",
                "military_tensions": 70,
                "economicIndicators": {
                    "gdpGrowthRate": -1.5,
                    "unemploymentRate": 10.0,
                    "inflationRate": 9.0
                },
                "domesticStability": 45,
                "politicalSystem": "Communist Holdout",
                "resources": {
                    "foodSupply": 60,
                    "rawMaterials": 90
                }
            }
        ],
        "conflicts": {
            "activeWars": [
                # Example: an ongoing war with minimal casualties so far
                {
                    "conflictName": "Eastern Border Conflict",
                    "startDate": "1974-06-10",
                    "endDate": None,
                    "status": "Ongoing",
                    "belligerents": {
                        "sideA": ["Soviet Remnants"],
                        "sideB": ["Germany"]
                    },
                    "casualties": {
                        "military": 1500,
                        "civilian": 300
                    },
                    "territorialChanges": []
                }
            ],
            "borderSkirmishes": [],
            "internalUnrest": [
                # Example of minor internal unrest
                {
                    "movementName": "Workers Reform League",
                    "startDate": "1974-11-01",
                    "endDate": None,
                    "cause": "Economic inequality",
                    "affectedRegions": ["Hamburg", "Berlin"],
                    "governmentResponse": "Ongoing",
                    "casualties": 20
                }
            ],
            "proxyWars": []
        },
        "globalEconomy": [
            # Example of a moderate recession event
            {
                "eventId": "ECO-1974-001",
                "name": "European Recession",
                "date": "1974-12-15",
                "type": "Recession",
                "location": {
                    "country": "Germany",
                    "region": "Central Europe",
                    "globalImpact": False
                },
                "causes": [
                    "Oil crisis",
                    "High inflation"
                ],
                "keyFigures": ["Bundesbank Officials"],
                "impact": [
                    {
                        "category": "Unemployment",
                        "details": {
                            "description": "Rising job losses across manufacturing and services",
                            "affectedEntities": ["Industrial Sector", "Workers"],
                            "quantitativeEffect": {
                                "value": 6.5,
                                "unit": "percent unemployment increase"
                            }
                        }
                    }
                ],
                "internationalResponse": [
                    {
                        "nation": "USA",
                        "reaction": "Offered limited financial assistance and currency swap lines"
                    }
                ],
                "longTermEffects": [
                    "Rise of populist movements",
                    "Increased debt"
                ]
            }
        ],
        "globalEvents": [
            # Example of a generic diplomatic event
            {
                "eventId": "GEN-1974-002",
                "name": "Pan-Atlantic Diplomatic Summit",
                "date": "1974-09-20",
                "type": "Political",
                "location": {
                    "country": "USA",
                    "region": "Washington D.C.",
                    "coordinates": {
                        "latitude": 38.9072,
                        "longitude": -77.0369
                    }
                },
                "causes": ["Regional security agreements"],
                "impact": [
                    {
                        "category": "Diplomacy",
                        "details": {
                            "description": "Slight thaw in tensions between Germany and the Soviet Remnants",
                            "affectedEntities": ["USA", "Germany", "Soviet Remnants"]
                        }
                    }
                ],
                "longTermEffects": [
                    "Temporary reduction in military tensions"
                ],
                "internationalResponse": [
                    {
                        "nation": "United Kingdom",
                        "reaction": "Supported continued dialogues"
                    }
                ]
            }
        ],
        "humanitarianCrises": [
            # No major crisis yet
        ],
        "naturalDisasters": [
            # Potential minor disaster example
            {
                "disasterType": "Flood",
                "location": "Mississippi River Basin",
                "date": "1974-10-05",
                "magnitude": 6.2,
                "casualties": 120,
                "economicDamage": "$3 billion",
                "affectedPopulation": 50000,
                "disasterResponse": {
                    "evacuations": 10000,
                    "aidProvided": "$50 million",
                    "internationalAssistance": False
                },
                "environmentalImpact": {
                    "co2Released": 0,
                    "habitatDestruction": "Moderate",
                    "waterContamination": True
                }
            }
        ],
        "politicalEvents": [
            # Using the political_events schema
            {
                "eventId": "POL-1974-003",
                "name": "Snap Elections in Germany",
                "date": "1974-10-30",
                "type": "Election",
                "location": {
                    "country": "Germany",
                    "region": "Nationwide",
                    "coordinates": {
                        "latitude": 51.1657,
                        "longitude": 10.4515
                    }
                },
                "causes": ["Government instability", "Economic crisis"],
                "keyFigures": ["Chancellor Candidate A", "Opposition Leader B"],
                "impact": [
                    {
                        "category": "Governance",
                        "details": {
                            "description": "Shifts in parliament seats",
                            "affectedEntities": ["Germany's Parliament"],
                            "quantitativeEffect": {
                                "value": 12,
                                "unit": "seat changes"
                            }
                        }
                    }
                ],
                "internationalResponse": [
                    {
                        "nation": "USA",
                        "reaction": "Observed with supportive statements"
                    }
                ],
                "longTermEffects": [
                    "Potential coalition government"
                ]
            }
        ],
        "politicalViolence": [
            {
                "eventId": "PV-1974-001",
                "name": "Assassination of Former Minister",
                "date": "1974-07-10",
                "type": "Assassination",
                "location": {
                    "country": "Germany",
                    "city": "Munich",
                    "coordinates": {
                        "latitude": 48.1351,
                        "longitude": 11.5820
                    }
                },
                "perpetrators": ["Radical Separatist Faction"],
                "target": {
                    "name": "Gerhard Müller",
                    "role": "Former Finance Minister",
                    "affiliation": "Centrist Party"
                },
                "casualties": {
                    "fatalities": 1,
                    "injuries": 2
                },
                "motive": "Political protest against austerity measures",
                "method": "Sniper attack",
                "impact": [
                    {
                        "category": "Security Measures",
                        "details": {
                            "description": "Heightened police presence",
                            "affectedEntities": ["Munich Police", "Political Rallies"]
                        }
                    }
                ],
                "internationalResponse": [],
                "longTermEffects": [
                    "Stricter security at public events"
                ]
            }
        ],
        "scientificDiscoveries": [
            {
                "discoveryName": "Advanced Fusion Reactor",
                "date": "1974-08-20",
                "field": "Energy",
                "impactLevel": "Moderate",
                "contributingNations": ["USA", "Germany"],
                "practicalApplications": ["Clean Energy Production", "Experimental Power Grids"],
                "keyFigures": ["Dr. Hans Keller", "Prof. Linda Rodgers"],
                "impact": [
                    {
                        "category": "Energy Supply",
                        "details": {
                            "description": "Potential to reduce reliance on fossil fuels",
                            "affectedEntities": ["Power Plants", "Oil Industry"],
                            "quantitativeEffect": {
                                "value": 20,
                                "unit": "percent cost reduction in electricity"
                            }
                        }
                    }
                ],
                "internationalResponse": [
                    {
                        "nation": "Soviet Remnants",
                        "reaction": "Criticized Western dominance in technology"
                    }
                ],
                "longTermEffects": [
                    "Gradual energy transition",
                    "Reduced carbon emissions"
                ]
            }
        ]
    }


    engine = EventEngine(global_state)
    
    # Let's do a single step with user input
    result_summary = engine.run_simulation_step(user_input="Prevent war if possible")
    print("[SUMMARY OF NEW EVENTS]")
    print(result_summary)
    print("\n[UPDATED GLOBAL STATE]")
    print(json.dumps(global_state, indent=2))
