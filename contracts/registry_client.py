"""Small Web3 wrapper: reads, signed pipeline writes, and local owner setup."""
import json
from pathlib import Path
from eth_account import Account
from web3 import Web3
from build.hash_utils import validate_hash
from verify.config import COMPILED_FILE, DEPLOYMENT_FILE, RPC_URL


def checked_receipt(w3, tx_hash):
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status != 1:
        raise RuntimeError("Blockchain transaction reverted")
    return receipt


def web3_connection(rpc_url):
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
    if not w3.is_connected():
        raise RuntimeError(f"Chain is offline at {rpc_url}; start npm run chain")
    return w3


class RegistryClient:
    def __init__(self, rpc_url=RPC_URL, deployment_file=DEPLOYMENT_FILE, private_key=None):
        self.w3 = web3_connection(rpc_url)
        deployment = json.loads(Path(deployment_file).read_text(encoding="utf-8"))
        if deployment["chain_id"] != self.w3.eth.chain_id:
            raise ValueError("Deployment belongs to a different chain")
        address = Web3.to_checksum_address(deployment["address"])
        code = self.w3.eth.get_code(address)
        if not code or Web3.keccak(code).hex() != deployment["code_hash"]:
            raise ValueError("Contract missing or changed; redeploy and trust the new deployment file")
        self.contract = self.w3.eth.contract(address=address, abi=deployment["abi"])
        self.private_key = private_key

    def is_authorized(self, address):
        return self.contract.functions.isAuthorized(Web3.to_checksum_address(address)).call()

    def get_build(self, artifact_hash):
        root, cid, pipeline, timestamp, exists = self.contract.functions.getBuild(
            bytes.fromhex(validate_hash(artifact_hash))).call()
        if not exists:
            return None
        return {"merkle_root": bytes(root).hex(), "cid": cid, "pipeline": pipeline, "timestamp": timestamp}

    def register_build(self, artifact_hash, merkle_root, cid):
        if not self.private_key:
            raise ValueError("Registration needs the pipeline private key")
        account = Account.from_key(self.private_key)
        function = self.contract.functions.registerBuild(bytes.fromhex(validate_hash(artifact_hash)),
                    bytes.fromhex(validate_hash(merkle_root)), cid)
        transaction = function.build_transaction({"from": account.address,
                      "nonce": self.w3.eth.get_transaction_count(account.address, "pending"),
                      "chainId": self.w3.eth.chain_id})
        signed = account.sign_transaction(transaction)
        return checked_receipt(self.w3, self.w3.eth.send_raw_transaction(signed.raw_transaction))


def deploy_registry(rpc_url=RPC_URL, deployment_file=DEPLOYMENT_FILE):
    w3 = web3_connection(rpc_url)
    compiled = json.loads(COMPILED_FILE.read_text(encoding="utf-8"))
    if Path(deployment_file).exists():
        raise ValueError("Deployment file already exists; keep it or choose a new --deployment path")
    # An unlocked owner is convenient for a LOCAL chain. Pipeline writes are always signed.
    owner = w3.eth.accounts[0]
    factory = w3.eth.contract(abi=compiled["abi"], bytecode=compiled["bytecode"])
    receipt = checked_receipt(w3, factory.constructor().transact({"from": owner}))
    deployment = {"address": receipt.contractAddress, "chain_id": w3.eth.chain_id,
                  "owner": owner, "abi": compiled["abi"],
                  "code_hash": Web3.keccak(w3.eth.get_code(receipt.contractAddress)).hex()}
    target = Path(deployment_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(deployment, indent=2), encoding="utf-8")
    return deployment


def configure_pipeline(registry, address, remove=False, fund=False):
    w3, contract = registry.w3, registry.contract
    address = Web3.to_checksum_address(address)
    owner = contract.functions.owner().call()
    function = contract.functions.removePipeline if remove else contract.functions.addPipeline
    receipt = checked_receipt(w3, function(address).transact({"from": owner}))
    if fund and not remove:
        checked_receipt(w3, w3.eth.send_transaction({"from": owner, "to": address,
                        "value": w3.to_wei(1, "ether")}))
    return receipt


def connect(rpc_url, contract_address):
    w3 = web3_connection(rpc_url)
    abi = json.loads(COMPILED_FILE.read_text(encoding="utf-8"))["abi"]
    return w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
