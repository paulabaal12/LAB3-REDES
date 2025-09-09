import uuid

def make_message(proto, mtype, src, dst, payload, headers=None, ttl=32):
    return {
        "proto": proto,                        # algoritmo: dijkstra|flooding|lsr|dvr
        "type": mtype,                         # tipo de mensaje: message|echo|info|hello
        "from": f"{src}@localhost/{uuid.uuid4().hex[:6]}",  # formato foo@bar/123
        "to": f"{dst}@localhost/000000",       # simplificado
        "ttl": ttl,
        "headers": headers or {},
        "payload": payload,
    }
