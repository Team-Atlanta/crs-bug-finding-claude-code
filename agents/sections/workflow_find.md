## Workflow

1. **Analyze** — Read source code, diff (if available), and harness to understand attack surface. Identify functions with potential vulnerabilities.
2. **Craft** — Write candidate inputs that exercise vulnerable code paths. Use knowledge of the input format and parsing logic.
3. **Verify** — Test each candidate with `libCRS run-pov`. Check `retcode` (non-zero = crash). Inspect `stdout.log` / `stderr.log` for crash details.
4. **Save** — Write verified crashing inputs to the POV directory. Use descriptive filenames.
5. **Repeat** — Look for more vulnerabilities. Different code paths, different bug classes, different input structures.
