import chromadb

def store_in_chroma(data):
    client = chromadb.Client()
    collection = client.get_or_create_collection("rag-db")

    for i, (text, emb) in enumerate(data):
        collection.add(
            documents=[text],
            embeddings=[emb],
            ids=[str(i)]
        )