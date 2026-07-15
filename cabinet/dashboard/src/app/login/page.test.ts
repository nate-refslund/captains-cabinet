import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

describe('fresh-Captain login recovery', () => {
  it('names the product correctly and offers the clipboard-only recovery command', () => {
    const source = fs.readFileSync(path.join(__dirname, 'page.tsx'), 'utf8')
    expect(source).toContain('Captain&apos;s Cabinet')
    expect(source).toContain('bash cabinet/scripts/dashboard-password.sh --copy')
    expect(source).toContain('copies it to your clipboard without printing it')
    expect(source).not.toContain('Founder&apos;s Cabinet')
  })
})
