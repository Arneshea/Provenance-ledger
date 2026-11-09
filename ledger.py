"""Run `python ledger.py --help` from the project root."""
import argparse
import json
import sys
from pathlib import Path
from contracts.registry_client import RegistryClient, configure_pipeline, deploy_registry
from ipfs.ipfs_client import IPFSClient
from merkle.merkle_tree import build_tree, entries_from_manifest, leaves_from_manifest
from merkle.merkle_proof import generate_proof, verify_proof
from sign.signatures import generate_keys
from verify.config import RPC_URL, IPFS_API_URL, DEPLOYMENT_FILE, KEYS_FOLDER
from verify.pipeline import register_build, verify_build, tamper_demo


def parser():
    p = argparse.ArgumentParser(description="CI/CD Artifact Provenance Ledger")
    p.add_argument("--rpc", default=RPC_URL)
    p.add_argument("--ipfs", default=IPFS_API_URL)
    p.add_argument("--deployment", default=str(DEPLOYMENT_FILE))
    p.add_argument("--key", default=str(KEYS_FOLDER / "pipeline.key"))
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("keygen", help="Create a pipeline identity without overwriting existing keys")
    commands.add_parser("deploy", help="Deploy compiled contract using a local unlocked owner")
    commands.add_parser("doctor", help="Check chain, contract and IPFS connectivity")
    for name in ("authorize", "revoke"):
        sub = commands.add_parser(name, help="Local owner pipeline administration")
        sub.add_argument("address")
        if name == "authorize":
            sub.add_argument("--fund", action="store_true", help="Send 1 local test ETH")
    sub = commands.add_parser("register", help="Package source, sign and register provenance")
    sub.add_argument("source")
    sub.add_argument("--output", default="artifacts/app.zip")
    sub.add_argument("--commit", required=True, help="Full Git commit, or documented demo commit")
    sub.add_argument("--dependencies", help="JSON file of dependency name/version/hash entries")
    for name in ("verify", "tamper-demo"):
        sub = commands.add_parser(name)
        sub.add_argument("artifact")
        if name == "verify":
            sub.add_argument("--expected-hash", help="Compare against a previously approved build")
    sub = commands.add_parser("proof", help="Prove one manifest entry against its registered root")
    sub.add_argument("artifact_hash")
    sub.add_argument("--index", type=int, required=True, help="Zero-based manifest leaf index")
    return p


def run(args):
    if args.command == "keygen":
        if Path(args.key).name != "pipeline.key":
            raise ValueError("keygen expects --key to end with pipeline.key")
        return generate_keys(Path(args.key).parent), 0
    if args.command == "deploy":
        deployment = deploy_registry(args.rpc, args.deployment)
        return {key: value for key, value in deployment.items() if key != "abi"}, 0
    private_key = Path(args.key).read_text().strip() if args.command == "register" else None
    registry = RegistryClient(args.rpc, args.deployment, private_key)
    storage = IPFSClient(args.ipfs)
    if args.command == "doctor":
        version = storage._post("version").json()["Version"]
        return {"chain_id": registry.w3.eth.chain_id, "contract": registry.contract.address,
                "ipfs_version": version, "status": "ready"}, 0
    if args.command in ("authorize", "revoke"):
        receipt = configure_pipeline(registry, args.address, args.command == "revoke",
                                     getattr(args, "fund", False))
        return {"transaction_hash": receipt.transactionHash.hex(), "address": args.address}, 0
    if args.command == "register":
        deps = json.loads(Path(args.dependencies).read_text()) if args.dependencies else []
        return register_build(args.source, args.output, args.commit, deps, private_key, registry, storage), 0
    if args.command == "verify":
        result = verify_build(args.artifact, registry, storage, args.expected_hash)
        return result.to_dict(), 0 if result.passed else 1
    if args.command == "tamper-demo":
        result = tamper_demo(args.artifact, registry, storage)
        return result, 0 if result["clean"]["passed"] and not result["tampered"]["passed"] else 1
    if args.command == "proof":
        record = registry.get_build(args.artifact_hash)
        if not record:
            raise ValueError("No on-chain record")
        bundle = storage.fetch_bundle(record["cid"])
        leaves = leaves_from_manifest(bundle["manifest"])
        proof = generate_proof(build_tree(leaves), args.index)
        valid = verify_proof(leaves[args.index], proof, record["merkle_root"])
        return {"entry": entries_from_manifest(bundle["manifest"])[args.index],
                "leaf": leaves[args.index], "proof": proof, "on_chain_root": record["merkle_root"],
                "valid": valid}, 0 if valid else 1


def main():
    args = parser().parse_args()
    try:
        output, code = run(args)
    except Exception as error:
        output, code = {"passed": False, "reason": str(error)}, 1
    print(json.dumps(output, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
