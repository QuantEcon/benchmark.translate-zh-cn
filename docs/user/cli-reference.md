# CLI Reference

All commands available in `qebench`.

## `qebench stats`

Show dataset coverage, domain breakdown, and progress toward targets.

```bash
uv run qebench stats
```

**Output includes:**
- Progress bars for terms, sentences, and paragraphs vs. targets
- Domain breakdown table with entry counts
- Total entries summary

No options — always shows the full dataset overview.

---

## `qebench translate`

Interactive translation practice. Presents English text, collects your Chinese translation, then reveals the reference and scores your attempt.

```bash
uv run qebench translate [OPTIONS]
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--count` | `-n` | `5` | Number of entries per session |
| `--domain` | `-d` | all | Filter by domain (e.g. `economics`) |
| `--difficulty` | | all | Filter: `basic`, `intermediate`, or `advanced` |
| `--user` | `-u` | `anonymous` | Your username for XP tracking |

**Examples:**

```bash
# Quick 3-term session on economics
uv run qebench translate -n 3 -d economics

# Practice advanced terms as "alice"
uv run qebench translate --difficulty advanced -u alice

# Default session (5 random entries)
uv run qebench translate
```

**Scoring:**
- **★ Exact match** — your translation matches the reference or an accepted alternative
- **◉ Close** — ≥70% character overlap
- **○ Partial** — ≥40% character overlap
- **△ Keep practicing** — <40% character overlap

Each completed entry earns **10 XP**.

---

## `qebench add`

Contribute new terms, sentences, or paragraphs to the dataset through interactive prompts.

```bash
uv run qebench add
```

No options — the command walks you through the process:

1. **Choose entry type** — term, sentence, or paragraph
2. **Fill in fields** — English text, Chinese translation, domain, difficulty, etc.
3. **Preview** — see a summary before saving
4. **Confirm** — save to the appropriate domain JSON file
5. **Continue?** — option to add another entry

Each contributed entry earns **15 XP**.

---

## XP System

Actions earn experience points tracked per user:

| Action | XP per item |
|---|---|
| Translate an entry | 10 |
| Add a new entry | 15 |
| Judge a comparison | 5 |

XP is stored in `results/xp/{username}.json` and shown at the end of each session.
