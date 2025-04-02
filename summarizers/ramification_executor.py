#!/usr/bin/env python3
"""
ramification_executor.py

Applies the specific state changes defined by pending Ramification objects
within the simulation's global_state.
"""

import json
from datetime import datetime
# Consider using a library for safe nested dictionary access/modification if needed
# from jsonpath_ng import jsonpath, parse # Example library

class RamificationExecutor:
    """
    Executes pending ramifications stored in the global_state.
    """

    def __init__(self, global_state: dict):
        """
        Initialize the executor with the simulation's global state.

        :param global_state: The main dictionary holding all simulation data.
        """
        self.global_state = global_state
        # Ensure ramifications list exists
        self.global_state.setdefault("ramifications", [])

    def _get_nested_value(self, path: str):
        """
        Safely retrieves a value from the global_state using a dot-notation path.
        Returns the value and its parent dictionary, or (None, None) if path is invalid.
        """
        keys = path.split('.')
        current_level = self.global_state
        parent = None
        last_key = keys[-1]

        try:
            for i, key in enumerate(keys[:-1]):
                if isinstance(current_level, dict) and key in current_level:
                    parent = current_level
                    current_level = current_level[key]
                elif isinstance(current_level, list) and key.isdigit():
                    idx = int(key)
                    if 0 <= idx < len(current_level):
                        parent = current_level
                        current_level = current_level[idx]
                    else:
                        return None, None # Index out of bounds
                else:
                    return None, None # Invalid path segment

            # Now check the final key
            if isinstance(current_level, dict) and last_key in current_level:
                return current_level[last_key], current_level # Return value and its direct parent dict
            elif isinstance(current_level, list) and last_key.isdigit():
                 idx = int(last_key)
                 if 0 <= idx < len(current_level):
                     return current_level[idx], current_level # Return value and its parent list
                 else:
                     return None, None # Index out of bounds
            else:
                 return None, None # Final key not found

        except (TypeError, IndexError, KeyError):
            return None, None # Error during path traversal

    def _set_nested_value(self, path: str, value):
        """
        Safely sets a value in the global_state using a dot-notation path.
        Creates intermediate dictionaries if they don't exist.
        Returns True on success, False on failure.
        """
        keys = path.split('.')
        current_level = self.global_state
        try:
            for i, key in enumerate(keys[:-1]):
                if isinstance(current_level, dict):
                    if key not in current_level:
                        # Create intermediate dict if path indicates one
                        if i + 1 < len(keys) and not keys[i+1].isdigit():
                             current_level[key] = {}
                        else: # Assume list if next key is digit, handle error later if needed
                             current_level[key] = []
                    current_level = current_level[key]
                elif isinstance(current_level, list) and key.isdigit():
                     idx = int(key)
                     if 0 <= idx < len(current_level):
                         current_level = current_level[idx]
                     # Cannot reliably create intermediate lists/dicts within lists this way
                     # Requires more complex logic or assumptions about structure
                     else: return False # Index out of bounds or cannot create intermediate list element
                else:
                    return False # Invalid path segment

            # Set the final value
            last_key = keys[-1]
            if isinstance(current_level, dict):
                current_level[last_key] = value
                return True
            elif isinstance(current_level, list) and last_key.isdigit():
                 idx = int(last_key)
                 if 0 <= idx < len(current_level):
                     current_level[idx] = value
                     return True
                 elif idx == len(current_level): # Allow appending
                      current_level.append(value)
                      return True
                 else: return False # Index out of bounds for setting
            else:
                return False # Cannot set value on non-dict/list parent

        except (TypeError, IndexError, ValueError):
            return False # Error during path traversal or setting

    def execute_pending_ramifications(self, current_sim_time_str: str):
        """
        Finds and executes all pending ramifications whose execution time is due.

        :param current_sim_time_str: The current simulation time as an ISO 8601 string (e.g., "YYYY-MM-DDTHH:MM:SS").
        """
        try:
            current_time = datetime.fromisoformat(current_sim_time_str)
        except ValueError:
            print(f"Error: Invalid current_sim_time_str format: {current_sim_time_str}")
            return

        executed_count = 0
        failed_count = 0

        # Iterate through a copy of the indices to allow modification during loop
        indices_to_process = [i for i, ram in enumerate(self.global_state["ramifications"]) if ram.get("status") == "pending"]

        for index in indices_to_process:
            # Re-fetch ramification in case list was modified (less likely with index iteration)
            if index >= len(self.global_state["ramifications"]): continue # Index out of bounds
            ram = self.global_state["ramifications"][index]

            if ram.get("status") != "pending":
                continue # Already processed or cancelled

            try:
                execution_time = datetime.fromisoformat(ram["executionTime"])
            except (ValueError, KeyError):
                ram["status"] = "failed"
                ram["failureReason"] = "Invalid or missing executionTime format."
                failed_count += 1
                continue

            if execution_time <= current_time:
                target_path = ram.get("targetPath")
                operation = ram.get("operation")
                value = ram.get("value") # Keep original type

                if not target_path or not operation:
                    ram["status"] = "failed"
                    ram["failureReason"] = "Missing targetPath or operation."
                    failed_count += 1
                    continue

                success = False
                error_msg = "Execution failed."
                try:
                    current_value, parent = self._get_nested_value(target_path)
                    last_key = target_path.split('.')[-1]

                    if parent is None and operation != 'set': # Cannot get parent means path invalid for most ops
                         raise ValueError(f"Invalid targetPath: '{target_path}'")

                    if operation == "set":
                        success = self._set_nested_value(target_path, value)
                        if not success: error_msg = f"Failed to set value at path '{target_path}'."
                    elif operation == "add":
                        if isinstance(current_value, (int, float)) and isinstance(value, (int, float)):
                            parent[last_key] = current_value + value
                            success = True
                        elif isinstance(current_value, list):
                            parent[last_key].append(value)
                            success = True
                        else: error_msg = f"Cannot add: type mismatch or invalid path '{target_path}' (current: {type(current_value)}, value: {type(value)})."
                    elif operation == "subtract":
                         if isinstance(current_value, (int, float)) and isinstance(value, (int, float)):
                            parent[last_key] = current_value - value
                            success = True
                         else: error_msg = f"Cannot subtract: type mismatch or invalid path '{target_path}'."
                    elif operation == "multiply":
                         if isinstance(current_value, (int, float)) and isinstance(value, (int, float)):
                            parent[last_key] = current_value * value
                            success = True
                         else: error_msg = f"Cannot multiply: type mismatch or invalid path '{target_path}'."
                    elif operation == "divide":
                         if isinstance(current_value, (int, float)) and isinstance(value, (int, float)) and value != 0:
                            parent[last_key] = current_value / value
                            success = True
                         elif value == 0: error_msg = "Cannot divide by zero."
                         else: error_msg = f"Cannot divide: type mismatch or invalid path '{target_path}'."
                    elif operation == "remove_item":
                        if isinstance(parent, list) and last_key.isdigit(): # Removing by index
                             idx = int(last_key)
                             if 0 <= idx < len(parent):
                                 del parent[idx]
                                 success = True
                             else: error_msg = f"Index {idx} out of bounds for remove_item."
                        elif isinstance(current_value, list): # Removing by value or identifier from list at parent[last_key]
                             item_to_remove = value
                             identifier = ram.get("valueIdentifier") # e.g., {"id": "item-123"} or just "item-123"
                             removed = False
                             new_list = []
                             for item in current_value:
                                 match = False
                                 if identifier:
                                     # Match based on identifier (assuming identifier is a dict key like 'id')
                                     if isinstance(identifier, dict) and isinstance(item, dict):
                                         id_key = list(identifier.keys())[0]
                                         id_val = identifier[id_key]
                                         if item.get(id_key) == id_val:
                                             match = True
                                     # Match based on identifier being the value itself (for lists of simple values)
                                     elif item == identifier:
                                          match = True
                                 # Fallback to matching the whole value if no identifier
                                 elif item == item_to_remove:
                                     match = True

                                 if match:
                                     removed = True
                                     # Don't add the item to the new list
                                 else:
                                     new_list.append(item)

                             if removed:
                                 parent[last_key] = new_list
                                 success = True
                             else: error_msg = f"Item not found for remove_item using value/identifier."
                        else: error_msg = f"Cannot remove_item: target path '{target_path}' is not a list or index."
                    elif operation == "update_item":
                         if not isinstance(current_value, list):
                              error_msg = f"Cannot update_item: target path '{target_path}' does not point to a list."
                         else:
                             identifier = ram.get("valueIdentifier") # e.g., {"id": "item-123"}
                             new_value = value # The new data for the item
                             updated = False
                             if not identifier or not isinstance(identifier, dict):
                                  error_msg = "update_item requires a valueIdentifier (e.g., {'id': 'value-to-match'})."
                             else:
                                 id_key = list(identifier.keys())[0]
                                 id_val = identifier[id_key]
                                 for i, item in enumerate(current_value):
                                     if isinstance(item, dict) and item.get(id_key) == id_val:
                                         # Update the item - merge or replace? Let's merge for now.
                                         if isinstance(new_value, dict):
                                             item.update(new_value) # Merge new data into existing item
                                             updated = True
                                             break
                                         else: # Replace if new value isn't a dict
                                              current_value[i] = new_value
                                              updated = True
                                              break
                                 if updated:
                                     success = True
                                 else:
                                     error_msg = f"Item not found for update_item using identifier {identifier}."
                    else:
                        error_msg = f"Unsupported operation: '{operation}'."

                except Exception as e:
                    success = False
                    error_msg = f"Exception during execution: {e}"

                if success:
                    ram["status"] = "executed"
                    executed_count += 1
                else:
                    ram["status"] = "failed"
                    ram["failureReason"] = error_msg
                    failed_count += 1

        if executed_count > 0 or failed_count > 0:
            print(f"Ramification Executor: Executed={executed_count}, Failed={failed_count}")


# Example usage (would typically be called from time_engine.py)
if __name__ == "__main__":
    print("Running Ramification Executor example...")
    # Example state with pending ramifications
    example_global_state = {
        "current_date": "1975-01-31", # Set by time engine before calling executor
        "nations": {
            "USA": {
                "nationId": "USA",
                "name": "United States",
                "internalAffairs": {"stability": 50, "publicApproval": 60},
                "economy": {"gdp": 1000, "unemploymentRate": 0.05},
                "nationwideImpacts": []
            },
             "USSR": {
                "nationId": "USSR",
                "name": "Soviet Union",
                "internalAffairs": {"stability": 70},
                "economy": {"gdp": 800},
                "nationwideImpacts": []
            }
        },
        "globalEvents": [],
        "effects": [],
        "ramifications": [
            {
                "ramificationId": str(uuid.uuid4()),
                "originEffectId": "effect1",
                "nationId": "USA",
                "description": "Decrease stability due to protest effect.",
                "targetPath": "nations.USA.internalAffairs.stability",
                "operation": "subtract",
                "value": 5,
                "executionTime": "1975-01-15T10:00:00", # Past due
                "status": "pending"
            },
            {
                "ramificationId": str(uuid.uuid4()),
                "originEffectId": "effect2",
                "nationId": "USA",
                "description": "Increase GDP due to economic effect.",
                "targetPath": "nations.USA.economy.gdp",
                "operation": "add",
                "value": 50.5,
                "executionTime": "1975-01-30T12:00:00", # Past due
                "status": "pending"
            },
             {
                "ramificationId": str(uuid.uuid4()),
                "originEffectId": "effect3",
                "nationId": "USSR",
                "description": "Set new policy flag.",
                "targetPath": "nations.USSR.internalAffairs.newPolicyActive", # Path doesn't exist initially
                "operation": "set",
                "value": True,
                "executionTime": "1975-01-20T00:00:00", # Past due
                "status": "pending"
            },
            {
                "ramificationId": str(uuid.uuid4()),
                "originEffectId": "effect4",
                "nationId": "USA",
                "description": "Future stability increase.",
                "targetPath": "nations.USA.internalAffairs.stability",
                "operation": "add",
                "value": 10,
                "executionTime": "1975-02-10T00:00:00", # Future
                "status": "pending"
            },
             {
                "ramificationId": str(uuid.uuid4()),
                "originEffectId": "effect5",
                "nationId": "USA",
                "description": "Invalid path test.",
                "targetPath": "nations.USA.nonExistent.value",
                "operation": "set",
                "value": 100,
                "executionTime": "1975-01-01T00:00:00", # Past due
                "status": "pending"
            }
        ]
    }

    executor = RamificationExecutor(example_global_state)
    current_sim_iso_time = "1975-01-31T00:00:00" # Example current time
    print(f"Executing ramifications due by {current_sim_iso_time}...")
    executor.execute_pending_ramifications(current_sim_iso_time)

    print("\n=== Final Global State ===")
    # Use default=str for datetime objects if they were ever added to state
    print(json.dumps(example_global_state, indent=2, default=str))
