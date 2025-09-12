import socket
import threading
import json
import asyncio
import time
import slixmpp
import json as _json

class TCPTransport:
    def __init__(self, host, port, on_message):
        self.host = host
        self.port = port
        self.on_message = on_message
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start_server(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen()
        print(f"[TCP] Node listening on {self.host}:{self.port}")

        def accept_loop():
            while True:
                conn, addr = self.sock.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

        threading.Thread(target=accept_loop, daemon=True).start()

    def _handle_client(self, conn):
        with conn:
            data = conn.recv(4096)
            if not data:
                return
            try:
                msg = json.loads(data.decode())
                self.on_message(msg)
            except Exception as e:
                print("[TCP] Error parsing message:", e)

    def send(self, target_host, target_port, message):
        try:
            with socket.create_connection((target_host, target_port), timeout=2) as s:
                s.sendall(json.dumps(message).encode())
                print(f"[TCP] {message.get('proto')} {message.get('type')} {message.get('from')} -> {message.get('to')}")
        except Exception as e:
            print(f"[TCP] Error sending to {target_host}:{target_port} -> {e}")
            raise

class XMPPBot(slixmpp.ClientXMPP):
    def __init__(self, jid, password, on_message_callback):
        super().__init__(jid, password)
        self.on_message_callback = on_message_callback
        self.add_event_handler("session_start", self._on_start)
        self.add_event_handler("message", self._on_message)

    async def _on_start(self, event):
        try:
            self.send_presence()
            await self.get_roster()
            print("[XMPP] Session started")
        except Exception as e:
            print(f"[XMPP] Error in session_start: {e}")

    def _on_message(self, msg):
        if msg['type'] in ('chat', 'normal'):
            try:
                data = _json.loads(str(msg['body']))
                self.on_message_callback(data)
            except Exception as e:
                print(f"[XMPP] Error al procesar mensaje: {e}")


# =========================
# XMPP TRANSPORT
# =========================
class XMPPTransport:

    def __init__(self, jid, password, on_message_callback,server='homelab.fortiguate.com', port=16379):
        self.jid = jid
        self.password = password
        self.on_message_callback = on_message_callback
        self.server = server
        self.port = port

        # Detecta si existe .process() a nivel de clase (legacy)
        self._legacy_mode = hasattr(slixmpp.ClientXMPP, 'process')

        # Estado moderno
        self._loop = None
        self._loop_thread = None
        self._running = False
        self._xmpp_ready = threading.Event()
        self.xmpp = None  

    def connect(self):
        """En moderno, la conexión real se agenda en start_listener(). En legacy, también."""
        pass

    def start_listener(self):
        if self._legacy_mode:
            self._start_legacy()
        else:
            self._start_modern()

    def send(self, to_jid, message):
        try:
            msg_str = _json.dumps(message)
        except Exception as e:
            print(f"[XMPP] Error serializando mensaje: {e}")
            return

        if self._legacy_mode:
            try:
                self.xmpp.send_message(mto=to_jid, mbody=msg_str, mtype='chat')
                print(f"[XMPP] Enviado (legacy) -> {to_jid}")
            except Exception as e:
                print(f"[XMPP] Error enviando mensaje (legacy): {e}")
            return

        if not self._xmpp_ready.wait(timeout=5):
            print("[XMPP] Bot no está listo aún; ¿llamaste start_listener()?")
            return

        if self._loop and self._running and self.xmpp:
            def _do_send():
                try:
                    self.xmpp.send_message(mto=to_jid, mbody=msg_str, mtype='chat')
                    print(f"[XMPP] Enviado -> {to_jid}")
                except Exception as e:
                    print(f"[XMPP] Error enviando (asyncio): {e}")
            self._loop.call_soon_threadsafe(_do_send)
        else:
            print("[XMPP] No hay loop activo")

    def disconnect(self):
        if self._legacy_mode:
            try:
                if self.xmpp:
                    self.xmpp.disconnect()
                    print("[XMPP] Legacy disconnect() solicitado")
            except Exception as e:
                print(f"[XMPP] Error en legacy disconnect(): {e}")
            return

        if self._loop and self._running and self.xmpp:
            def _do_disc():
                try:
                    self.xmpp.disconnect()
                except Exception as e:
                    print(f"[XMPP] Error en disconnect(): {e}")
            self._loop.call_soon_threadsafe(_do_disc)
        else:
            print("[XMPP] No hay loop activo para desconectar")

    def _start_legacy(self):
        self.xmpp = XMPPBot(self.jid, self.password, self.on_message_callback)

        def _legacy_runner():
            try:
                ok = self.xmpp.connect((self.server, self.port))
                if not ok:
                    print(f"[XMPP] Legacy connect() falló contra {self.server}:{self.port}")
                    return
                print("[XMPP] Legacy conectado; iniciando process(forever=True)")
                self.xmpp.process(forever=True)
            except Exception as e:
                print(f"[XMPP] Error en legacy runner: {e}")
            finally:
                self.xmpp.disconnect()

        t = threading.Thread(target=_legacy_runner, daemon=True)
        t.start()

    def _start_modern(self):
        if self._running:
            print("[XMPP] Listener ya estaba iniciado")
            return

        self._running = True
        self._xmpp_ready.clear()

        def _loop_runner():
            try:
                import sys
                if sys.platform.startswith("win"):
                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass

            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            try:
                self.xmpp = XMPPBot(self.jid, self.password, self.on_message_callback)
                self.xmpp.connect(host=self.server, port=self.port)
                self._xmpp_ready.set()
                print(f"[XMPP] Async loop corriendo (host={self.server}, port={self.port})")
                # Esperar a que se desconecte
                self._loop.run_until_complete(self.xmpp.disconnected)
                print("[XMPP] Señal de desconexión recibida")
            except Exception as e:
                print(f"[XMPP] Error en loop_runner: {e}")
            finally:
                try:
                    pending = asyncio.all_tasks(loop=self._loop)
                    for task in pending:
                        task.cancel()
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                finally:
                    self._loop.stop()
                    self._loop.close()
                    self._loop = None
                    self._running = False
                    self.xmpp = None
                    self._xmpp_ready.clear()
                    print("[XMPP] Async loop cerrado")

        self._loop_thread = threading.Thread(target=_loop_runner, daemon=True)
        self._loop_thread.start()
        time.sleep(0.1) 


        time.sleep(0.1)

    def disconnect(self):
        if self._has_process:
            try:
                self.xmpp.disconnect()
                print("[XMPP] Legacy disconnect() solicitado")
            except Exception as e:
                print(f"[XMPP] Error en legacy disconnect(): {e}")
            return

        if self._loop and self._running:
            def _do_disc():
                try:
                    self.xmpp.disconnect()
                except Exception as e:
                    print(f"[XMPP] Error en disconnect(): {e}")

            self._loop.call_soon_threadsafe(_do_disc)
        else:
            print("[XMPP] No hay loop activo para desconectar")



import asyncio
import redis.asyncio as redis
import json
import threading

class RedisTransport:
    def __init__(self, node_id, on_message, host="homelab.fortiguate.com", port=16379, password="4YNydkHFPcayvlx7$zpKm", neighbor_groups=None, my_group=9):
        self.node_id = node_id
        self.on_message = on_message
        self.host = host
        self.port = port
        self.password = password
        self.redis = redis.Redis(host=self.host, port=self.port, password=self.password)
        self._loop = None
        self._thread = None
        self._running = False
        self.neighbor_groups = neighbor_groups or {}
        self.my_group = my_group

    async def _reader(self, pubsub):
        """Coroutine que escucha el canal de este nodo"""
        while self._running:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is not None:
                    data = message["data"]
                    try:
                        msg = json.loads(data.decode() if isinstance(data, bytes) else data)
                        self.on_message(msg)
                    except Exception as e:
                        print(f"[Redis] Error parsing message: {e}")
            except Exception as e:
                print(f"[Redis] Reader error: {e}")
                await asyncio.sleep(1)

    async def _start_async(self):
        """Loop asíncrono que mantiene la suscripción activa"""
        try:
            async with self.redis.pubsub() as pubsub:
                # Suscribirse a los canales de todos los vecinos
                for nbr, group in self.neighbor_groups.items():
                    canal = f"sec30.grupo{group}.{nbr}"
                    await pubsub.subscribe(canal)
                    print(f"[Redis] Subscribed to {canal}")
                # También suscribirse a tu propio canal
                my_canal = f"sec30.grupo{self.my_group}.{self.node_id}"
                await pubsub.subscribe(my_canal)
                print(f"[Redis] Subscribed to own channel {my_canal}")
                await self._reader(pubsub)
        except Exception as e:
            print(f"[Redis] Error in _start_async: {e}")

    def start_server(self):
        """Inicia el loop asíncrono en un hilo aparte"""
        if self._running:
            print("[Redis] Listener already running")
            return

        self._running = True

        def _run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._start_async())

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        print(f"[Redis] Listener started for node {self.node_id}")

    def send(self, target_node, message, group=None):
        """Publica un mensaje en el canal del destino, usando el grupo correcto"""
        try:
            msg_str = json.dumps(message)
            import asyncio
            import threading
            group = group if group is not None else self.neighbor_groups.get(target_node, 9)
            channel = f"{target_node}"
            #print(f"[DEBUG][{self.node_id}] Enviando a {target_node} (grupo {group}) por canal: {channel}")
            # Si estamos en el hilo del loop de Redis, usar create_task
            if self._loop and self._loop.is_running():
                if threading.current_thread() == self._thread:
                    # Mismo hilo: podemos usar create_task
                    asyncio.create_task(self.redis.publish(channel, msg_str))
                else:
                    # Otro hilo: usar run_coroutine_threadsafe
                    fut = asyncio.run_coroutine_threadsafe(
                        self.redis.publish(channel, msg_str),
                        self._loop
                    )
                    fut.result()  # Espera a que termine y propaga excepciones
            else:
                asyncio.run(self.redis.publish(channel, msg_str))
            print(f"[Redis] {message.get('proto')} {message.get('type')} {message.get('from')} -> {target_node} (canal {channel})")
        except Exception as e:
            print(f"[Redis] Error sending to {target_node}: {e}")

    def disconnect(self):
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        print("[Redis] Transport disconnected")
