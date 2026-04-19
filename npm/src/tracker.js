'use strict';

const { execSync }                               = require('child_process');
const { loadSessions, saveSessions, nextId,
        getActiveId, setActiveId }               = require('./storage');

const FIX_KEYWORDS = [
  'fix','bug','debug','patch','resolve','correct',
  'repair','hotfix','issue','error','broken','crash',
];

function startSession({ files = [], notes = '', source = 'manual' } = {}) {
  const sessions = loadSessions();
  const id       = nextId(sessions);
  const session  = {
    id,
    started_at:  new Date().toISOString(),
    ended_at:    null,
    status:      'active',
    files,
    notes,
    author:      gitAuthor(),
    source,
    commit_hash: null,
  };
  sessions.push(session);
  saveSessions(sessions);
  setActiveId(id);
  return session;
}

function stopSession(id, { status = 'resolved', notes = '' } = {}) {
  const sessions = loadSessions();
  const session  = sessions.find(s => s.id === id);
  if (!session) throw new Error(`Session ${id} not found`);

  session.ended_at    = new Date().toISOString();
  session.status      = status;
  session.commit_hash = currentCommit();
  if (notes) session.notes = [session.notes, notes].filter(Boolean).join(' | ');

  saveSessions(sessions);
  if (getActiveId() === id) setActiveId(null);
  return session;
}

function getActiveSession() {
  const sessions = loadSessions();
  const id       = getActiveId();
  if (id != null) {
    const s = sessions.find(s => s.id === id && s.status === 'active');
    if (s) return s;
  }
  return sessions.slice().reverse().find(s => s.status === 'active') ?? null;
}

function listSessions({ limit = 20, status = null } = {}) {
  let sessions = loadSessions().slice().reverse();
  if (status) sessions = sessions.filter(s => s.status === status);
  return sessions.slice(0, limit);
}

function inferSessionFromCommit(files, commitMessage, durationMinutes) {
  const msg = (commitMessage || '').toLowerCase();
  if (!FIX_KEYWORDS.some(kw => msg.includes(kw))) return null;

  const now     = new Date();
  const started = new Date(now - durationMinutes * 60 * 1000);
  const sessions = loadSessions();
  const id       = nextId(sessions);

  const session = {
    id,
    started_at:  started.toISOString(),
    ended_at:    now.toISOString(),
    status:      'resolved',
    files,
    notes:       `Auto-inferred from commit: ${commitMessage.slice(0, 120)}`,
    author:      gitAuthor(),
    source:      'auto',
    commit_hash: currentCommit(),
  };
  sessions.push(session);
  saveSessions(sessions);
  return session;
}

function durationMinutes(session) {
  if (!session.started_at || !session.ended_at) return null;
  const ms = new Date(session.ended_at) - new Date(session.started_at);
  return Math.round(ms / 60000 * 10) / 10;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function gitAuthor() {
  try {
    return execSync('git config user.name',
      { encoding: 'utf8', stdio: ['pipe','pipe','ignore'] }).trim();
  } catch { return process.env.USER || 'unknown'; }
}

function currentCommit() {
  try {
    return execSync('git rev-parse HEAD',
      { encoding: 'utf8', stdio: ['pipe','pipe','ignore'] }).trim();
  } catch { return null; }
}

module.exports = {
  startSession, stopSession, getActiveSession,
  listSessions, inferSessionFromCommit, durationMinutes,
};
