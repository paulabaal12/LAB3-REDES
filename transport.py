import asyncio
import redis.asyncio as redis
import json


class AsyncRedisTransport:
    def __init__(self, node_id, on_message, host="homelab.fortiguate.com", port=16379, password="4YNydkHFPcayvlx7$zpKm", neighbor_ids=None):
        """
        node_id: id completo del nodo (ej: 'sec30.grupo1.nodo1')
        on_message: callback async para manejar mensajes entrantes
        neighbor_ids: lista de IDs completos de los vecinos
        """
        self.node_id = node_id
        self.on_message = on_message  # debe ser async def o compatible
        self.host = host
        self.port = port
        self.password = password
        self.redis = redis.Redis(host=self.host, port=self.port, password=self.password)
        self.neighbor_ids = neighbor_ids or []
        self._running = False

    async def _reader(self, pubsub):
        """Coroutine que escucha los canales suscritos"""
        while self._running:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data = message["data"]
                    try:
                        msg = json.loads(data.decode() if isinstance(data, bytes) else data)
                        if asyncio.iscoroutinefunction(self.on_message):
                            await self.on_message(msg)
                        else:
                            self.on_message(msg)
                    except Exception as e:
                        print(f"[Redis] Error parsing message: {e}")
            except Exception as e:
                print(f"[Redis] Reader error: {e}")
                await asyncio.sleep(1)

    async def start_server(self):
        """Empieza a escuchar en mi canal"""
        if self._running:
            print("[Redis] Listener already running")
            return

        self._running = True
        try:
            self.pubsub = self.redis.pubsub()
            # solo me suscribo a mi canal
            await self.pubsub.subscribe(self.node_id)
            print(f"[Redis] Listener started for {self.node_id}")
            asyncio.create_task(self._reader(self.pubsub))
        except Exception as e:
            print(f"[Redis] Error in start_server: {e}")

    async def send(self, target_node, message):
        """Publica un mensaje en el canal del destino"""
        try:
            msg_str = json.dumps(message)
            channel = target_node
            print(f"[DEBUG][{self.node_id}] Enviando a {target_node} por canal: {channel}")
            await self.redis.publish(channel, msg_str)
            print(f"[Redis] {message.get('type')} {message.get('from')} -> {target_node} (canal {channel})")
        except Exception as e:
            print(f"[Redis] Error sending to {target_node}: {e}")

    async def disconnect(self):
        self._running = False
        if hasattr(self, "pubsub"):
            await self.pubsub.unsubscribe(self.node_id)
            await self.pubsub.close()
        await self.redis.close()
        print("[Redis] Transport disconnected")
