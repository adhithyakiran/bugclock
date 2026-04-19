'use strict';
/**
 * JSON-file storage — no native dependencies, works everywhere.
 * sessions.json  → gitignored, personal timing data
 * marked_files.json → committable, shared team registry
 */

const fs   = require('fs');
const path = require('path');

const TRACKER_DIR        = '.claude-tracker';
const SESSIONS_PATH      = path.join(TRACKER_DIR, 'sessions.json');
const MARKED_FILES_PATH  = path.join(TRACKER_DIR, 'marked_files.json');
const ACTIVE_PATH        = path.join(TRACKER_DIR, 'active_session');

function ensureDir() {
  fs.mkdirSync(TRACKER_DIR, { recursive: true });
}

// ── Sessions ──────────────────────────────────────────────────────────────────

function loadSessions() {
  if (!fs.existsSync(SESSIONS_PATH)) return [];
  try { return JSON.parse(fs.readFileSync(SESSIONS_PATH, 'utf8')); }
  catch { return []; }
}

function saveSessions(sessions) {
  ensureDir();
  fs.writeFileSync(SESSIONS_PATH, JSON.stringify(sessions, null, 2));
}

function nextId(sessions) {
  return sessions.length ? Math.max(...sessions.map(s => s.id)) + 1 : 1;
}

// ── Marked files ──────────────────────────────────────────────────────────────

function loadMarkedFiles() {
  if (!fs.existsSync(MARKED_FILES_PATH)) return {};
  try { return JSON.parse(fs.readFileSync(MARKED_FILES_PATH, 'utf8')); }
  catch { return {}; }
}

function saveMarkedFile(filepath, method = 'manual') {
  ensureDir();
  const registry = loadMarkedFiles();
  registry[filepath] = { marked_at: new Date().toISOString(), method };
  fs.writeFileSync(MARKED_FILES_PATH, JSON.stringify(registry, null, 2));
}

function isManuallyMarked(filepath) {
  return filepath in loadMarkedFiles();
}

// ── Active session pointer ────────────────────────────────────────────────────

function getActiveId() {
  if (!fs.existsSync(ACTIVE_PATH)) return null;
  try { return parseInt(fs.readFileSync(ACTIVE_PATH, 'utf8').trim(), 10); }
  catch { return null; }
}

function setActiveId(id) {
  ensureDir();
  if (id == null) {
    if (fs.existsSync(ACTIVE_PATH)) fs.unlinkSync(ACTIVE_PATH);
  } else {
    fs.writeFileSync(ACTIVE_PATH, String(id));
  }
}

module.exports = {
  TRACKER_DIR,
  SESSIONS_PATH,
  MARKED_FILES_PATH,
  loadSessions,
  saveSessions,
  nextId,
  loadMarkedFiles,
  saveMarkedFile,
  isManuallyMarked,
  getActiveId,
  setActiveId,
  ensureDir,
};
