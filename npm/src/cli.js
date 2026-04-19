'use strict';

const { Command } = require('commander');
const chalk       = require('chalk');
const fs          = require('fs');
const path        = require('path');

const { version }   = require('../package.json');
const storage       = require('./storage');
const tracker       = require('./tracker');
const detector      = require('./detector');
const reporter      = require('./reporter');
const hooks         = require('./hooks');

const program = new Command();

program
  .name('bugclock')
  .description('Track debugging time spent on Claude-generated code')
  .version(version);

// ── init ──────────────────────────────────────────────────────────────────────

program
  .command('init')
  .description('Set up bugclock in the current repo')
  .action(() => {
    storage.ensureDir();
    console.log('');
    console.log(chalk.cyan('━'.repeat(50)));
    console.log(chalk.bold.cyan('  bugclock') + chalk.dim('  initialized'));
    console.log(chalk.cyan('━'.repeat(50)));
    console.log(`  Database  ${chalk.dim('.claude-tracker/sessions.json')}`);
    console.log(`  Registry  ${chalk.dim('.claude-tracker/marked_files.json')}  ${chalk.green('(committable)')}`);
    console.log('');
    hooks.install(false);
    console.log(`  ${chalk.green('✓')} Git hooks installed  ${chalk.dim('(pre-commit, post-commit)')}`);
    console.log('');
    console.log('  Next steps:');
    console.log(`    ${chalk.cyan('bugclock mark <file>')}  — tag a file as Claude-generated`);
    console.log(`    ${chalk.cyan('bugclock start')}        — begin a debug session`);
    console.log(`    ${chalk.cyan('bugclock report')}       — view analytics`);
    console.log('');
  });

// ── start ─────────────────────────────────────────────────────────────────────

program
  .command('start')
  .description('Begin a debug session')
  .option('-f, --file <path>', 'file being debugged (repeatable)', collect, [])
  .option('-n, --note <text>', 'note about the bug', '')
  .action((opts) => {
    const active = tracker.getActiveSession();
    if (active) {
      console.log(chalk.yellow(`Session #${active.id} already active`) +
        ` (started ${active.started_at.slice(0,16).replace('T',' ')} UTC)`);
      console.log(`Run ${chalk.cyan('bugclock stop')} first.`);
      process.exit(1);
    }

    const files       = opts.file;
    const claudeFiles = files.filter(detector.isClaudeGenerated);
    const session     = tracker.startSession({ files, notes: opts.note });

    console.log('');
    console.log(`${chalk.green('✓')} Debug session ${chalk.bold('#' + session.id)} started`);
    if (files.length)       console.log(`  Files:            ${files.join(', ')}`);
    if (claudeFiles.length) console.log(`  ${chalk.cyan('Claude-generated:')} ${claudeFiles.join(', ')}`);
    console.log(`  Run ${chalk.cyan('bugclock stop')} when done.`);
    console.log('');
  });

// ── stop ──────────────────────────────────────────────────────────────────────

program
  .command('stop')
  .description('End the current debug session')
  .option('--resolved',  'mark as resolved (default)', true)
  .option('--abandoned', 'mark as abandoned')
  .option('-n, --note <text>', 'resolution note', '')
  .action((opts) => {
    const active = tracker.getActiveSession();
    if (!active) {
      console.log(chalk.yellow('No active debug session found.'));
      process.exit(1);
    }
    const status = opts.abandoned ? 'abandoned' : 'resolved';
    const result = tracker.stopSession(active.id, { status, notes: opts.note });
    const dur    = tracker.durationMinutes(result);
    const color  = status === 'resolved' ? chalk.green : chalk.red;

    console.log('');
    console.log(
      `${color('✓')} Session ${chalk.bold('#' + result.id)} ${color(status)}  —  ` +
      `${chalk.bold(dur + ' min')} spent debugging`
    );
    console.log('');
  });

// ── status ────────────────────────────────────────────────────────────────────

program
  .command('status')
  .description('Show the currently active session')
  .action(() => {
    const active = tracker.getActiveSession();
    if (!active) {
      console.log(chalk.dim('No active debug session.'));
      return;
    }
    const elapsed = Math.round((Date.now() - new Date(active.started_at)) / 60000 * 10) / 10;
    const files   = (active.files || []).join(', ') || '—';
    console.log('');
    console.log(chalk.green(`  Session #${active.id} — ACTIVE`));
    console.log(`  Started   ${active.started_at.slice(0,16).replace('T',' ')} UTC`);
    console.log(`  Elapsed   ${chalk.yellow(elapsed + ' min')}`);
    console.log(`  Files     ${files}`);
    console.log(`  Author    ${active.author || '—'}`);
    console.log('');
  });

// ── report ────────────────────────────────────────────────────────────────────

program
  .command('report')
  .description('Show full analytics dashboard')
  .option('--days <n>', 'days to include', v => parseInt(v, 10), 30)
  .action((opts) => reporter.printReport(opts.days));

// ── sessions ──────────────────────────────────────────────────────────────────

program
  .command('sessions')
  .description('List recent debug sessions')
  .option('--limit <n>', 'max sessions to show', v => parseInt(v, 10), 20)
  .option('--status <s>', 'filter by status (resolved|abandoned|active)')
  .action((opts) => {
    const rows = tracker.listSessions({ limit: opts.limit, status: opts.status });
    if (!rows.length) { console.log(chalk.dim('No sessions found.')); return; }

    const Table = require('cli-table3');
    const table = new Table({
      head: ['#','Started','Duration','Status','Source','Files'].map(h => chalk.bold(h)),
      style: { compact: true },
    });
    for (const s of rows) {
      const dur   = tracker.durationMinutes(s);
      const color = { resolved: chalk.green, abandoned: chalk.red, active: chalk.yellow }[s.status] || chalk.white;
      const files = (s.files||[]).join(', ') || '—';
      table.push([
        String(s.id),
        s.started_at.slice(0,16).replace('T',' '),
        dur != null ? `${dur} min` : chalk.yellow('active'),
        color(s.status),
        s.source || 'manual',
        files.length > 38 ? files.slice(0,35)+'...' : files,
      ]);
    }
    console.log(table.toString());
  });

// ── scan ──────────────────────────────────────────────────────────────────────

program
  .command('scan')
  .description('Find all Claude-generated files in the repo')
  .action(() => {
    console.log(chalk.dim('Scanning repository…'));
    const files = detector.scanRepo();
    if (!files.length) {
      console.log(chalk.yellow('No Claude-generated files detected.'));
      console.log(`Add ${chalk.cyan('# @claude-generated')} to any file, or run ${chalk.cyan('bugclock mark <file>')}.`);
      return;
    }
    console.log(`\n${chalk.green('Found ' + files.length + ' Claude-generated file(s):')}\n`);
    files.forEach(f => console.log(`  ${chalk.cyan(f)}`));
    console.log('');
  });

// ── mark ──────────────────────────────────────────────────────────────────────

program
  .command('mark <filepath>')
  .description('Manually tag a file as Claude-generated')
  .action((filepath) => {
    if (!fs.existsSync(filepath)) {
      console.log(chalk.red('File not found: ') + filepath);
      process.exit(1);
    }
    storage.saveMarkedFile(filepath);
    console.log(`${chalk.green('✓')} Marked ${chalk.cyan(filepath)} as Claude-generated`);
    console.log(`  Registry: ${chalk.dim(storage.MARKED_FILES_PATH)}  ${chalk.dim('(commit this to share with your team)')}`);
  });

// ── export ────────────────────────────────────────────────────────────────────

program
  .command('export')
  .description('Export session data as JSON or CSV')
  .option('--format <fmt>', 'json or csv', 'json')
  .option('--days <n>', 'days to include', v => parseInt(v, 10), 30)
  .option('-o, --output <path>', 'output file (default: stdout)')
  .action((opts) => {
    const data = opts.format === 'csv'
      ? reporter.exportCsv(opts.days)
      : reporter.exportJson(opts.days);

    if (opts.output) {
      fs.writeFileSync(opts.output, data);
      console.log(`${chalk.green('✓')} Exported to ${chalk.cyan(opts.output)}`);
    } else {
      process.stdout.write(data + '\n');
    }
  });

// ── uninstall ─────────────────────────────────────────────────────────────────

program
  .command('uninstall')
  .description('Remove git hooks installed by bugclock')
  .action(() => {
    hooks.uninstall(true);
    console.log(`${chalk.green('✓')} Hooks removed. Session data is still in ${chalk.dim('.claude-tracker/')}`);
  });

// ── helpers ───────────────────────────────────────────────────────────────────

function collect(val, prev) { return prev.concat([val]); }

program.parse(process.argv);
