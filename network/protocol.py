import uuid
import time

def make_message(proto, mtype, src, dst, payload, headers=None, ttl=32):
    # Obtener el número de nodo desde "nodoN"
    print ({
        "type": mtype,
        "from": f"sec30.{src}",
        "to": f"sec30.{dst}",
        "hops": proto
    })
    return {
        "type": mtype,
        "from": f"sec30.{src}",
        "to": f"sec30.{dst}",
        "hops": proto
    }

def make_table_message(table):
    return {

    }

# ---------- Para new_main.py ----------
def make_hello_message(proto, src, dst, hops):
    print ({
        "type": "hello",
        "from": src,
        "to": dst,
        "hops": hops
    })
    return {
        "type": "hello",
        "from": src,
        "to": dst,
        "hops": hops
    }

def make_info_message(proto, src, dst, edges):
    """
    edges: list of tuples (u, v, weight)
    """
    return {
        "proto": proto,
        "type": "message",
        "from": src,
        "to": dst,
        "edges": edges,
        "timestamp": time.time()
    }


# 1. Inicio el nodo N9, de la topología reconoce a los vecinos N4 y N5 y lo agrega a su tabla, además define un timer de 5 segundos si llega a 0 lo elimina de su tabla

# 2. Se envía msg cada 15 segundos y hello cada 3 segundos a los vecinos
    # En este caso se envía 2 hello a cada vecino:
    # {
    #   type: "hello",
    #   from: "sec30.grupoX.nodoX",
    #   to: "sec30.grupoY.nodoY",
    #   hops: peso entre nodos
    #}
    # Se lee la tabla de la topología y por ejemplo si en la tabla hay 4 conexiones, se envían 4 mensajes a cada vecino; donde cada mensaje contiene las 4 conexiones:
    #{
    #   type: "message",
    #   from: "sec30.grupoX.nodoX",
    #   to: "sec30.grupoY.nodoY",
    #   hops: peso entre nodos
    #}



# 3. Armar topología / Recibir mensajes
    # Se recibe Hello de N4 con hops = 8
        # Se agrega N4 a la topología:
        #
        #{
        #  "N9":{  "N4": { "weight": 8, "time": 5},
        #}
    # Se reciben messages que contienen:
    #{ type: "message",from: "sec30.grupo6.nodo6",to: "sec30.grupo11.nodo11",hops:5}
    #{ type: "message",from: "sec30.grupo6.nodo6",to: "sec30.grupo10.nodo10",hops:6}
    # Entonces se agrega a la topología:
    #{
    #  "N9":{  "N4": { "weight": 8, "time": 5} },
    #  "N6":{  "N11": { "weight": 5, "time": 5}, "N10": { "weight": 6, "time": 5} }
    #}

# 4. Actualizar topología
# el timer de cada Nodo en nuestra tabla se decrementa cada segundo, sin embargo cuando se recibe un mensaje confirmando la conexión, o un hello de parte de un vecino... el timer se reinicia.
# Si el timer llega a 0, se elimina el nodo de la tabla