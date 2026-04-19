'use strict';

const { execSync }       = require('child_process');
const { isClaudeGenerated } = require('./detector');
const { getActiveSession }  = require('./tracker');

try {
  const staged = execSync(
    'git diff --cached --name-only --diff-filter=M',
    { encoding: 'utf8', stdio: ['pipe','pipe','ignore'] }
  ).trim().split('\n').filter(Boolean);

  const claudeFiles = staged.filter(isClaudeGenerated);
  if (!claudeFiles.length) process.exit(0);

  const active = getActiveSession();
  if (active) process.exit(0);

  process.stderr.write(
    '\n[bugclock] Modifying Claude-generated files:\n' +
    claudeFiles.map(f => `  ${f}`).join('\n') +
    '\nNo active debug session. Run `bugclock start` or the post-commit hook will auto-infer it.\n\n'
  );
} catch {
  // never block the commit
}
