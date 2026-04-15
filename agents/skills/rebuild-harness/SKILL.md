---
name: rebuild-harness
description: How to rebuild the harness with source modifications using libCRS apply-patch-build
---

# Rebuild Harness

Rebuild the harness after modifying source code (e.g., adding debug logs, instrumentation, or testing a hypothesis). Uses the builder sidecar to compile inside the target environment.

## When to Use

- Adding `printf`/`fprintf(stderr, ...)` to trace execution paths
- Adding assertions to test hypotheses about vulnerable code
- Modifying the harness to reach different code paths
- Instrumenting code to understand input parsing

## Workflow

```bash
# 1. Edit source files in {source_dir}
#    (the source is a git repo — use git diff to generate patches)

# 2. Generate a patch
cd {source_dir}
git add -A
git diff --cached > /tmp/debug.diff

# 3. Build with the patch applied
libCRS apply-patch-build /tmp/debug.diff /tmp/build_001

# 4. Check build result
cat /tmp/build_001/retcode
# 0 = success, non-zero = build failed

# If build failed, inspect logs:
cat /tmp/build_001/stderr.log
cat /tmp/build_001/stdout.log

# 5. Get the rebuild ID (only exists if build succeeded)
cat /tmp/build_001/rebuild_id

# 6. Run POV against the new build
libCRS run-pov /tmp/candidate.bin /tmp/run_debug \
  --harness {harness} --rebuild-id $(cat /tmp/build_001/rebuild_id)

# 7. Check output (your debug prints will appear here)
cat /tmp/run_debug/stdout.log
cat /tmp/run_debug/stderr.log
```

## Example: Adding Debug Logging

```bash
# Add a debug print to trace which branch is taken
cd {source_dir}
# Edit the file...

git add -A
git diff --cached > /tmp/debug_trace.diff

# Build and test
libCRS apply-patch-build /tmp/debug_trace.diff /tmp/build_debug
REBUILD_ID=$(cat /tmp/build_debug/rebuild_id)

libCRS run-pov /tmp/candidate.bin /tmp/run_debug \
  --harness {harness} --rebuild-id $REBUILD_ID

# See your debug output
cat /tmp/run_debug/stderr.log
```

## Notes

- Rebuild IDs are content-addressed: same patch → same rebuild ID (cached).
- Failed builds are NOT cached — you can fix and retry.
- Always reset source after debugging: `git checkout -- .`
- For final POV verification, omit `--rebuild-id` (runs against the original vulnerable build), not your debug build.
- Builds can be slow (recompiles the full project). Review your diff before building.
