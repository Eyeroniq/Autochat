from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "chroma_db")

# 🔥 THIS IS THE REAL FIX
chroma_client = PersistentClient(path=DB_PATH)

collection = chroma_client.get_or_create_collection("chat_memory")

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


def get_embedding(text):
    return embedding_model.encode(text).tolist()


# -------------------- ADD MEMORY --------------------

def add_to_memory(query, answer):
    try:
        embedding = get_embedding(query)

        collection.add(
            documents=[answer],
            embeddings=[embedding],
            ids=[str(hash(query))]  # unique id
        )

        print("✅ Added to Chroma memory")

    except Exception as e:
        print("❌ Error adding to Chroma:", e)


# -------------------- SEARCH MEMORY --------------------

def search_memory(query):
    embedding = get_embedding(query)

    results = collection.query(
        query_embeddings=[embedding],
        n_results=2   # 🔥 get more context
    )

    if not results["documents"]:
        return []

    docs = results["documents"][0]
    distances = results["distances"][0]

    context = []

    for doc, dist in zip(docs, distances):
        if dist < 0.5:   # relaxed threshold
            context.append(doc)

    return context