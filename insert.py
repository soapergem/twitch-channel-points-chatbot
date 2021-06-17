#!/usr/bin/env python
import csv

from google.cloud import firestore

# configure this variable to indicate which line to begin the import
# note that for all intents and purposes, the header line is line 0
STARTING_LINE = 1

# configure this variable to indicate which ID to start inserting at
# for the first run, make sure this is set to 1
STARTING_ID = 1

db = firestore.Client()
quotes = db.collection("lotr-quotes")
id = STARTING_ID
line_no = 1

with open("quotes.csv") as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        if line_no >= STARTING_LINE:
            entry = {
                "id": id,
                "quote": row.get("Quote"),
                "source": row.get("Source"),
                "source_type": row.get("Type"),
                "speaker": row.get("Speaker"),
            }
            quotes.add(entry)
            id += 1
        line_no += 1

print(f"Last ID: {id}")
