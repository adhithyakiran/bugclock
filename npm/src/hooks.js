'use strict';

const fs   = require('fs');
const path = require('path');

const HOOKS_DIR = path.join('.git', 'hooks');

const PRE_COMMIT = `#!/bin/sh
# bugclock
node -e "try{require('bugclock/src/hook-precommit')}catch(e){}" 2>/dev/null || true
`;

const POST_COMMIT = `#!/bin/sh
# bugclock
node -e "try{require('bugclock/src/hook-postcommit')}catch(e){}" 2>/dev/null || true
`;

function install(verbose = true) {
  if (!fs.existsSync(HOOKS_DIR)) {
    if (verbose) console.log('  [warn] .git/hooks not found — is this a git repo?');
    return false;
  }
  writeHook('pre-commit',  PRE_COMMIT);
  writeHook('post-commit', POST_COMMIT);
  if (verbose) console.log('  ✓ Git hooks installed (pre-commit, post-commit)');
  return true;
}

function uninstall(verbose = true) {
  for (const name of ['pre-commit', 'post-commit']) {
    const p = path.join(HOOKS_DIR, name);
    if (!fs.existsSync(p)) continue;
    const content = fs.readFileSync(p, 'utf8');
    if (content.includes('bugclock')) {
      fs.unlinkSync(p);
      if (verbose) console.log(`  ✓ Removed ${name} hook`);
    }
  }
}

function writeHook(name, content) {
  const hookPath = path.join(HOOKS_DIR, name);
  if (fs.existsSync(hookPath)) {
    const existing = fs.readFileSync(hookPath, 'utf8');
    if (!existing.includes('bugclock')) {
      fs.writeFileSync(hookPath, existing.trimEnd() + '\n\n' + content);
    }
  } else {
    fs.writeFileSync(hookPath, content);
  }
  // make executable (no-op on Windows, fine on Unix)
  try { fs.chmodSync(hookPath, 0o755); } catch {}
}

module.exports = { install, uninstall };
