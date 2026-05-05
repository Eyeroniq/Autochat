import os
import json
import time
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from llmware.models import ModelCatalog

from pipelines.flows.ingest_flow import ingest_pipeline
from backend.vector_store import search_memory, add_to_memory, collection

# -------------------- INIT --------------------

os.environ["OMP_NUM_THREADS"] = "1"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load model
model = ModelCatalog().load_model(
    "bling-phi-3-gguf",
    temperature=0.2,
    sample=False
)

# -------------------- SCHEMAS --------------------

class QueryRequest(BaseModel):
    query: str

class FeedbackRequest(BaseModel):
    query: str
    feedback: str

# -------------------- METRICS --------------------

REQUEST_COUNT = Counter(
    "total_requests",
    "Total API Requests",
    ["endpoint"]
)

FEEDBACK_COUNT = Counter(
    "feedback_count",
    "Total Feedback Given",
    ["type"]
)

RESPONSE_TIME = Histogram(
    "response_time_seconds",
    "Response time"
)

CONFIDENCE_SCORE = Gauge(
    "confidence_score",
    "Simulated model confidence score"
)

EMBEDDING_AGE = Gauge(
    "embedding_age_days",
    "Simulated embedding age in days"
)

UPDATE_TRIGGER = Gauge(
    "update_trigger_flag",
    "1 if update needed, 0 otherwise"
)

# -------------------- HELPERS --------------------

def normalize_query(query: str) -> str:
    query = query.strip().lower()
    if not query.endswith("?"):
        query += "?"
    return query


def log_query(query):
    path = "backend/logs/queries.json"

    os.makedirs(os.path.dirname(path), exist_ok=True)

    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump([], f)

    with open(path, "r+") as f:
        try:
            data = json.load(f)
        except:
            data = []

        data.append({"query": query, "time": time.time()})

        f.seek(0)
        json.dump(data, f, indent=2)
        f.truncate()


def generate_improved_answer(query):
    prompt = f"""
You are an expert AI assistant.

Give a clear, correct, and complete answer in 2-3 sentences.
Do not give one-word answers.
Do not repeat the question.

Question: {query}
Answer:
"""
    response = model.inference(prompt)
    answer = response["llm_response"] if isinstance(response, dict) else response
    return answer.strip()

# -------------------- ROUTES --------------------

@app.post("/chat")
def chat(request: QueryRequest):
    start = time.time()

    REQUEST_COUNT.labels(endpoint="chat").inc()

    query = normalize_query(request.query)

    log_query(query)

    try:
        context_list = search_memory(query)

        if context_list:
            context_text = "\n".join(context_list)

            prompt = f"""
You are a smart AI assistant.

Use the context below if relevant.

Context:
{context_text}

Question: {query}

Give a clear, structured answer in 2-3 sentences.
"""
            response = model.inference(prompt)
            answer = response["llm_response"] if isinstance(response, dict) else response
            source = "rag"

        else:
            response = model.inference(query)
            answer = response["llm_response"] if isinstance(response, dict) else response
            source = "model"

    except Exception as e:
        return {"response": "Error generating response", "error": str(e)}

    # ---------------- OBSERVABILITY ----------------

    import random

    confidence = random.uniform(0.3, 0.9)
    CONFIDENCE_SCORE.set(confidence)

    age_days = random.randint(1, 15)
    EMBEDDING_AGE.set(age_days)

    if confidence < 0.5 or age_days > 7:
        UPDATE_TRIGGER.set(1)
    else:
        UPDATE_TRIGGER.set(0)

    RESPONSE_TIME.observe(time.time() - start)

    return {
        "response": answer,
        "source": source,
        "confidence": round(confidence, 2),
        "embedding_age_days": age_days
    }


@app.post("/feedback")
def feedback(request: FeedbackRequest):
    start = time.time()

    if request.feedback.lower() not in ["no", "not useful"]:
        return {"status": "ignored"}

    FEEDBACK_COUNT.labels(type="negative").inc()

    query = normalize_query(request.query)

    improved = generate_improved_answer(query)

    add_to_memory(query, improved)

    RESPONSE_TIME.observe(time.time() - start)

    return {"status": "stored"}


@app.get("/debug-memory")
def debug_memory():
    data = collection.get()

    return {
        "stored_queries": data["ids"],
        "stored_answers": data["documents"]
    }


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")


@app.post("/run-pipeline")
def run_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(ingest_pipeline)
    return {"status": "Pipeline running in background"}