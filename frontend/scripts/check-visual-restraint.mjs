/**
 * §T Visual Restraint gate — exits non-zero if forbidden token or color patterns found.
 *
 * Forbidden patterns:
 *   1. ring-brand / outline-brand — brass on focus rings (always wrong)
 *   2. Invented tokens not in the design system:
 *      surface-elevated, border-subtle, border-muted, text-tertiary, surface-hover
 */

import { readFileSync, readdirSync, statSync } from 'fs'
import { join, extname } from 'path'
import { fileURLToPath } from 'url'
import { dirname } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SRC_DIR = join(__dirname, '..', 'src')

const FORBIDDEN = [
  { pattern: /ring-brand/, label: 'brass focus ring (ring-brand)' },
  { pattern: /outline-brand/, label: 'brass focus outline (outline-brand)' },
  { pattern: /\bsurface-elevated\b/, label: 'invented token: surface-elevated (use surface-raised)' },
  { pattern: /\bborder-subtle\b/, label: 'invented token: border-subtle (use border)' },
  { pattern: /\bborder-muted\b/, label: 'invented token: border-muted (use border)' },
  { pattern: /\btext-tertiary\b/, label: 'invented token: text-tertiary (use text-muted)' },
  { pattern: /\bsurface-hover\b/, label: 'invented token: surface-hover (use surface-raised or surface-sunken)' },
]

function walk(dir) {
  const entries = readdirSync(dir)
  const files = []
  for (const entry of entries) {
    const full = join(dir, entry)
    const stat = statSync(full)
    if (stat.isDirectory()) {
      files.push(...walk(full))
    } else if (['.tsx', '.ts', '.css'].includes(extname(entry)) && !entry.includes('.test.')) {
      files.push(full)
    }
  }
  return files
}

const files = walk(SRC_DIR)
const violations = []

for (const filePath of files) {
  const content = readFileSync(filePath, 'utf-8')
  const lines = content.split('\n')
  lines.forEach((line, i) => {
    for (const { pattern, label } of FORBIDDEN) {
      if (pattern.test(line)) {
        violations.push(`${filePath}:${i + 1} — ${label}\n  ${line.trim()}`)
      }
    }
  })
}

if (violations.length > 0) {
  console.error(`\n§T Visual Restraint gate: ${violations.length} violation(s) found:\n`)
  violations.forEach((v) => console.error(`  ✗ ${v}\n`))
  process.exit(1)
} else {
  console.log('§T Visual Restraint gate: ✓ no violations found.')
  process.exit(0)
}
