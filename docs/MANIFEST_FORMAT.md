# Manifest and Merkle rules, version 1.0

Canonical JSON uses UTF-8, `ensure_ascii=False`, compact comma/colon separators, no extra newline, and no non-finite numbers. These are protocol rules, implemented centrally in `build/build_artifact.py`.

Top-level field order: `version`, `artifact_name`, `artifact_hash`, `commit_hash`, `dependencies`, `timestamp`, `builder_id`. Unknown or missing fields are rejected. All non-dependency fields are nonempty strings. Version is `1.0`; hashes are lowercase hex; artifact SHA-256 is 64 digits; Git commits are 40 or 64 digits. Timestamp is UTC `YYYY-MM-DDTHH:MM:SSZ`.

Dependencies are objects in fixed key order `name`, `version`, `hash`, sorted alphabetically by unique name. Their hashes are SHA-256 fingerprints supplied by the builder. An empty dependency list is valid.

Leaf entries in order:

1. `["version", value]`
2. `["artifact_name", value]`
3. `["artifact_hash", value]`
4. `["commit_hash", value]`
5. Each `["dependency", {"name": ..., "version": ..., "hash": ...}]`, sorted by name.
6. `["timestamp", value]`
7. `["builder_id", value]`

`leaf = SHA256(0x00 || canonical_JSON(entry))`. Field labels prevent ambiguity between equal values in different fields. Dependencies are represented by their individual entries, not an additional list leaf. `parent = SHA256(0x01 || raw_left_32_bytes || raw_right_32_bytes)`. Prefixes separate leaves from internal nodes. Duplicate the final node at every odd-width level. A single-leaf tree's root is the leaf. Empty trees are rejected.

Proofs are ordered pairs `[sibling_hex, "left"|"right"]`, from leaf level upward. “Left” means place the sibling before the running hash. The proof verifier needs only the leaf, proof, and trusted root. Proofs demonstrate membership, not field uniqueness or a global tree size.

Signed bundle keys: `manifest`, `merkle_root`, `signature`, `signer`. The root's raw bytes are EIP-191 signed using secp256k1. `signer` and manifest `builder_id` must match the on-chain pipeline. No private key or separate trusted public key is uploaded.

IPFS import parameters are fixed: CIDv1, raw leaves, 262144-byte chunker, no wrapping directory. Fetch reimports returned bytes in only-hash mode with the same parameters and compares the CID. Bundles are capped at 2 MiB.
