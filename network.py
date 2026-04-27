import socket, threading, json, subprocess, re, time

class NetworkNode:
    def __init__(self, port=5001):
        self.port, self.peers, self.public_url = port, set(), None
        self.start_tunnel()

    def start_tunnel(self):
        def run():
            # Tunelowanie przez localhost.run
            p = subprocess.Popen(["ssh","-o","StrictHostKeyChecking=accept-new","-R",f"80:localhost:{self.port}","nokey@localhost.run"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                m = re.search(r'([\w-]+\.lhr\.life)', line)
                if m: 
                    self.public_url = m.group(1).strip()
                    print(f"[*] Public URL: {self.public_url}")
                    break
        threading.Thread(target=run, daemon=True).start()

    def connect_to_peer(self, addr):
        clean_addr = addr.replace("http://", "").split(":")[0].strip()
        if not clean_addr or clean_addr == self.public_url: return
        
        self.peers.add(clean_addr)
        # 1. Przywitaj się
        self.send_to_one(clean_addr, {
            "type": "GOSSIP_HELLO",
            "my_url": self.public_url,
            "known_peers": list(self.peers)
        })
        # 2. Poproś o łańcuch
        self.send_to_one(clean_addr, {"type": "GET_CHAIN", "my_url": self.public_url})

    def start_server(self, cb):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', self.port))
        s.listen(5)
        def run():
            while True:
                try:
                    c, _ = s.accept()
                    d = b""
                    while True:
                        part = c.recv(4096)
                        if not part: break
                        d += part
                    if d:
                        msg = json.loads(d.decode())
                        if msg['type'] == "GOSSIP_HELLO":
                            if msg['my_url'] and msg['my_url'] != self.public_url and msg['my_url'] not in self.peers:
                                self.peers.add(msg['my_url'])
                            for p in msg.get('known_peers', []):
                                if p and p != self.public_url and p not in self.peers:
                                    self.peers.add(p)
                                    # Propagacja sieci
                                    threading.Thread(target=self.connect_to_peer, args=(p,)).start()
                        cb(msg, self)
                    c.close()
                except: pass
        threading.Thread(target=run, daemon=True).start()

    def send_to_one(self, host, data):
        if not host: return
        def _send():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(10)
                s.connect((host.strip(), 80)) 
                s.sendall(json.dumps(data).encode())
                s.close()
            except Exception as e:
                print(f"Connection error to {host}: {e}")
        threading.Thread(target=_send).start()

    def broadcast(self, data):
        for p in list(self.peers): 
            self.send_to_one(p, data)
