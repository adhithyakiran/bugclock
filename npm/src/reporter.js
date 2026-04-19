'use strict';

const chalk    = require('chalk');
const Table    = require('cli-table3');
const { loadSessions } = require('./storage');
const { durationMinutes } = require('./tracker');

function printReport(days = 30) {
  const sessions  = fetchCompleted(days);

  if (!sessions.length) {
    console.log(chalk.yellow(`\nNo completed sessions in the last ${days} days.\n`));
    console.log(`Run ${chalk.cyan('bugclock start')} to begin tracking.\n`);
    return;
  }

  const stats = computeStats(sessions);

  console.log('\n' + chalk.cyan('━'.repeat(52)));
  console.log(chalk.bold.cyan('  bugclock') + chalk.dim(`  · last ${days} days`));
  console.log(chalk.cyan('━'.repeat(52)));

  // Key metrics
  console.log('');
  printMetrics(stats);

  // Daily chart
  printDailyChart(sessions, Math.min(days, 14));

  // Recent sessions table
  printSessionsTable(sessions.slice(0, 10));

  // Top files
  printTopFiles(sessions);

  const auto = sessions.filter(s => s.source === 'auto').length;
  if (auto) {
    console.log(chalk.dim(`  ${sessions.length - auto} manual · ${auto} auto-inferred from commits\n`));
  }
}

function exportJson(days = 30) {
  return JSON.stringify(
    fetchCompleted(days).map(s => ({ ...s, duration_minutes: durationMinutes(s) })),
    null, 2
  );
}

function exportCsv(days = 30) {
  const sessions = fetchCompleted(days);
  const header   = 'id,started_at,ended_at,duration_minutes,status,files,author,source,notes,commit_hash';
  const rows     = sessions.map(s =>
    [
      s.id,
      s.started_at,
      s.ended_at  || '',
      durationMinutes(s) ?? '',
      s.status,
      `"${(s.files || []).join('; ')}"`,
      s.author    || '',
      s.source    || '',
      `"${(s.notes || '').replace(/"/g, '""')}"`,
      s.commit_hash || '',
    ].join(',')
  );
  return [header, ...rows].join('\n');
}

// ── Private ───────────────────────────────────────────────────────────────────

function fetchCompleted(days) {
  const cutoff = new Date(Date.now() - days * 86400000).toISOString();
  return loadSessions()
    .filter(s => s.status !== 'active' && s.started_at >= cutoff)
    .slice().reverse();
}

function computeStats(sessions) {
  const durations = sessions.map(durationMinutes).filter(d => d != null);
  const resolved  = sessions.filter(s => s.status === 'resolved').length;
  const total     = durations.reduce((a, b) => a + b, 0);
  return {
    total:    sessions.length,
    resolved,
    abandoned: sessions.length - resolved,
    totalMin: Math.round(total * 10) / 10,
    avgMin:   durations.length ? Math.round(total / durations.length * 10) / 10 : 0,
    longestMin: durations.length ? Math.round(Math.max(...durations) * 10) / 10 : 0,
  };
}

function printMetrics(s) {
  const metrics = [
    ['Total Sessions', String(s.total),        chalk.white],
    ['Resolved',       String(s.resolved),     chalk.green],
    ['Abandoned',      String(s.abandoned),    chalk.red],
    ['Total Time',     `${s.totalMin} min`,    chalk.yellow],
    ['Avg / Session',  `${s.avgMin} min`,      chalk.magenta],
    ['Longest',        `${s.longestMin} min`,  chalk.white],
  ];
  metrics.forEach(([label, value, color]) => {
    console.log(`  ${chalk.dim((label + ':').padEnd(18))} ${color(value)}`);
  });
  console.log('');
}

function printDailyChart(sessions, days) {
  const buckets = {};
  for (const s of sessions) {
    const d = durationMinutes(s);
    if (d == null) continue;
    const day = s.started_at.slice(0, 10);
    buckets[day] = (buckets[day] || 0) + d;
  }
  if (!Object.keys(buckets).length) return;

  const maxVal    = Math.max(...Object.values(buckets)) || 1;
  const BAR_WIDTH = 20;
  const today     = new Date();

  console.log(chalk.bold('  Daily Debug Time (minutes)'));
  for (let i = days - 1; i >= 0; i--) {
    const d   = new Date(today);
    d.setDate(today.getDate() - i);
    const day = d.toISOString().slice(0, 10);
    const val = buckets[day] || 0;
    const filled = Math.round((val / maxVal) * BAR_WIDTH);
    const bar = chalk.cyan('█'.repeat(filled)) + chalk.dim('░'.repeat(BAR_WIDTH - filled));
    console.log(`  ${chalk.dim(day)}  ${String(Math.round(val * 10) / 10).padStart(5)}  ${bar}`);
  }
  console.log('');
}

function printSessionsTable(sessions) {
  const table = new Table({
    head: ['#', 'Started', 'Duration', 'Status', 'Files', 'Author'].map(h => chalk.bold(h)),
    colWidths: [5, 18, 10, 12, 32, 16],
    style: { compact: true },
  });

  for (const s of sessions) {
    const dur  = durationMinutes(s);
    const files = (s.files || []).join(', ') || '—';
    const statusColor = { resolved: chalk.green, abandoned: chalk.red }[s.status] || chalk.yellow;
    table.push([
      String(s.id),
      s.started_at.slice(0, 16).replace('T', ' '),
      dur != null ? `${dur} min` : '—',
      statusColor(s.status),
      files.length > 30 ? files.slice(0, 27) + '...' : files,
      s.author || '—',
    ]);
  }

  console.log(chalk.bold('  Recent Sessions'));
  console.log(table.toString());
  console.log('');
}

function printTopFiles(sessions) {
  const timeMap  = {};
  const countMap = {};
  for (const s of sessions) {
    const d = durationMinutes(s) || 0;
    for (const f of s.files || []) {
      timeMap[f]  = (timeMap[f]  || 0) + d;
      countMap[f] = (countMap[f] || 0) + 1;
    }
  }
  if (!Object.keys(timeMap).length) return;

  const top = Object.entries(timeMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);

  const table = new Table({
    head: ['File', 'Sessions', 'Total Time'].map(h => chalk.bold(h)),
    style: { compact: true },
  });
  for (const [f, t] of top) {
    table.push([chalk.cyan(f), String(countMap[f]), `${Math.round(t * 10) / 10} min`]);
  }

  console.log(chalk.bold('  Most-Debugged Files'));
  console.log(table.toString());
  console.log('');
}

module.exports = { printReport, exportJson, exportCsv };
