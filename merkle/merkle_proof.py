from build.hash_utils import validate_hash
from merkle.merkle_tree import parent_hash


def generate_proof(tree, leaf_index: int) -> list:
    if not tree or not 0 <= leaf_index < len(tree[0]):
        raise ValueError("Leaf index out of range")
    proof = []
    for level in tree[:-1]:
        sibling = leaf_index ^ 1
        proof.append((level[sibling] if sibling < len(level) else level[leaf_index],
                      "left" if leaf_index % 2 else "right"))
        leaf_index //= 2
    return proof


def verify_proof(leaf_hash, proof, expected_root) -> bool:
    try:
        current = validate_hash(leaf_hash)
        for sibling, side in proof:
            if side not in ("left", "right"):
                return False
            current = parent_hash(sibling, current) if side == "left" else parent_hash(current, sibling)
        return current == validate_hash(expected_root)
    except (TypeError, ValueError):
        return False
