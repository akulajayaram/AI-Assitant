import redis
import json

redis_client = redis.Redis(host="localhost", port=6379, db=0)

def save_session(session_id, history):
    redis_client.set(session_id, json.dumps(history))

def load_session(session_id):
    data = redis_client.get(session_id)
    if data:
        return json.loads(data)
    return None