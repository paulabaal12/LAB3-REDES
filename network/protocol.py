import time

def make_message(msg_type, from_id, to_id, payload=None, headers=None, hops=0):
    return {
        "type": msg_type,
        "from": from_id,
        "to": to_id,
        "hops": hops,
        "headers": headers or {},
        "payload": payload or "",
        "timestamp": time.time()
    }
