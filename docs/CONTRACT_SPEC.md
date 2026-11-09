# BuildRegistry implementation decisions

Solidity is pinned to **0.8.24**, compiled for Shanghai with optimization (200 runs). `npm run compile` generates the ABI and bytecode using the pinned local npm compiler.

The immutable owner is the deployer. It is not automatically authorized as a pipeline. `addPipeline` rejects zero/already-authorized addresses; `removePipeline` rejects addresses not currently authorized. Both are owner-only and emit indexed events.

`registerBuild(bytes32 artifactHash, bytes32 merkleRoot, string cid)` requires current pipeline authorization, nonzero hash/root, a CID string of 1–128 bytes, and no existing record. It records root, CID, sender, block timestamp, and existence, and emits `BuildRegistered`. The contract does not parse CIDs or validate signatures: the independent verifier performs those checks.

`getBuild(bytes32)` returns the struct; unknown records have `exists=false` and zero/empty fields. The Python wrapper returns `None`. No edit/delete method exists.

Decisions: single owner, readable CID string, off-chain signature checking, no per-build revocation. Pipeline revocation changes the authorization mapping without removing historical provenance. The verifier requires current authorization even for historical builds. Owner transfer and multisig administration are future extensions.
