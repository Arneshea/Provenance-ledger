const fs = require('node:fs');
const path = require('node:path');
const solc = require('solc');
const root = path.resolve(__dirname, '..');
const input = {
  language: 'Solidity',
  sources: { 'BuildRegistry.sol': { content: fs.readFileSync(path.join(root, 'contracts/BuildRegistry.sol'), 'utf8') } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: 'shanghai',
    outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } } }
};
const output = JSON.parse(solc.compile(JSON.stringify(input)));
for (const error of output.errors || []) console.error(error.formattedMessage);
if ((output.errors || []).some(e => e.severity === 'error')) process.exit(1);
const contract = output.contracts['BuildRegistry.sol'].BuildRegistry;
fs.writeFileSync(path.join(root, 'contracts/compiled.json'), JSON.stringify({
  compiler: solc.version(), abi: contract.abi, bytecode: '0x' + contract.evm.bytecode.object
}, null, 2));
console.log('Compiled BuildRegistry (Solidity ' + solc.version() + ')');
