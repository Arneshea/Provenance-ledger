// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @notice Append-only artifact provenance registry for a trusted CI pipeline.
contract BuildRegistry {
    address public immutable owner;
    mapping(address => bool) private pipelines;

    struct Build {
        bytes32 merkleRoot;
        string cid;
        address pipeline;
        uint256 timestamp;
        bool exists;
    }
    mapping(bytes32 => Build) private builds;

    event PipelineAdded(address indexed pipeline);
    event PipelineRemoved(address indexed pipeline);
    event BuildRegistered(bytes32 indexed artifactHash, bytes32 merkleRoot,
                          string cid, address indexed pipeline, uint256 timestamp);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }
    modifier onlyPipeline() {
        require(pipelines[msg.sender], "Unauthorized pipeline");
        _;
    }
    constructor() { owner = msg.sender; }

    function addPipeline(address pipeline) external onlyOwner {
        require(pipeline != address(0), "Zero pipeline");
        require(!pipelines[pipeline], "Already authorized");
        pipelines[pipeline] = true;
        emit PipelineAdded(pipeline);
    }
    function removePipeline(address pipeline) external onlyOwner {
        require(pipelines[pipeline], "Not authorized");
        pipelines[pipeline] = false;
        emit PipelineRemoved(pipeline);
    }
    function isAuthorized(address pipeline) external view returns (bool) {
        return pipelines[pipeline];
    }
    function registerBuild(bytes32 artifactHash, bytes32 merkleRoot, string calldata cid)
        external onlyPipeline
    {
        require(artifactHash != bytes32(0) && merkleRoot != bytes32(0), "Zero hash or root");
        require(bytes(cid).length > 0 && bytes(cid).length <= 128, "Invalid CID length");
        require(!builds[artifactHash].exists, "Build already registered");
        builds[artifactHash] = Build(merkleRoot, cid, msg.sender, block.timestamp, true);
        emit BuildRegistered(artifactHash, merkleRoot, cid, msg.sender, block.timestamp);
    }
    function getBuild(bytes32 artifactHash) external view returns (Build memory) {
        return builds[artifactHash];
    }
}
