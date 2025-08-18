import json

def load_topology(file_path):
    with open(file_path) as f:
        data = json.load(f)
    return data["config"]

def load_names(file_path):
    with open(file_path) as f:
        data = json.load(f)
    return data["config"]
