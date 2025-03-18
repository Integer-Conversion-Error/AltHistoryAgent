#!/usr/bin/env python3

import os
import json
import time
import google.generativeai as genai
from initializer_util import configure_genai  # Or however you normally import this

###############################################################################
#                 LOAD SCHEMAS (SENTIMENT & TRADE) FROM JSON FILES           #
###############################################################################

def load_schema_text(schema_path):
    """
    Loads a JSON schema file as raw text for embedding in the AI prompt.
    """
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file '{schema_path}' not found.")
    with open(schema_path, "r", encoding="utf-8") as f:
        return f.read()

###############################################################################
#                   FETCH COMBINED (SENTIMENT + TRADE) DATA                   #
###############################################################################

def fetch_combined_data_for_pair(nationA, nationB, year, relation_id,
                                 sentiment_schema_text, trade_schema_text, model):
    """
    Makes ONE AI call to get BOTH sentiment (relationship) data AND trade data
    in a single JSON. The AI must output JSON with two top-level keys:
      {
        "sentimentData": { ...one object matching the sentiment schema "items"... },
        "tradeData": { ...one object matching the trade schema "items"... }
      }

    We embed the two schemas in the prompt. Each returned piece is for the same
    two nations in that same year, but they differ in structure:
      - The "sentimentData" must correspond to the one relationship object
        (like the "items" shape in the sentiment schema).
      - The "tradeData" must correspond to one trade object
        (like the "items" shape in the trade schema).

    We'll parse the AI's output, returning (sentiment_obj, trade_obj) if valid.
    If any step fails, we retry up to a maximum number of attempts.
    """
    # Build the single prompt that merges both schemas and instructions
    prompt = f"""
We are modeling a relationship and trade link between two nations: {nationA} and {nationB}, in year {year}.
We have TWO JSON schemas:

1) **Sentiment/Relationship Schema** (one item shape):
{sentiment_schema_text}

2) **Trade Relation Schema** (one item shape):
{trade_schema_text}

You must output a SINGLE valid JSON object with exactly two keys:
  "sentimentData" : one object matching the sentiment schema (single item),
  "tradeData" : one object matching the trade schema (single item).

Constraints:
- For the sentimentData object:
   * "nationA" must be "{nationA}"
   * "nationB" must be "{nationB}"
- For the tradeData object:
   * "relationId" must be "{relation_id}"
   * "year" must be {year}
   * "nationA" must be "{nationA}"
   * "nationB" must be "{nationB}"

Ensure you do NOT wrap them in arrays. Provide exactly these two keys at top-level. 
No extra commentary, code fences, or extra keys. 
    """.strip()

    max_attempts = 8
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        print(f"\n[AI] Attempt {attempt}/{max_attempts} to get combined sentiment+trade for {nationA}-{nationB} (year {year})...")

        try:
            response = model.generate_content(prompt)
            raw_output = response.text.strip()[7:-3]

            # Attempt to parse the entire output as JSON
            combined_obj = json.loads(raw_output)

            # We expect top-level "sentimentData" and "tradeData"
            if "sentimentData" not in combined_obj or "tradeData" not in combined_obj:
                raise ValueError("Response missing 'sentimentData' or 'tradeData' at top-level.")

            sentiment_obj = combined_obj["sentimentData"]
            trade_obj = combined_obj["tradeData"]

            # We could do further validation checks here if needed:
            # e.g. ensure sentiment_obj["nationA"] == nationA, etc.

            return sentiment_obj, trade_obj

        except (json.JSONDecodeError, ValueError) as e:
            print(f"  [ERROR] Parsing/Validation: {e} -- Retrying...")
            time.sleep(2)

        except Exception as e:
            print(f"  [ERROR] Unexpected: {e} -- Retrying...")
            time.sleep(2)

    # If all attempts fail, return fallback structures
    print("  [FAILURE] Reached max attempts. Returning fallback data.")
    fallback_sentiment = {
        "nationA": nationA,
        "nationB": nationB,
        "diplomaticRelations": "Neutral",
        "economicTrust": 50,
        "militaryTensions": 50,
        "ideologicalAlignment": "Neutral",
        "relevantEvents": []
    }
    fallback_trade = {
        "relationId": relation_id,
        "year": year,
        "nationA": nationA,
        "nationB": nationB,
        "totalTradeVolume": "No Trade/Embargo ($0)",
        "tradeDifference": {
            "balance": "Perfectly Balanced (0%)",
            "surplusNation": "",
            "deficitNation": ""
        },
        "exportsFromA": [],
        "exportsFromB": []
    }
    return fallback_sentiment, fallback_trade

###############################################################################
#                   BUILD COMBINED DATA FOR ALL PAIRS                         #
###############################################################################

def build_combined_relations(nations, year,
                             sentiment_schema_text,
                             trade_schema_text,
                             model):
    """
    For each unique pair of nations, we do ONE AI request that returns
    a combined JSON containing both "sentimentData" and "tradeData".
    We accumulate them in two separate lists: sentiments and trades.
    """
    sentiment_relations = []
    trade_relations = []
    relation_id_counter = 1

    for i in range(len(nations)):
        for j in range(i+1, len(nations)):
            nationA = nations[i]
            nationB = nations[j]
            relation_id = f"rel-{relation_id_counter}"
            relation_id_counter += 1

            # Single call to fetch combined data
            sentiment_obj, trade_obj = fetch_combined_data_for_pair(
                nationA=nationA,
                nationB=nationB,
                year=year,
                relation_id=relation_id,
                sentiment_schema_text=sentiment_schema_text,
                trade_schema_text=trade_schema_text,
                model=model
            )
            sentiment_relations.append(sentiment_obj)
            trade_relations.append(trade_obj)

    return sentiment_relations, trade_relations

###############################################################################
#                      SAVE SENTIMENT & TRADE FILES SEPARATELY                #
###############################################################################

def save_global_sentiment(sentiment_data, filename="global_sentiment.json"):
    """
    Saves the final array of sentiment relations to JSON.
    """
    if not sentiment_data:
        print("No sentiment data to save.")
        return
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(sentiment_data, f, indent=2)
    print(f"Saved {len(sentiment_data)} sentiment items to {filename}")

def save_trade_relations(trade_data, filename="global_trade.json"):
    """
    Saves the final array of trade relations to JSON.
    """
    if not trade_data:
        print("No trade data to save.")
        return
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(trade_data, f, indent=2)
    print(f"Saved {len(trade_data)} trade items to {filename}")

###############################################################################
#                                   MAIN                                      #
###############################################################################

def main():
    """
    Example usage: 
    We'll load the two schemas, pick a set of nations, do a single AI call 
    per pair, parse out the 'sentiment' vs. 'trade' data, and save them separately.
    """
    # 1) Configure the AI model
    global model
    model = configure_genai(temp=0.5, model="gemini-2.0-flash-exp")

    # 2) Load the two schemas
    sentiment_schema_text = load_schema_text("global_subschemas/global_sentiment_schema.json")
    trade_schema_text = load_schema_text("global_subschemas/global_trade_schema.json")

    # 3) Example data
    nations = ["US", "UK", "USSR"]
    year = 1985

    # 4) Build combined data
    sentiment_list, trade_list = build_combined_relations(
        nations=nations,
        year=year,
        sentiment_schema_text=sentiment_schema_text,
        trade_schema_text=trade_schema_text,
        model=model
    )

    # 5) Save them into separate files
    save_global_sentiment(sentiment_list, "global_sentiment.json")
    save_trade_relations(trade_list, "global_trade.json")

def initialize_combined(nations, year):
    """
    A wrapper function to run the combined generation for 
    an arbitrary set of nations, year, and output files.
    """
    global model
    model = configure_genai(temp=0.5, model="gemini-2.0-flash-exp")
    
    sentiment_schema_text = load_schema_text("global_subschemas/global_sentiment_schema.json")
    trade_schema_text = load_schema_text("global_subschemas/global_trade_schema.json")

    sentiment_list, trade_list = build_combined_relations(
        nations=nations,
        year=year,
        sentiment_schema_text=sentiment_schema_text,
        trade_schema_text=trade_schema_text,
        model=model
    )
    filename = f"simulation_data/generated_timeline_{year}/"
    save_global_sentiment(sentiment_list, filename+"global_sentiment.json")
    save_trade_relations(trade_list, filename+"global_trade.json")

    return sentiment_list, trade_list

if __name__ == "__main__":
    main()
