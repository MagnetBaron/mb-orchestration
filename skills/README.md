# Selective mobile skill tree

`registry.json` is the routing source for the locally installed iOS,
Flutter, and Dart skills. `sync.py` links the installed copies into both the
user-level universal skill directory and this repository's `.agents/skills`
directory. It also generates Codex configuration with these boundaries:

| Route | Skill availability | Loading behavior |
|---|---|---|
| Dispatch | none | all 24 mobile skills disabled |
| Default/non-mobile agents | none | inherit Dispatch's disabled set |
| Existing implementation seat on a mobile brief | only the names in the brief's `skills:` field | explicit; each named `SKILL.md` is added to `must_read` |
| `mb-mobile-accessibility-reviewer` | `ios-accessibility` only | progressive and read-only |

Run `python3 skills/sync.py` after installing or updating the source skills.
Run `python3 skills/sync.py --check` to verify installed files, symlink targets,
and generated Codex configuration without changing anything.

The repository records the upstream commit used for each source. Updating a
skill is a deliberate registry revision, not an untracked pull from `main`.

Dispatch selects skill names from the installed skill frontmatter (name and
description only). It does not read full skill bodies. A mobile brief must name
only the skills that match the work and add those exact `SKILL.md` paths to
`must_read`; `skills: []` is correct when none of these focused workflows
applies. This is a role loaded inside an existing seat, never a new Codex or
implementation seat.
