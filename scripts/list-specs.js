const fs = require('fs');
const path = require('path');

const IGNORE_DIRS = new Set([
  'node_modules',
  '.git',
  '.venv',
  'dist',
  'build',
  '.pytest_cache',
  '.ruff_cache',
  'coverage',
  '.idea',
  '.vscode',
]);

function findSpecs(dir) {
  let results = [];
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    return results;
  }

  for (const entry of entries) {
    if (entry.isDirectory()) {
      if (IGNORE_DIRS.has(entry.name)) continue;
      results.push(...findSpecs(path.join(dir, entry.name)));
    } else {
      const lower = entry.name.toLowerCase();
      if (lower.includes('spec')) {
        results.push(path.join(dir, entry.name));
      }
    }
  }
  return results;
}

const specs = findSpecs('.');
for (const s of specs) {
  console.log(s);
}
