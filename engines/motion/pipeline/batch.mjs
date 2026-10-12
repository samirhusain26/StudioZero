// Write library/<batch>/batch.json (contract v1) through the shared packager (tools/package.mjs) for project scalargame.
//   node engines/motion/pipeline/batch.mjs --batch=<batchId> [--set=questions-<set> | --set=<path/to/set.mjs>] [--dir=<batch dir>] [--dry] [--no-validate]
// Reads each validated job's render.json (render.mjs writes it), the checked set and projects/scalargame (captions,
// links, hashtags), then runs the contract validator. --dry checks captions → library/_dev/batch-dry.json.
import {main} from '../../../tools/package.mjs';

process.exitCode = await main(['--project=scalargame', ...process.argv.slice(2)]);
