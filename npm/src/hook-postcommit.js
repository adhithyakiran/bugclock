'use strict';

const { execSync }                                   = require('child_process');
const { isClaudeGenerated }                          = require('./detector');
const { getActiveSession, stopSession,
        inferSessionFromCommit, durationMinutes }     = require('./tracker');

try {
  const commitMsg = execSync(
    'git log -1 --format=%s',
    { encoding: 'utf8', stdio: ['pipe','pipe','ignore'] }
  ).trim();

  const changed = execSync(
    'git diff-tree --no-commit-id -r --name-only HEAD',
    { encoding: 'utf8', stdio: ['pipe','pipe','ignore'] }
  ).trim().split('\n').filter(Boolean);

  const claudeFiles = changed.filter(isClaudeGenerated);
  if (!claudeFiles.length) process.exit(0);

  // Close an open manual session
  const active = getActiveSession();
  if (active) {
    const result = stopSession(active.id, { status: 'resolved' });
    const dur    = durationMinutes(result);
    process.stderr.write(
      `\n[bugclock] Session #${active.id} auto-closed (${dur} min) on commit "${commitMsg.slice(0, 60)}"\n\n`
    );
    process.exit(0);
  }

  // Auto-infer from file modification times
  const dur     = estimateDuration(claudeFiles);
  const session = inferSessionFromCommit(claudeFiles, commitMsg, dur);
  if (session) {
    process.stderr.write(
      `\n[bugclock] Auto-recorded session #${session.id} (~${Math.round(dur * 10) / 10} min) for: ${claudeFiles.slice(0, 3).join(', ')}\n\n`
    );
  }
} catch {
  // never block the commit
}

function estimateDuration(files) {
  const now    = Date.now();
  let oldest   = now;
  for (const f of files) {
    try {
      const mtime = require('fs').statSync(f).mtimeMs;
      if (mtime < oldest) oldest = mtime;
    } catch {}
  }
  return Math.min((now - oldest) / 60000, 240); // cap at 4 hours
}
