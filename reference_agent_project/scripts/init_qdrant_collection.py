from app.services.qdrant_store import QdrantStore

if __name__ == '__main__':
    QdrantStore().ensure_collection()
    print('collection ready')
