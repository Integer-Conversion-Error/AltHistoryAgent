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

# Adjust imports based on your actual package layout.
# Assumes event_engine.py and ramification_executor.py are in the 'summarizers' directory.
try:
    import sys
    # Ensure the summarizers directory is in the path if not running as a package
    if "summarizers" not in sys.path and os.path.exists("summarizers"):
        sys.path.append("summarizers")
    from event_engine import EventEngine
    from ramification_executor import RamificationExecutor

except ImportError as e:
    print(f"Error: Could not import simulation engines. Check file structure and imports: {e}")
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
        self.event_engine = EventEngine(self.global_state)  # Renamed for clarity
        self.ramification_executor = RamificationExecutor(self.global_state) # Instantiate executor
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
            user_input_raw = input("Enter command ('next', 'generate event: <prompt>', 'jump <YYYY-MM-DD>', 'auto <steps>', or 'exit'): ").strip()
            user_input_lower = user_input_raw.lower()

            if user_input_lower in ["exit", "quit"]:
                print("Exiting simulation.")
                break
            elif user_input_lower.startswith("generate event:"):
                # --- NEW: Handle User Event Generation ---
                prompt_text = user_input_raw[len("generate event:"):].strip()
                if prompt_text:
                    print(f"Received request to generate event: '{prompt_text}'")
                    # Call the EventEngine method to generate and queue the event
                    self.event_engine.generate_event_from_prompt(prompt_text)
                    # The event is now in pending_events. It will be processed in the next 'next' command or auto step.
                    print("Event generation requested. Enter 'next' or another command to proceed with the simulation step.")
                    continue # Go back to the start of the loop to wait for the next command
                else:
                    print("Error: 'generate event:' command requires a prompt text.")
                    continue # Ask for input again
            elif user_input_lower.startswith("jump "):
                 target_date_str = user_input_raw[len("jump "):].strip()
                 try:
                     # Basic validation for YYYY-MM-DD format
                     datetime.datetime.strptime(target_date_str, "%Y-%m-%d")
                     self.jump_to_date(target_date_str)
                 except ValueError:
                     print("Invalid date format for jump command. Please use YYYY-MM-DD.")
                 continue # Ask for input again
            elif user_input_lower.startswith("auto "):
                 try:
                     steps = int(user_input_raw[len("auto "):].strip())
                     self.run_auto_steps(steps=steps)
                 except ValueError:
                     print("Invalid number of steps for auto command.")
                 continue # Ask for input again
            elif user_input_lower != "next" and user_input_lower != "": # Treat empty input as 'next'
                 print(f"Unknown command: '{user_input_raw}'. Use 'next', 'generate event:', 'jump', 'auto', or 'exit'.")
                 continue

            # --- Simulation Step (Triggered by 'next' or after auto steps) ---
            # Pass the original user input if it wasn't a special command like 'generate event'
            # If it was 'generate event', pass empty string so it doesn't re-process that.
            sim_step_input = "" if user_input_lower.startswith("generate event:") else user_input_raw

            # 2a) Run Event Engine to generate events and consequences (Impact->Effect->Ramification)
            # Note: EventEngine's run_simulation_step now also advances time internally
            # The user-generated event (if any) is already in pending_events and will be processed here.
            event_summary = self.event_engine.run_simulation_step(user_input=sim_step_input)
            # Summary is now printed within run_simulation_step

            # 2b) Execute pending ramifications that are due by the *new* current time
            current_sim_date_str = self.global_state.get("current_date", "1970-01-01")
            # Format date as ISO datetime string for executor (assuming start of day)
            current_sim_iso_time = f"{current_sim_date_str}T00:00:00"
            print(f"\n--- Executing Ramifications due by {current_sim_iso_time} ---")
            self.ramification_executor.execute_pending_ramifications(current_sim_iso_time)
            # --- End Simulation Step ---


            # 3) Save the updated global state
            save_global_state(self.global_state, self.global_state_path)
            print(f"\nState saved to {self.global_state_path}.")

            # 4) Loop repeats

    def run_auto_steps(self, steps: int = 12, days_per_step: int = 30):
        """
        Runs a fixed number of simulation steps automatically, for a hands-off approach.

        :param steps: How many simulation steps to advance.
        :param days_per_step: How many days each step moves forward.
        """
        # Note: The EventEngine's run_simulation_step now advances time internally.
        # We might need to adjust how days_per_step is handled if EventEngine uses a fixed step.
        # Assuming EventEngine advances by a fixed amount (e.g., 30 days) per call.
        print(f"Running {steps} automatic steps...")
        for i in range(1, steps + 1):
            print(f"\n===== Automatic Step {i}/{steps} =====")
            # --- Simulation Step ---
            # 2a) Run Event Engine (advances time internally)
            event_summary = self.event_engine.run_simulation_step(user_input="")
            print("\n--- Event Generation Summary ---")
            print(event_summary)

            # 2b) Execute pending ramifications for the new current time
            current_sim_date_str = self.global_state.get("current_date", "1970-01-01")
            current_sim_iso_time = f"{current_sim_date_str}T00:00:00"
            print(f"\n--- Executing Ramifications due by {current_sim_iso_time} ---")
            self.ramification_executor.execute_pending_ramifications(current_sim_iso_time)
            # --- End Simulation Step ---

            # Save after each step
            save_global_state(self.global_state, self.global_state_path)
            print(f"\nState saved. Current Date: {self.global_state['current_date']}")
            # time.sleep(0.5) # Shorter delay

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
        # WARNING: Jumping time might skip ramification execution windows.
        # A more robust implementation might run the executor iteratively
        # for each day/week/month being skipped.
        # This simple version just sets the date.

        print(f"Warning: Jumping time directly to {target_date}. Ramifications scheduled between "
              f"{self.global_state['current_date']} and {target_date} might be skipped by this simple jump.")

        self.global_state["current_date"] = target_date
        # Update the EventEngine's internal time step as well
        self.event_engine.time_step = target_dt

        # Optionally run the executor once for the target date?
        # current_sim_iso_time = f"{target_date}T00:00:00"
        # self.ramification_executor.execute_pending_ramifications(current_sim_iso_time)

        save_global_state(self.global_state, self.global_state_path)
        print(f"Time jumped to {target_date}. Global state saved.")

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
    Prompts the user for the simulation start year to load the correct state file.
    """
    # Prompt user for the start year of the simulation to load
    start_year = input("Enter the start year of the simulation to load (e.g., 1975): ").strip()
    if not start_year.isdigit():
        print("Invalid year provided. Exiting.")
        sys.exit(1)

    # Construct the required path using the specified format
    state_file_path = os.path.join("simulation_data", f"generated_timeline_{start_year}", "global_state.json")
    print(f"Attempting to load state from required path: {state_file_path}")

    # Check ONLY the required path
    if not os.path.exists(state_file_path):
        print(f"\nError: Global state file not found at the required path: {state_file_path}")
        print(f"Please ensure the initializer script ran successfully for year {start_year} and the file exists at that exact location.")
        sys.exit(1)

    # If the file exists at the required path, proceed
    print(f"\nLoading simulation state from: {state_file_path}")
    engine = TimeEngine(global_state_file=state_file_path)

    # Launch interactive main loop
    engine.main_loop()

if __name__ == "__main__":
    main()
