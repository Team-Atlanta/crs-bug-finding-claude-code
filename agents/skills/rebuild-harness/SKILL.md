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
libCRS apply-patch-build /tmp/debug.diff /tmp/build_001 --builder {builder}

# 4. Check build result
cat /tmp/build_001/build_exit_code
# 0 = success, non-zero = build failed

# If build failed, inspect logs:
cat /tmp/build_001/build_stderr.log
cat /tmp/build_001/build_stdout.log

# 5. Get the build ID (only exists if build succeeded)
cat /tmp/build_001/build_id

# 6. Run POV against the new build
libCRS run-pov /tmp/candidate.bin /tmp/run_debug \
  --harness {harness} --build-id $(cat /tmp/build_001/build_id) --builder {builder}

# 7. Check output (your debug prints will appear here)
cat /tmp/run_debug/pov_stdout.log
cat /tmp/run_debug/pov_stderr.log
```

## Example: Adding Debug Logging

```bash
# Add a debug print to trace which branch is taken
cd {source_dir}
# Edit the file...

git add -A
git diff --cached > /tmp/debug_trace.diff

# Build and test
libCRS apply-patch-build /tmp/debug_trace.diff /tmp/build_debug --builder {builder}
BUILD_ID=$(cat /tmp/build_debug/build_id)

libCRS run-pov /tmp/candidate.bin /tmp/run_debug \
  --harness {harness} --build-id $BUILD_ID --builder {builder}

# See your debug output
cat /tmp/run_debug/pov_stderr.log
```

## Notes

- Build IDs are content-addressed: same patch → same build ID (cached).
- Failed builds are NOT cached — you can fix and retry.
- Always reset source after debugging: `git checkout -- .`
- For final POV verification, use `--build-id base` (the original vulnerable build), not your debug build.
- Builds can be slow (recompiles the full project). Review your diff before building.
