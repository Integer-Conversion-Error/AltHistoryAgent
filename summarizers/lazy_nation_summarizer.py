import os
import json
from typing import List
import google.generativeai as genai
from summarizers.initializer_util import *



def gather_json_files(root_folder: str) -> List[str]:
    """
    Recursively gather all .json files from the given root folder.
    """
    json_files = []
    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.endswith(".json"):
                full_path = os.path.join(dirpath, filename)
                json_files.append(full_path)
    return json_files

def load_json_content(file_paths: List[str]) -> dict:
    """
    Load and return the content of each JSON file as a dict keyed by filename.
    """
    all_content = {}
    for path in file_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_content[path] = json.load(f)
        except Exception as e:
            print(f"Error reading {path}: {e}")
    return all_content

def summarize_content(model, all_content: dict) -> str:
    """
    Summarize the combined content of all JSON files using the Gemini model.
    You can customize the prompt as needed for your use-case.
    """
    # Convert all loaded JSON to a text representation
    # For an "exhaustive" summary, you might want to chunk the data if it's large.
    # For simplicity, let's combine everything into one string:
    combined_text = ""
    for filename, content in all_content.items():
        combined_text += f"\n---\nFile: {filename}\n{json.dumps(content, indent=2)}\n"

    prompt = (
        "You are given JSON schemas and data describing nations at different points in history. "
        "Summarize the data *exhaustively*, highlighting key elements, structures, and historical context.\n\n"
        "Here is the data:\n"
        f"{combined_text}\n\n"
        "Now, please provide a comprehensive, structured summary of this information."
    )

    response = model.generate_content(prompt)
    # The model returns a list of generated responses; we’ll assume we want the first.
    return response.text if response and len(response.text) > 0 else ""

def main():
    # 1. Configure the generative model
    model = configure_genai(temp=0.1)

    # 2. Gather all JSON files (adjust 'nation_subschemas' to your actual directory)
    directory_to_scan = "simulation_data/generated_timelines/generated_nations_1965/Soviet Union"
    json_files = gather_json_files(directory_to_scan)

    if not json_files:
        print(f"No .json files were found in {directory_to_scan}")
        return

    # 3. Load JSON content
    all_content = load_json_content(json_files)

    # 4. Summarize the loaded content
    summary = summarize_content(model, all_content)

    # 5. Print or save the summary
    print("\n=== EXHAUSTIVE SUMMARY ===\n")
    print(summary)

def load_and_summarize_nation(nation = "Soviet Union",timeline = "1965"):
    directory_to_scan = f"simulation_data/generated_timelines_{timeline}/generated_nations/{nation}"
    model = configure_genai(temp=0.1)
    json_files = gather_json_files(directory_to_scan)

    if not json_files:
        print(f"No .json files were found in {directory_to_scan}")
        return

    # 3. Load JSON content
    all_content = load_json_content(json_files)

    # 4. Summarize the loaded content
    summary = summarize_content(model, all_content)

    # 5. Print or save the summary
    print("\n=== EXHAUSTIVE SUMMARY ===\n")
    print(summary)
    return summary

if __name__ == "__main__":
    main()
