---
name: verify-pov
description: How to verify a candidate POV input using libCRS run-pov
---

# Verify POV

Test whether a candidate input crashes the harness. This runs inside the target environment (has JVM, ASAN, correct libraries).

## Basic Usage

```bash
# 1. Write candidate input to a file
python3 -c "import sys; sys.stdout.buffer.write(b'AAAA' * 50)" > /tmp/candidate.bin

# 2. Run against the harness (omit --rebuild-id to use the base build)
libCRS run-pov /tmp/candidate.bin /tmp/run_001 \
  --harness {harness}

# 3. Check result
cat /tmp/run_001/retcode
# non-zero = crash (valid POV)
# 0 = no crash
# 124 = timeout

# 4. Inspect crash details
cat /tmp/run_001/stderr.log   # ASAN output, stack traces
cat /tmp/run_001/stdout.log   # Program output, Java exceptions
```

## Multiple Candidates

Use different response directories for each candidate:

```bash
libCRS run-pov /tmp/candidate_1.bin /tmp/run_001 --harness {harness}
libCRS run-pov /tmp/candidate_2.bin /tmp/run_002 --harness {harness}

# Compare results
for d in /tmp/run_001 /tmp/run_002; do
  echo "=== $d ==="
  cat "$d/retcode"
  head -5 "$d/stderr.log"
done
```

## Crash Indicators by Language

**C/C++ (ASAN):** Non-zero exit code + `AddressSanitizer` / `SEGV` / `ABRT` in stderr.

**JVM (Jazzer):** Non-zero exit code (often 77) + `FuzzerSecurityIssueCritical` or `FuzzerSecurityIssueHigh` in stdout. Jazzer hooks detect dangerous API calls (command injection, SQL injection, path traversal, etc.).

## Notes

- Omitting `--rebuild-id` runs against the pre-built vulnerable target. Always use this for bug-finding.
- Use `--rebuild-id <id>` only when testing against a patched/instrumented build from `apply-patch-build`.
- Each run-pov call takes a few seconds (harness startup + execution).
- No limit on how many times you can call run-pov.
- **Do NOT run harness binaries directly** — the finder container lacks the target runtime.
