// vault.ts — confinement + root-resolution teeth.
//
// Every filesystem read in the vault browser flows through resolveInVault();
// these tests are the negative controls for path traversal, absolute paths,
// NUL injection, and — the star — SYMLINK ESCAPE (an in-vault symlink whose
// realpath lands outside the root must be denied). Plus: root resolution is a
// faithful org_vault_dir() mirror that fail-closes and NEVER reads the personal
// `vault_dir` key. Fixtures are temp dirs — the real vault is never touched.

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import fs from 'fs'
import os from 'os'
import path from 'path'
import {
  vaultRoot,
  hasVault,
  resolveInVault,
  VaultPathError,
  listDir,
  readNote,
  classifyPath,
  buildBasenameIndex,
  resolveNoteTarget,
  resetVaultRootCache,
  resetBasenameIndexCache,
} from './vault'

const ENV_KEYS = [
  'CABINET_ROOT',
  'CABINET_ORG_VAULT_DIR',
  'CABINET_PRODUCT_BRAIN_DIR',
] as const

let saved: Record<string, string | undefined>
let vault: string
let outside: string

function clearEnv() {
  for (const k of ENV_KEYS) delete process.env[k]
  resetVaultRootCache()
  resetBasenameIndexCache()
}

/** Build a populated fixture vault + an outside dir with a secret, plus
 *  symlinks (dir + file) that escape the vault. Points the resolver at it. */
function makeFixtureVault(): void {
  vault = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vault-fx-')))
  outside = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vault-out-')))

  fs.writeFileSync(path.join(outside, 'secret.txt'), 'TOP SECRET')

  fs.mkdirSync(path.join(vault, 'decisions'))
  fs.writeFileSync(path.join(vault, 'decisions', 'n.md'), '# N\n\nbody')
  fs.writeFileSync(path.join(vault, 'README.md'), '# Readme')
  fs.writeFileSync(path.join(vault, 'data.txt'), 'not markdown')
  fs.mkdirSync(path.join(vault, 'notes'))
  fs.writeFileSync(path.join(vault, 'notes', 'alpha.md'), '# Alpha')
  fs.writeFileSync(path.join(vault, 'notes', 'beta.markdown'), '# Beta')
  // dotdir + dotfile — must be excluded from listings
  fs.mkdirSync(path.join(vault, '.git'))
  fs.writeFileSync(path.join(vault, '.git', 'config'), 'x')
  fs.writeFileSync(path.join(vault, '.gitkeep'), '')

  // Escaping symlinks: a dir symlink and a .md-named file symlink, both → outside.
  fs.symlinkSync(outside, path.join(vault, 'escape'), 'dir')
  fs.symlinkSync(path.join(outside, 'secret.txt'), path.join(vault, 'leak.md'), 'file')

  // A title-addressed archive whose files were renamed to lib-<id>-<slug>.md
  // (retire-library export). Wikilinks in the corpus address these by TITLE.
  fs.mkdirSync(path.join(vault, 'library-archive'))
  fs.writeFileSync(
    path.join(vault, 'library-archive', 'lib-2-product-overview.md'),
    '---\ntitle: Product Overview\n---\n# Product Overview\n\nbody'
  )
  fs.writeFileSync(
    path.join(vault, 'library-archive', 'lib-4-decisions-index.md'),
    '---\ntitle: Decisions Index\n---\n# Decisions Index\n\nbody'
  )
  // No frontmatter title — resolves only via the stripped-basename slug key.
  fs.writeFileSync(
    path.join(vault, 'library-archive', 'lib-9-plain-note.md'),
    '# Plain Note\n\nno frontmatter title here'
  )

  process.env.CABINET_ORG_VAULT_DIR = vault
  resetVaultRootCache()
  resetBasenameIndexCache()
}

beforeEach(() => {
  saved = {}
  for (const k of ENV_KEYS) saved[k] = process.env[k]
  clearEnv()
})

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k]
    else process.env[k] = saved[k]
  }
  resetVaultRootCache()
  resetBasenameIndexCache()
})

describe('resolveInVault — traversal negative controls', () => {
  beforeEach(makeFixtureVault)

  it('denies parent-escape ../../etc/passwd', () => {
    expect(() => resolveInVault('../../etc/passwd')).toThrow(VaultPathError)
  })

  it('denies an absolute path /etc/passwd', () => {
    expect(() => resolveInVault('/etc/passwd')).toThrow(VaultPathError)
  })

  it('denies a mid-path escape decisions/../../../x', () => {
    expect(() => resolveInVault('decisions/../../../x')).toThrow(VaultPathError)
  })

  it('denies pre-decoded encoded traversal ..%2f..%2f (literal dots after decode)', () => {
    // Next decodes %2e%2e%2f before the param reaches us; simulate the decoded form.
    expect(() => resolveInVault('../../secret.txt')).toThrow(VaultPathError)
    // The literal (still-encoded) form is just a normal, non-existent name → miss.
    expect(() => resolveInVault('..%2f..%2fsecret.txt')).toThrow(VaultPathError)
  })

  it('denies a NUL byte in the path', () => {
    expect(() => resolveInVault('foo\0.md')).toThrow(VaultPathError)
  })

  it('★ denies SYMLINK ESCAPE — dir symlink target outside the vault', () => {
    // realpath('escape/secret.txt') lands in `outside`; the post-symlink
    // prefix-assert must reject it.
    expect(() => resolveInVault('escape/secret.txt')).toThrow(VaultPathError)
    expect(() => resolveInVault('escape')).toThrow(VaultPathError)
  })

  it('★ denies a .md-named symlink whose target escapes the vault', () => {
    // Passes the extension check but realpath escapes → readNote must 404.
    expect(() => resolveInVault('leak.md')).toThrow(VaultPathError)
    expect(() => readNote('leak.md')).toThrow(VaultPathError)
  })

  it('denies a dotfile read (.git/config)', () => {
    // resolveInVault itself confines but does not filter dotfiles; the value is
    // that content readers reject it as non-markdown, and listings exclude it.
    expect(() => readNote('.git/config')).toThrow(VaultPathError)
  })
})

describe('resolveInVault + readNote — positive controls', () => {
  beforeEach(makeFixtureVault)

  it('resolves an in-vault note under the realpath root', () => {
    const real = resolveInVault('decisions/n.md')
    expect(fs.existsSync(real)).toBe(true)
    expect(real.startsWith(vault + path.sep)).toBe(true)
    expect(real.endsWith(path.join('decisions', 'n.md'))).toBe(true)
  })

  it('reads a note and strips frontmatter', () => {
    fs.writeFileSync(
      path.join(vault, 'fm.md'),
      '---\ntitle: Hello\ndate: "2026-07-17"\n---\n# Body\n\ntext'
    )
    const note = readNote('fm.md')
    expect(note.frontmatter).toEqual({ title: 'Hello', date: '2026-07-17' })
    expect(note.body.startsWith('# Body')).toBe(true)
    expect(note.headings[0]).toMatchObject({ text: 'Body', level: 1 })
  })

  it('frontmatter parses via the SAFE js-yaml schema — a hostile value stays inert data', () => {
    fs.writeFileSync(
      path.join(vault, 'hostile-fm.md'),
      '---\nevil: "<script>alert(1)</script>"\n---\nbody'
    )
    const note = readNote('hostile-fm.md')
    // The value is a plain STRING (data), never markup and never a constructed
    // object — the page prints it as React text, which escapes it.
    expect(note.frontmatter?.evil).toBe('<script>alert(1)</script>')
    expect(typeof note.frontmatter?.evil).toBe('string')
  })

  it('refuses to content-read a non-markdown file', () => {
    expect(() => readNote('data.txt')).toThrow(VaultPathError)
  })

  it('classifyPath: root→dir, note→file, missing→null, non-md→null', () => {
    expect(classifyPath('')).toBe('dir')
    expect(classifyPath('decisions')).toBe('dir')
    expect(classifyPath('decisions/n.md')).toBe('file')
    expect(classifyPath('nope/missing.md')).toBeNull()
    expect(classifyPath('data.txt')).toBeNull()
    expect(classifyPath('leak.md')).toBeNull() // symlink escape → null
  })
})

describe('listDir — confinement + filtering', () => {
  beforeEach(makeFixtureVault)

  it('lists dirs-first, excludes dotfiles, non-md, and escaping symlinks', () => {
    const names = listDir('').map((e) => e.name)
    // Dirs first (decisions, notes), then files (README.md). No dotfiles,
    // no data.txt, and crucially NO `escape`/`leak.md` symlinks.
    expect(names).toContain('decisions')
    expect(names).toContain('notes')
    expect(names).toContain('README.md')
    expect(names).not.toContain('.git')
    expect(names).not.toContain('.gitkeep')
    expect(names).not.toContain('data.txt')
    expect(names).not.toContain('escape')
    expect(names).not.toContain('leak.md')
    // dirs sort before files
    expect(names.indexOf('decisions')).toBeLessThan(names.indexOf('README.md'))
  })

  it('entry relPaths are vault-relative and re-confine', () => {
    const entries = listDir('notes')
    for (const e of entries) {
      expect(e.relPath.startsWith('notes/')).toBe(true)
      expect(() => resolveInVault(e.relPath)).not.toThrow()
    }
  })
})

describe('vaultRoot — mirrors org_vault_dir(), never the personal vault_dir', () => {
  it('★ a config with ONLY vault_dir set resolves to <repo>/vault, not the personal path', () => {
    const repo = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vault-repo-')))
    fs.mkdirSync(path.join(repo, 'instance', 'config'), { recursive: true })
    const personal = path.join(repo, 'PERSONAL-BRAIN-DO-NOT-SERVE')
    fs.mkdirSync(personal)
    fs.writeFileSync(path.join(personal, 'private.md'), 'secret diary')
    // platform.yml carries ONLY the personal vault_dir key — no org_vault_dir.
    fs.writeFileSync(
      path.join(repo, 'instance', 'config', 'platform.yml'),
      `vault_dir: ${personal}\n`
    )
    fs.mkdirSync(path.join(repo, 'vault'))
    fs.writeFileSync(path.join(repo, 'vault', 'ok.md'), '# ok')

    process.env.CABINET_ROOT = repo
    resetVaultRootCache()

    const root = vaultRoot()
    expect(root).toBe(path.join(repo, 'vault'))
    expect(root).not.toBe(personal)
    expect(root).not.toContain('PERSONAL-BRAIN')
  })

  it('honors the org_vault_dir config key when its dir exists', () => {
    const repo = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vault-repo2-')))
    fs.mkdirSync(path.join(repo, 'instance', 'config'), { recursive: true })
    fs.mkdirSync(path.join(repo, 'corpus'))
    fs.writeFileSync(
      path.join(repo, 'instance', 'config', 'platform.yml'),
      `vault_dir: /nope/personal\norg_vault_dir: corpus\n`
    )
    process.env.CABINET_ROOT = repo
    resetVaultRootCache()
    expect(vaultRoot()).toBe(path.join(repo, 'corpus'))
  })

  it('env CABINET_ORG_VAULT_DIR wins verbatim', () => {
    process.env.CABINET_ORG_VAULT_DIR = '/tmp/some-org-vault'
    resetVaultRootCache()
    expect(vaultRoot()).toBe('/tmp/some-org-vault')
  })

  it('fail-closed: no vault → null, hasVault false, every path denied', () => {
    const bare = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vault-bare-')))
    process.env.CABINET_ROOT = bare // no vault/ or product-brain/ subdir
    resetVaultRootCache()
    expect(vaultRoot()).toBeNull()
    expect(hasVault()).toBe(false)
    expect(() => resolveInVault('anything.md')).toThrow(VaultPathError)
    expect(classifyPath('')).toBeNull()
  })
})

describe('buildBasenameIndex + resolveNoteTarget — confined wikilink resolution', () => {
  beforeEach(makeFixtureVault)

  it('indexes real notes by basename, skips symlinks/dotfiles', () => {
    const idx = buildBasenameIndex()
    expect(idx.get('n')).toEqual(['decisions/n.md'])
    expect(idx.get('alpha')).toEqual(['notes/alpha.md'])
    expect(idx.get('readme')).toEqual(['README.md'])
    // The escaping .md symlink is never indexed.
    expect(idx.get('leak')).toBeUndefined()
  })

  it('resolves a bare basename and a path target to confined relpaths', () => {
    const idx = buildBasenameIndex()
    expect(resolveNoteTarget('n', idx)).toBe('decisions/n.md')
    expect(resolveNoteTarget('decisions/n', idx)).toBe('decisions/n.md')
    expect(resolveNoteTarget('README.md', idx)).toBe('README.md')
  })

  it('returns null for a hostile / escaping / unknown target', () => {
    const idx = buildBasenameIndex()
    expect(resolveNoteTarget('../etc/passwd', idx)).toBeNull()
    expect(resolveNoteTarget('/etc/passwd', idx)).toBeNull()
    expect(resolveNoteTarget('leak', idx)).toBeNull() // symlink escape
    expect(resolveNoteTarget('does-not-exist', idx)).toBeNull()
  })
})

describe('buildBasenameIndex + resolveNoteTarget — title/slug addressing', () => {
  beforeEach(makeFixtureVault)

  it('resolves a wikilink by frontmatter TITLE to the exported filename', () => {
    const idx = buildBasenameIndex()
    // [[Product Overview]] must reach lib-2-product-overview.md — the exact
    // corpus mismatch that made 0/24 archive wikilinks resolve before the fix.
    expect(resolveNoteTarget('Product Overview', idx)).toBe(
      'library-archive/lib-2-product-overview.md'
    )
    expect(resolveNoteTarget('Decisions Index', idx)).toBe(
      'library-archive/lib-4-decisions-index.md'
    )
  })

  it('resolves the slug form and the raw exported basename too', () => {
    const idx = buildBasenameIndex()
    expect(resolveNoteTarget('product-overview', idx)).toBe(
      'library-archive/lib-2-product-overview.md'
    )
    expect(resolveNoteTarget('lib-2-product-overview', idx)).toBe(
      'library-archive/lib-2-product-overview.md'
    )
  })

  it('resolves a title-cased wikilink to an UNTITLED export via the stripped basename', () => {
    const idx = buildBasenameIndex()
    // lib-9-plain-note.md carries no frontmatter title; the stripped-basename
    // slug key ('plain-note') still resolves [[Plain Note]].
    expect(resolveNoteTarget('Plain Note', idx)).toBe(
      'library-archive/lib-9-plain-note.md'
    )
  })

  it('does not regress exact basename resolution (no key-space collision)', () => {
    const idx = buildBasenameIndex()
    expect(resolveNoteTarget('n', idx)).toBe('decisions/n.md')
    expect(resolveNoteTarget('README.md', idx)).toBe('README.md')
  })

  it('★ a hostile frontmatter TITLE cannot turn a wikilink into a path escape', () => {
    // Isolated vault so we do not perturb the shared fixture key space.
    const v = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vault-trap-')))
    const out = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vault-trapout-')))
    fs.writeFileSync(path.join(out, 'secret.txt'), 'SECRET')
    // A note whose DECLARED title is a traversal string.
    fs.writeFileSync(
      path.join(v, 'trap.md'),
      '---\ntitle: "../../secret.txt"\n---\nbody'
    )
    process.env.CABINET_ORG_VAULT_DIR = v
    resetVaultRootCache()
    resetBasenameIndexCache()

    const idx = buildBasenameIndex()
    const hit = resolveNoteTarget('../../secret.txt', idx)
    // The hostile title created an index KEY, but it maps to the confined
    // in-vault note — never the escaping path.
    expect(hit).toBe('trap.md')
    expect(hit).not.toContain('secret.txt')
    // And the resolved relpath re-confines cleanly under the vault root.
    expect(resolveInVault(hit as string).startsWith(v + path.sep)).toBe(true)
  })
})
