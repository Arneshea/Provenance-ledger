"""EIP-191 signatures bind the SHA-256 root to an Ethereum pipeline address."""
import os
from pathlib import Path
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys.exceptions import BadSignature
from build.hash_utils import validate_hash


def generate_keys(output_folder) -> dict:
    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)
    private_path = folder / "pipeline.key"
    account = Account.create()
    # Exclusive creation prevents accidentally destroying an existing identity.
    descriptor = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(account.key.hex())
    (folder / "pipeline.address").write_text(account.address, encoding="utf-8")
    return {"private_key_file": str(private_path), "address": account.address}


def sign_root(root_hash, private_key) -> str:
    message = encode_defunct(primitive=bytes.fromhex(validate_hash(root_hash)))
    return Account.sign_message(message, private_key).signature.hex()


def verify_signature(root_hash, signature, public_key) -> bool:
    # public_key is the trusted Ethereum address, never a key supplied by IPFS.
    try:
        message = encode_defunct(primitive=bytes.fromhex(validate_hash(root_hash)))
        recovered = Account.recover_message(message, signature=signature)
        return recovered.lower() == public_key.lower()
    except (ValueError, TypeError, AttributeError, BadSignature):
        return False
