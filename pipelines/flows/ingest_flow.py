from prefect import flow, task
import json

@task
def load_logs():
    print("Loading logs...")
    return [{"query": "What is AI?"}]

@task
def clean_data(data):
    print("Cleaning data...")
    return [d["query"] for d in data]

@flow
def ingest_pipeline():
    print("Pipeline started 🚀")
    data = load_logs()
    clean = clean_data(data)
    print("Final:", clean)

if __name__ == "__main__":
    ingest_pipeline()