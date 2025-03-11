#!/usr/bin/env python3
"""
time_engine.py

Handles the main simulation flow for an AI-driven alternate history scenario,
tying together timeline advancement, event checking, ramifications application,
and user/AI interactions.

Requirements/Context:
- Relies on the event_engine.py code (EventEngine class) for condition checking
  and event generation.
- Potentially references high_level_context_distributor.py, low_level_summarizer.py,
  generate_event.py, low_level_writer.py, nation_initalizer.py, etc. 
  (In real usage, you import relevant functions/classes from those modules.)
- The user has a global_state JSON or Python dictionary that includes "current_date"
  and other data needed for the simulation.
- This file can be extended or adapted to unify the entire simulation loop.
"""

import os
import sys
import time
import datetime
import json

# Adjust imports based on your actual package layout. For demonstration, we assume:
# - event_engine.py in the same directory
# - other modules in sibling directories or an installed package.

try:
    import sys
    sys.path.append("summarizers")  # Add the folder to the system path
    from event_engine import EventEngine  # Import the EventEngine class

except ImportError:
    print("Error: Could not import EventEngine from event_engine.py. Check file structure.")
    sys.exit(1)

# Potential optional imports from your other modules:
# from high_level_context_distributor import manage_json_queries, ...
# from low_level_summarizer import perform_summarization, ...
# from generate_event import generate_global_event_json, ...
# from low_level_writer import produce_structured_data
# from nation_initalizer import fill_nation_data_with_paragraphs


def load_global_state(global_state_path: str) -> dict:
    """
    Loads the global state JSON from a file.
    If the file does not exist, creates a minimal default state.

    :param global_state_path: Path to the JSON file holding the simulation state.
    :return: Parsed global_state as a Python dictionary.
    """
    if not os.path.exists(global_state_path):
        # Provide a minimal stub if none is found
        print(f"Warning: {global_state_path} not found. Creating a default global state.")
        return {
            "current_date": "1970-01-01",
            "nations": [],
            "conflicts": {
                "activeWars": [],
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
    else:
        with open(global_state_path, "r", encoding="utf-8") as file:
            return json.load(file)


def save_global_state(global_state: dict, global_state_path: str):
    """
    Saves the updated global state to disk as JSON.

    :param global_state: The updated state dictionary.
    :param global_state_path: Path to the JSON file where state is stored.
    """
    os.makedirs(os.path.dirname(global_state_path), exist_ok=True)
    with open(global_state_path, "w", encoding="utf-8") as file:
        json.dump(global_state, file, indent=2)


class TimeEngine:
    """
    The TimeEngine orchestrates the main simulation loop, using EventEngine
    for condition checks, user input, and timeline progression.
    """

    def __init__(self, global_state_file: str = "simulation_data/global_state.json"):
        """
        Initializes the TimeEngine by loading or creating the global state, 
        and creating an EventEngine instance to handle event logic.

        :param global_state_file: Path to the global state JSON.
        """
        self.global_state_path = global_state_file
        self.global_state = load_global_state(global_state_file)
        self.engine = EventEngine(self.global_state)  # From event_engine.py
        # Additional parameters or advanced logic can be included here.

    def main_loop(self):
        """
        Primary simulation loop for the scenario. Repeats steps until user quits
        or the simulation hits an end condition.
        """
        # Example user-driven approach:
        while True:
            # 1) Display current date & ask user input
            current_date = self.global_state.get("current_date", "????-??-??")
            print(f"\n===== TimeEngine - Current Date: {current_date} =====")
            user_input = input("Enter command (or 'exit' to stop): ").strip().lower()

            if user_input in ["exit", "quit"]:
                print("Exiting simulation.")
                break

            # 2) Run one simulation step with optional user input
            summary = self.engine.run_simulation_step(user_input=user_input)
            print("\n--- Simulation Step Summary ---")
            print(summary)

            # 3) Save the updated global state
            save_global_state(self.global_state, self.global_state_path)
            print(f"State saved to {self.global_state_path}.")
            
            # 4) Possibly show user the next date or any new events
            # This loop then repeats.

    def run_auto_steps(self, steps: int = 12, days_per_step: int = 30):
        """
        Runs a fixed number of simulation steps automatically, for a hands-off approach.

        :param steps: How many simulation steps to advance.
        :param days_per_step: How many days each step moves forward.
        """
        for i in range(1, steps + 1):
            print(f"\n=== Automatic Step {i}/{steps} ===")
            # No user input in this mode
            summary = self.engine.run_simulation_step(user_input="")
            print(f"Summary of Step {i}:\n{summary}")
            # Save after each step
            save_global_state(self.global_state, self.global_state_path)
            print(f"Current Date: {self.global_state['current_date']}")
            time.sleep(1)  # small delay for demonstration

    def jump_to_date(self, target_date: str):
        """
        Moves the simulation forward or backward to a specific date (YYYY-MM-DD).
        This is optional but might be desired for skipping periods.

        If moving backward in time, it doesn't "undo" events - so be careful!
        """
        # Convert current date & target date to datetime objects
        current_dt = datetime.datetime.strptime(self.global_state["current_date"], "%Y-%m-%d")
        target_dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")

        if target_dt <= current_dt:
            print("Warning: Attempting to jump backward or to the same date. This won't revert history.")
        
        days_diff = (target_dt - current_dt).days
        if days_diff > 0:
            # We can do multiple steps or a single big jump:
            self.engine.advance_time(days=days_diff)
            self.global_state["current_date"] = target_date
            print(f"Jumped from {current_dt.strftime('%Y-%m-%d')} to {target_date}.")
        else:
            # If target_dt < current_dt, just set the date, ignoring timeline reversion
            self.global_state["current_date"] = target_date
            print(f"Time moved backward to {target_date}, no events undone though.")

        save_global_state(self.global_state, self.global_state_path)
        print("Global state updated.")

    def incorporate_user_scenario(self, scenario_prompt: str):
        """
        If the user or system wants to incorporate a brand-new scenario,
        we can directly create events or modify nations. This is 
        a conceptual placeholder for advanced logic.
        """
        print("Incorporating user-defined scenario logic (to be implemented).")
        # Possibly call out to 'generate_event.py' or 'low_level_writer.py' with scenario_prompt
        # Then store or schedule those events in the engine's queue.


def main():
    """
    If run as a standalone script, we initialize TimeEngine and start the main loop.
    """
    # Example usage:
    # The global state is stored in simulation_data/global_state.json
    engine = TimeEngine(global_state_file="simulation_data/global_state.json")
    # Launch interactive main loop
    engine.main_loop()

if __name__ == "__main__":
    main()
