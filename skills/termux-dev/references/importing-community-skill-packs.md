# Importing community skill packs into Hermes (verified 2026-08-25)

Community AI-skill repos on GitHub increasingly use the SAME convention as Hermes:
`skills/<kebab-name>/SKILL.md` with YAML frontmatter (`name`, `description`).
This means they can be installed directly by copying folders into
`~/.hermes/skills/<category>/<name>/`. Verified working with:

- addyosmani/agent-skills (⭐89K) — 24 engineering skills, all compatible
- K-Dense-AI/scientific-agent-skills (⭐34K) — 163 science skills, selective install
- nextlevelbuilder/ui-ux-pro-max-skill (⭐120K) — 7 design skills + large data dirs

## Workflow

1. Shallow clone to a temp dir:
   `git clone --depth 1 https://github.com/<org>/<repo>.git ~/tmp/sk/<repo>`
2. Enumerate skill folders (find paths containing `SKILL.md`). Some repos keep them
   under `skills/`, some under `.claude/skills/` (Claude-format, same frontmatter).
3. Copy chosen folders into the right Hermes category:
   - Engineering skills → `software-development/`
   - Science/data-viz → `mlops/` or `research/`
   - Design/UI → `creative/`
4. **Prefix names to avoid collisions** when a folder name is generic:
   e.g. copy `.claude/skills/design` → `~/.hermes/skills/creative/uiux-design`.
5. Verify: count SKILL.md files under ~/.hermes/skills and spot-check that each new
   folder contains its SKILL.md.
6. Clean up the temp clone.

## Selective install for giant repos

K-Dense has 163 skills, most needing niche bioinformatics libraries. Don't bulk-copy;
pick a whitelist of broadly useful ones and resolve near-miss names manually
(e.g. wanted `matplotlib-visualization`, actual folder was `matplotlib`).

Large repos ship real data assets too (ui-ux-pro-max: 79 style profiles, 192 palettes,
74 font pairings across 250+ files) — these survive copytree and are what make the
skills actually good; check file counts per skill after install.

## Collision policy

Hermes bundled/hub skills live in their own categories. Community copies go under an
existing category with a distinguishing prefix (`uiux-`, `sci-`) so a future
curator consolidation can tell provenance.

## Result reference

2026-08-25 import session: 89 → 128 total skills (+23 engineering, +9 science,
+7 design), zero conflicts, all verified present on disk afterwards.
