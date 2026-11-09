# Faculty demonstration and viva guide

## A short explanation in your own words

“My project detects whether a software artifact changed between build and deployment. The trusted pipeline packages the source and calculates its SHA-256 fingerprint. It creates a manifest describing the artifact, commit, dependencies, time, and builder. A Merkle tree commits all those fields into one root. The pipeline signs that root, stores the signed manifest in IPFS, and records the root and CID in an access-controlled smart contract. Before deployment, a verifier checks the artifact hash, manifest root, signature, and pipeline authorization. Any failure blocks deployment.”

Practice explaining the flow and then phrase it naturally yourself. Read the code for each step; do not memorize claims you cannot demonstrate.

## Understand the problem first

CI means continuous integration: building and testing a code change. CD means continuous delivery or deployment: preparing or releasing that build. The resulting ZIP, package, or binary is an **artifact**. This project focuses on the handoff between those stages, when the artifact might be replaced or modified in storage or transit.

Example: a pipeline builds `app.zip`, but someone changes `app.py` inside the ZIP before deployment. Its filename may be unchanged. The deploy verifier checks the bytes against the registered provenance and blocks that changed file.

The application does not perform a real deployment or run uploaded code. “Deployment allowed” means the gate passed and a CI script could proceed. “Deployment blocked” means it must stop.

## Build and registration workflow

1. **Identify the builder.** Generate an Ethereum pipeline key. The owner authorizes its address and funds it with local test ETH for transaction gas. The owner and pipeline have separate roles; deploying the contract does not automatically authorize the owner as a builder.
2. **Prepare the artifact.** The sample/source flow creates a deterministic ZIP with sorted paths and fixed archive metadata. Upload registration preserves an existing file's exact bytes. A ZIP artifact is not the same object as its manifest.
3. **Hash the artifact.** Read it in chunks and calculate SHA-256. This fingerprint is the contract lookup key. The artifact filename is descriptive; integrity is checked through its bytes.
4. **Create the manifest.** Record format version, artifact name/hash, full Git commit, dependencies, UTC build timestamp, and builder address. Sort dependencies by name and serialize fields consistently. Commit/dependency metadata is a pipeline claim; this application does not independently rebuild the Git commit or download dependencies.
5. **Build the Merkle tree.** Hash each labeled field and each dependency entry into a leaf, then repeatedly hash pairs until one root remains. Leaves and parents have different byte prefixes to prevent ambiguous interpretation. Duplicate the last node whenever a level has odd width. Without dependencies there are six leaves: version, name, artifact hash, commit, timestamp, builder.
6. **Sign the root.** The pipeline signs the root's 32 bytes with its Ethereum key using EIP-191. This authenticates who attested the root. It does not encrypt or hide the manifest.
7. **Store provenance in IPFS.** Pin one JSON bundle containing the manifest, root, signature, and signer. IPFS returns a CID for those bundle bytes. The artifact itself remains in local/artifact storage; this implementation uploads the provenance bundle to IPFS.
8. **Register on-chain.** Submit a signed transaction calling `registerBuild(artifactHash, root, cid)`. The contract checks pipeline permission and rejects duplicate artifact hashes and invalid zero/empty values. It stores root, CID, pipeline address, block timestamp, and an existence flag. It also emits a registration event.

The root signature and registration transaction are signed for different purposes: the root signature authenticates the off-chain manifest commitment; the transaction signature authenticates the contract caller.

In this demonstration, “build” means packaging the sample source into an artifact, not compiling or testing an arbitrary uploaded project. A real CI system would produce its artifact first, then call the registration flow. The sample's dependency list is empty because the sample app has no third-party dependencies.

## Verification workflow

1. Receive an uploaded artifact or select the saved original. Calculate its actual SHA-256.
2. Without an approved baseline selection, look up the actual hash. With a selected baseline, look up that approved hash, allowing a mismatching candidate to be compared against its intended release.
3. Read the on-chain record and check the registering pipeline's current authorization.
4. Fetch the bundle at the recorded CID. The Kubo client checks returned bytes against that CID using the same import parameters. Retrieval errors block verification.
5. Compare received artifact hash, manifest artifact hash, and lookup hash. All must match.
6. Validate the manifest format, reconstruct its leaves/tree, and compare the computed root with both the bundle root and the contract root.
7. Recover the root-signature address and compare it with the on-chain pipeline. Check that bundle signer and manifest builder agree with that identity.
8. Allow only if all checks pass. Any failed check or processing/network error blocks the result. The CLI exits with 0 for PASS and 1 for blocked/error; the dashboard shows the same gate's result.

There are five displayed checks because IPFS retrieval/CID validation happens as part of obtaining evidence between pipeline authorization and the artifact/manifest/signature checks. An unreachable bundle produces an error and leaves later checks unreached.

## Every dashboard feature

| Feature | How to use it | What to explain |
|---|---|---|
| Service indicators and refresh | Check Ganache/IPFS are Online; refresh after starting a service. | The browser talks to Python; Python talks to the actual local chain and IPFS API. |
| Create sample build | Click once, wait for registration and the verification report. | This runs the full real registration flow. A unique build ID makes each sample's bytes distinct; the displayed repeated-letter commit is demo metadata. |
| Artifact upload / drag-and-drop | Select a file up to 12 MiB. | Selecting a file does not register it; Verify uploads it for checking, while Register explicitly signs and records it. ZIPs support member comparisons. |
| Approved-build selection | Select the intended registered build before verifying the candidate. | Pins the expected release. Otherwise a different legitimately registered build can also be valid. |
| Verify artifact | Upload, optionally select the approved build, then click Verify. | Runs the five independent checks and blocks if any fails. |
| Use selected original | Choose a build with a local original and click this action. | Verifies the saved artifact without needing to browse for the same file. A record without a local copy can still provide provenance/proofs. |
| Register uploaded artifact | Upload; enter a full Git commit and optional dependency JSON; sign/register. | Uses the configured trusted local pipeline identity and preserves uploaded bytes. It is a local demo action, not a public upload service or proof that arbitrary uploads are safe. |
| Verdict and check count | Read ALLOWED/BLOCKED and the reason. | Four successful checks cannot compensate for one failed check. The count is explanatory, not a security score. |
| Five-check flow | Read pass, fail, and not reached states. | Explains where verification caught the mismatch. Not reached is not evidence that this particular check failed. |
| File comparison | After a candidate check against a local original, inspect the member table. | Per-member SHA-256 labels files unchanged, modified, added, or removed. The original is used only after its hash matches the selected record. |
| First changed byte | Read the byte offset above the comparison table. | This is zero-based in the complete artifact. ZIP headers/CRC/metadata can be the first differing bytes; it is not necessarily a source-code character offset. |
| Changed-line view | Expand/read the diff under a modified small text file. | `-` lines belong to the original, `+` lines to the received file; `@@` identifies line ranges. Text diffs require UTF-8 members up to 64 KiB and show at most 120 lines. |
| Fingerprints and provenance | Compare actual/approved hashes and computed/on-chain roots; inspect CID and pipeline. | These are distinct pieces of evidence, not interchangeable identifiers. |
| Manifest view | Expand the manifest in the report. | It shows build metadata from the fetched bundle; its authenticity depends on the report's root/signature checks. In lab simulations it can deliberately be altered. |
| Download report | Export the current report as JSON. | Saves check results, provenance evidence, and any comparisons for inspection. A downloaded report is not independently signed and can be edited; rerun verification for a fresh decision. |
| Tampering lab: change file | Select a locally available ZIP baseline and click Change a file. | A temporary ZIP copy gets a changed member, preferably a `.py` file. The artifact hash fails; root and signature can remain valid for the unchanged original manifest. |
| Tampering lab: append bytes | Choose Append hidden bytes. | Overall artifact SHA-256 changes even if every ZIP member still matches. Extra/container bytes still count. |
| Tampering lab: manifest edit | Choose Edit the manifest. | A labeled simulation changes the fetched commit metadata; recomputation yields the wrong Merkle root. Real IPFS retrieval would also reject altered bundle bytes. |
| Tampering lab: forged signature | Choose Forge the signature. | A labeled simulation signs the original root with an unrelated key; signer identity fails while the root still matches. Real IPFS retrieval would also reject altered bundle bytes. |
| Merkle explorer | Choose a build, then click a manifest entry. | Shows its leaf, left/right sibling hashes, and trusted root. The backend verifies this inclusion proof. The convenience UI fetches the whole manifest to generate it; an independent proof verifier needs only leaf, siblings, and trusted root. |
| Build ledger and refresh | Open history, refresh, and choose Verify or Inspect proof. | Reads real `BuildRegistered` events with artifact fingerprint, date, CID, block, and local-original availability. Existing records cannot be overwritten. |

Comparison is bounded to 500 members and 32 MiB total uncompressed content. Files are read from archives without extraction or execution. When an original is unavailable, a hash can detect a mismatch but cannot locate its member/line. The lab does not determine the attacker, actual attack time, or network hop.

## Owner controls and CLI features

The browser intentionally concentrates on building, checking, and explaining artifacts. Owner administration remains in the CLI:

| Command | Purpose |
|---|---|
| `ledger.py keygen` | Generate a new identity; refuses to overwrite the existing key. |
| `ledger.py deploy` | Deploy compiled Solidity; refuses to overwrite the deployment file. |
| `ledger.py authorize ADDRESS --fund` | Owner authorizes a pipeline and optionally sends 1 local test ETH. |
| `ledger.py revoke ADDRESS` | Owner removes pipeline authorization. Historical records remain, but this verifier blocks their builds while that pipeline is revoked. |
| `ledger.py doctor` | Check chain, deployment, and IPFS connectivity. |
| `ledger.py register SOURCE --commit HASH` | Package source and run the complete registration flow. |
| `ledger.py verify ARTIFACT` | Run the deploy gate; optionally add `--expected-hash HASH` to pin an approved build. |
| `ledger.py tamper-demo ARTIFACT` | Verify clean, append bytes to a new copy, verify the copy; never overwrite the original. |
| `ledger.py proof HASH --index N` | Generate and check a manifest entry's inclusion proof. |

Run commands with `.venv/Scripts/python.exe` before `ledger.py`. Global options such as `--rpc`, `--ipfs`, `--key`, and `--deployment` go before the subcommand. The default pipeline key remains on the Python host and is never returned to the browser or uploaded to IPFS.

## A practical eight-minute presentation

| Time | Show | Say in your own words |
|---|---|---|
| 0:00–0:45 | Project title and problem | “An artifact can change after a successful build. I verify its exact bytes and trusted builder identity before deployment.” |
| 0:45–1:30 | Workflow diagram | Explain artifact → hash → manifest → Merkle root → signature → IPFS → contract. Point out what is stored where. |
| 1:30–2:15 | Create sample build and clean verdict | “This registers a real build. All five checks agree, so the gate allows deployment.” |
| 2:15–3:30 | Change-a-file attack and diff | Point to `app.py`, its added line, changed fingerprint, and BLOCKED verdict. Explain why the original root/signature still pass. |
| 3:30–4:15 | Append-bytes attack | Show unchanged members but changed container hash. Explain why byte integrity is stronger than checking filenames or visible files. |
| 4:15–5:00 | Manifest/signature scenarios | Explicitly identify simulations. Show which distinct check fails and explain CID validation would be an earlier boundary in real retrieval. |
| 5:00–6:00 | Merkle explorer | Choose a field. Explain sibling placement and recomputing to the trusted root without requiring the other field values in an independent proof. |
| 6:00–6:45 | Build ledger and contract | Show history and the Solidity owner/pipeline/duplicate checks. Explain why storage alone is not the trust anchor. |
| 6:45–7:30 | Tests and modules | Mention the documented 35-test suite, real-node integration, and the shared verifier used by browser and CLI. |
| 7:30–8:00 | Limitations and next steps | State local-chain consensus limits, offline IPFS availability, and compromised-builder risk. Suggest real CI integration and testnet deployment. |

For a three-minute slot, show only the problem, clean build, changed-file attack, and one Merkle proof. Avoid spending the presentation installing dependencies. Start the services and open the dashboard beforehand; have the saved screenshot/report ready in case a service is unavailable. A screenshot is a fallback explanation, not a live verification result.

End with: “The project makes an integrity and provenance decision before deployment. It detects changes and unauthorized attestations, while still depending on a trustworthy build pipeline and chain.”

## Five-minute demo

For a visual presentation, start `.venv/Scripts/python.exe -m web.server` after the two services, then open `http://127.0.0.1:8000`.

1. Click **Create sample build** and explain the five green verification checks.
2. Open **Tampering lab**, select the sample, and choose **Change a file**. Show the failed artifact fingerprint, the modified `app.py`, and its changed lines. The original signed manifest still passes because only the artifact copy changed.
3. Try **Append hidden bytes**. All ZIP member contents match, but the container bytes and overall hash differ. Explain why filenames or visual appearance are insufficient.
4. Try **Edit the manifest** and **Forge the signature**. Explain these are teaching simulations of corrupted responses, bypassing IPFS retrieval to isolate root/signature failures. Real retrieval also enforces CID integrity.
5. Open **Merkle explorer**, choose an entry, and follow the siblings to the recorded root.
6. Open **Build ledger** to show the actual registration history. Download a verification report if needed.

The dashboard reuses the same verification gate as the CLI. It does not infer the attacker or the time of modification. Text diffs come from comparing the candidate with a hash-validated local original, not from reversing a SHA-256 hash.

### CLI presentation alternative

1. Start Ganache and IPFS using the README. Run `doctor`; explain the two local services.
2. Show `contracts/BuildRegistry.sol`: owner permissions, pipeline permissions, record fields, and the duplicate-registration check.
3. Run `scripts/demo.ps1` after initial authorization. Read out the artifact hash, root, CID, and transaction hash.
4. Show the generated manifest. Explain that ZIP contents stay outside the chain; only root, CID, registering address, and block timestamp are stored.
5. Show clean verification: all booleans are true.
6. Show tampered verification: the artifact hash is false while the original signed metadata still verifies. The original ZIP is unchanged.
7. Run a proof for the printed artifact hash. Explain how sibling hashes connect a single field to the recorded root.
8. Optionally revoke the pipeline, verify the original again, and show that the record is preserved but deployment is blocked. Reauthorize afterward to continue building.

## Read these functions in order

`build.hash_utils.hash_file` → `build.build_artifact.create_manifest` → `merkle.merkle_tree.leaves_from_manifest` → `build_tree` → `sign.signatures.sign_root` → `IPFSClient.upload_bundle` → `RegistryClient.register_build` → Solidity `registerBuild` → `verify.pipeline.verify_build`.

The CLI only parses arguments and calls these functions. Tests use memory doubles for isolated failure cases; the application always uses real Kubo and Solidity.

## Questions you should be able to answer

| Question | Answer |
|---|---|
| What is provenance? | A record of an artifact's claimed origin and build metadata, bound to its exact bytes and pipeline identity. |
| Why hash the artifact? | A one-byte change produces a different fingerprint with overwhelming probability. We compare bytes through SHA-256, not filenames. |
| Why a Merkle tree? | It commits all fields into one root and supports a short proof for one entry without revealing the entire manifest to a proof verifier. |
| Why not hash the entire JSON? | That would support whole-manifest integrity, but would not provide individual-entry inclusion proofs. |
| How do two machines agree on a root? | Fixed field order, canonical JSON, sorted dependencies, UTC timestamps, and identical leaf/parent/odd-node rules. |
| What exactly is signed? | The 32 raw bytes of the SHA-256 Merkle root, wrapped with Ethereum's EIP-191 message prefix. |
| How is a signer trusted? | Recover its Ethereum address and compare it with the pipeline stored by the contract, then check current authorization. |
| Why IPFS? | Its CID addresses content. The signed bundle stays off-chain, avoiding large on-chain storage. Pinning preserves it locally. |
| Why blockchain? | The contract provides access-controlled, append-only records and transaction events, separate from artifact storage. |
| Is local Ganache decentralized? | No. It demonstrates EVM contract behavior but not real multi-node consensus security. |
| Can the owner edit a record? | No contract function permits overwriting/deleting it. The owner can authorize or remove pipelines. |
| Can an attacker upload a forged manifest? | Yes, but it gets a different CID. Root/signature checks also block changes not matching the recorded provenance. |
| What if the builder is compromised? | A compromised authorized builder can attest malicious code. This system checks provenance, not whether the software is safe. |
| What if IPFS is down? | Verification blocks. Integrity does not imply availability. |
| What if another valid build is substituted? | Verification by hash alone recognizes it as valid. Pin the expected approved hash to enforce a specific release. |
| Does a valid signature prove the commit was built? | No. It proves who attested the metadata. A trustworthy CI checkout/build process is still required. |
| Why is a revoked pipeline's old build blocked? | This implementation requires current authorization, a conservative deploy policy; historical records stay intact. |
| Is this a full CI/CD system? | No. It implements artifact registration and a deploy gate. A real pipeline would call these commands around its build/deploy steps. |

## Explain the three hashes without mixing them up

- **Artifact hash:** SHA-256 of ZIP bytes; lookup key in the contract.
- **Merkle root:** SHA-256 tree commitment to individual manifest entries; signed by the pipeline.
- **CID:** IPFS content identifier of the complete signed bundle; not the artifact hash or the Merkle root.

The manifest timestamp is supplied and signed by the pipeline. The registration timestamp is the chain's block time. They have different sources and meanings.
