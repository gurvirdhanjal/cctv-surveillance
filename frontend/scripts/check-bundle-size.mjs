#!/usr/bin/env node
/**
 * Bundle size guard — 4G.6
 *
 * Reads dist/assets and checks gzip sizes against spec §17 limits:
 *   initial (index.*): ≤ 200 kB gzip
 *   any route chunk:   ≤ 250 kB gzip
 *
 * Exit 0 = all within limits. Exit 1 = at least one violation.
 */

import { readdirSync, readFileSync } from 'fs'
import { resolve, join } from 'path'
import { createGzip } from 'zlib'
import { Readable } from 'stream'

const LIMITS = {
  initial: 200 * 1024,   // 200 kB gzip
  chunk:   250 * 1024,   // 250 kB gzip
}

const distDir = resolve(import.meta.dirname, '../dist/assets')

async function gzipSize(buf) {
  return new Promise((ok, fail) => {
    let total = 0
    const gz = createGzip({ level: 9 })
    Readable.from(buf).pipe(gz)
    gz.on('data', (chunk) => (total += chunk.length))
    gz.on('end', () => ok(total))
    gz.on('error', fail)
  })
}

function fmt(bytes) {
  return `${(bytes / 1024).toFixed(1)} kB`
}

let files
try {
  files = readdirSync(distDir).filter((f) => f.endsWith('.js'))
} catch {
  console.error(`ERROR: dist/assets not found — run "pnpm build" first`)
  process.exit(1)
}

let failed = false

for (const file of files) {
  const buf = readFileSync(join(distDir, file))
  const gz = await gzipSize(buf)
  const isInitial = file.startsWith('index')
  const limit = isInitial ? LIMITS.initial : LIMITS.chunk
  const ok = gz <= limit
  const icon = ok ? '✓' : '✗'
  const tag = isInitial ? 'initial' : 'chunk'
  console.log(`${icon} [${tag}] ${file}: ${fmt(gz)} / ${fmt(limit)}`)
  if (!ok) failed = true
}

if (failed) {
  console.error('\nBundle size limit exceeded. Investigate with: pnpm build --analyze')
  process.exit(1)
} else {
  console.log('\nAll bundle sizes within limits.')
}
