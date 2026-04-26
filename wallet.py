import ecdsa, hashlib, os

class Wallet:
    def __init__(self, filename="wallet.dat"):
        self.filename = filename
        self.private_key = None
        self.public_key = None
        if os.path.exists(filename): self.load_wallet()
        else: self.create_wallet()

    def create_wallet(self):
        self.private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        self.save_wallet()

    def import_wallet(self, private_hex):
        try:
            self.private_key = ecdsa.SigningKey.from_string(bytes.fromhex(private_hex), curve=ecdsa.SECP256k1)
            self.save_wallet()
            return True
        except: return False

    def import_from_file(self, path):
        try:
            with open(path, "rb") as f:
                key_data = f.read()
                # Klucz SECP256k1 musi mieć dokładnie 32 bajty
                if len(key_data) != 32: return False
                self.private_key = ecdsa.SigningKey.from_string(key_data, curve=ecdsa.SECP256k1)
                self.save_wallet()
                return True
        except: return False

    def save_wallet(self):
        self.public_key = self.private_key.get_verifying_key()
        with open(self.filename, "wb") as f:
            f.write(self.private_key.to_string())

    def load_wallet(self):
        with open(self.filename, "rb") as f:
            self.private_key = ecdsa.SigningKey.from_string(f.read(), curve=ecdsa.SECP256k1)
            self.public_key = self.private_key.get_verifying_key()

    def get_address(self):
        return hashlib.sha256(self.public_key.to_string()).hexdigest()[:40]
    
    def get_private_hex(self):
        return self.private_key.to_string().hex()