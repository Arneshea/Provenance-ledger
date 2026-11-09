"""Configuration is explicit, with local-only defaults."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RPC_URL = os.getenv("LEDGER_RPC_URL", "http://127.0.0.1:8545")
IPFS_API_URL = os.getenv("LEDGER_IPFS_API_URL", "http://127.0.0.1:5001")
DEPLOYMENT_FILE = ROOT / "contracts" / "deployment.json"
COMPILED_FILE = ROOT / "contracts" / "compiled.json"
KEYS_FOLDER = ROOT / "keys"
ARTIFACT_FOLDER = ROOT / "artifacts"
