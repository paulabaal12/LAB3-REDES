def make_hello_message(from_node, to_node, weight):
    return {
        "type": "hello",
        "from": from_node,
        "to": to_node,
        "hops": weight
    }


def make_info_message(from_node, to_node, weight):
    return {
        "type": "message",
        "from": from_node,
        "to": to_node,
        "hops": weight
    }