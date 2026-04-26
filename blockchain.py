import hashlib, json, time, sqlite3, threading, os, sys

def get_app_path(filename):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)

class Blockchain:
    def __init__(self, db_name="blockchain.db"):
        self.db_path = get_app_path(db_name) # Ścieżka w folderu aplikacji
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.lock = threading.Lock()
        self.pending_transactions = []
        self._init_db()

    def _init_db(self):
        with self.lock:
            self.cursor.execute('CREATE TABLE IF NOT EXISTS blocks (idx INTEGER PRIMARY KEY, prev_hash TEXT, timestamp REAL, data TEXT, nonce INTEGER, hash TEXT)')
            self.cursor.execute('CREATE TABLE IF NOT EXISTS utxo (tx_id TEXT, out_idx INTEGER, address TEXT, amount REAL, spent INTEGER)')
            self.conn.commit()
        if not self.get_last_block(): self.create_genesis_block()

    def get_current_difficulty(self):
        with self.lock:
            self.cursor.execute("SELECT timestamp FROM blocks ORDER BY idx DESC LIMIT 5")
            times = [r[0] for r in self.cursor.fetchall()]
        if len(times) < 5: return 4
        avg = (times[0] - times[-1]) / 5 if len(times) > 1 else 100
        return 5 if avg < 15 else (3 if avg > 40 else 4)

    def get_balance(self, address):
        with self.lock:
            self.cursor.execute("SELECT SUM(amount) FROM utxo WHERE address=? AND spent=0", (address,))
            res = self.cursor.fetchone()
        return float(res[0]) if res and res[0] is not None else 0.0

    def get_last_block(self):
        with self.lock:
            self.cursor.execute("SELECT * FROM blocks ORDER BY idx DESC LIMIT 1")
            return self.cursor.fetchone()

    def calculate_hash(self, idx, prev_hash, timestamp, data, nonce):
        return hashlib.sha256(f"{idx}{prev_hash}{timestamp}{data}{nonce}".encode()).hexdigest()

    def create_genesis_block(self):
        self.pending_transactions = [{"id": "gen", "inputs": [], "outputs": [{"address": "SYSTEM", "amount": 1000000.0}]}]
        genesis = self.create_block(0, "0"*64)
        self.save_block(genesis)

    def create_block(self, nonce, prev_hash):
        last = self.get_last_block()
        b = {'idx': (last[0]+1) if last else 0, 'timestamp': time.time(), 'transactions': list(self.pending_transactions), 'nonce': nonce, 'prev_hash': prev_hash}
        self.pending_transactions = []
        return b

    def save_block(self, block):
        with self.lock:
            self.cursor.execute("SELECT idx FROM blocks WHERE idx=?", (block['idx'],))
            if self.cursor.fetchone(): return False
            tx_json = json.dumps(block['transactions'])
            h = self.calculate_hash(block['idx'], block['prev_hash'], block['timestamp'], tx_json, block['nonce'])
            self.cursor.execute("INSERT INTO blocks VALUES (?,?,?,?,?,?)", (block['idx'], block['prev_hash'], block['timestamp'], tx_json, block['nonce'], h))
            for tx in block['transactions']:
                tid = hashlib.sha256(json.dumps(tx).encode()).hexdigest()
                for inp in tx.get('inputs', []): 
                    self.cursor.execute("UPDATE utxo SET spent=1 WHERE tx_id=? AND out_idx=?", (inp['tx_id'], inp['out_idx']))
                for i, out in enumerate(tx.get('outputs', [])): 
                    self.cursor.execute("INSERT INTO utxo VALUES (?,?,?,?,0)", (tid, i, out['address'], out['amount']))
            self.conn.commit()
            return True

    def add_transaction(self, sender, recipient, amount):
        if self.get_balance(sender) < amount: return False
        with self.lock:
            self.cursor.execute("SELECT tx_id, out_idx, amount FROM utxo WHERE address=? AND spent=0", (sender,))
            utxos = self.cursor.fetchall()
        inputs, coll = [], 0
        for u in utxos:
            inputs.append({"tx_id":u[0],"out_idx":u[1]})
            coll += u[2]
            if coll >= amount: break
        fee = amount * 0.01
        outs = [{"address":recipient,"amount":amount-fee}, {"address":"TREASURY","amount":fee}]
        if coll > amount: outs.append({"address":sender,"amount":coll-amount})
        self.pending_transactions.append({"sender":sender,"inputs":inputs,"outputs":outs,"timestamp":time.time()})
        return True

    def is_chain_valid(self, chain):
        for i in range(1, len(chain)):
            prev, curr = chain[i-1], chain[i]
            tx_json = json.dumps(curr['transactions'])
            check_hash = self.calculate_hash(curr['idx'], curr['prev_hash'], curr['timestamp'], tx_json, curr['nonce'])
            if curr['hash'] != check_hash or curr['prev_hash'] != prev['hash']: return False
        return True

    def replace_chain(self, chain):
        if not self.is_chain_valid(chain): return False
        curr_last = self.get_last_block()
        if len(chain) <= (curr_last[0] + 1 if curr_last else 0): return False
        with self.lock:
            self.cursor.execute("DELETE FROM blocks")
            self.cursor.execute("DELETE FROM utxo")
            self.conn.commit()
        for b in chain: self._force_save_block(b)
        return True

    def _force_save_block(self, block):
        with self.lock:
            tx_json = json.dumps(block['transactions'])
            self.cursor.execute("INSERT INTO blocks VALUES (?,?,?,?,?,?)", (block['idx'], block['prev_hash'], block['timestamp'], tx_json, block['nonce'], block['hash']))
            for tx in block['transactions']:
                tid = hashlib.sha256(json.dumps(tx).encode()).hexdigest()
                for inp in tx.get('inputs', []): self.cursor.execute("UPDATE utxo SET spent=1 WHERE tx_id=? AND out_idx=?", (inp['tx_id'], inp['out_idx']))
                for i, out in enumerate(tx.get('outputs', [])): self.cursor.execute("INSERT INTO utxo VALUES (?,?,?,?,0)", (tid, i, out['address'], out['amount']))
            self.conn.commit()
