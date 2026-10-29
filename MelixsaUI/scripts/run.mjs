import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { spawn } from 'node:child_process';

// Resolve npm next to Node, avoiding stale global npm launchers on Windows.
const npm = join(dirname(process.execPath), 'node_modules', 'npm', 'bin', 'npm-cli.js');
const args = process.argv.slice(2);
const install = args[0] === 'install';
// Keep dependency caches inside the project, including on restricted workspaces.
if (install && !args.includes('--cache')) args.push('--cache', '.npm-cache');
const npmArgs = install ? args : ['run', args[0], '--', ...args.slice(1)];
const child = existsSync(npm)
  ? spawn(process.execPath, [npm, ...npmArgs], { stdio: 'inherit' })
  : spawn(process.platform === 'win32' ? 'npm.cmd' : 'npm', npmArgs, { stdio: 'inherit', shell: process.platform === 'win32' });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
