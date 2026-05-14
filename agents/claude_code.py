"""
Claude Code agent for autonomous vulnerability discovery.

Implements the agent interface (setup / run) using Claude Code CLI
in agentic mode. Claude Code reads CLAUDE.md for workflow instructions,
then autonomously: analyzes source -> identifies vulnerabilities ->
crafts inputs -> verifies crashes -> writes POVs to pov_dir/.
"""

import json
import logging
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger("agent.claude_code")


# 0 = no timeout (run until budget is exhausted)
try:
    AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "0"))
except ValueError:
    AGENT_TIMEOUT = 0
if AGENT_TIMEOUT < 0:
    AGENT_TIMEOUT = 0

_TEMPLATE_PATH = Path(__file__).with_suffix(".md")
_SECTIONS_DIR = _TEMPLATE_PATH.with_name("sections")
_SKILLS_DIR = _TEMPLATE_PATH.with_name("skills")


def _load_section(section_name: str) -> str:
    section_path = _SECTIONS_DIR / section_name
    return section_path.read_text()


def _load_prompt_templates() -> dict[str, str]:
    return {
        "agents_md": _TEMPLATE_PATH.read_text(),
        "workflow_find": _load_section("workflow_find.md"),
        "diff_present": _load_section("diff_present.md"),
        "diff_absent": _load_section("diff_absent.md"),
        "seeds_present": _load_section("seeds_present.md"),
        "pre_submit": _load_section("pre_submit.md"),
    }


def _md_inline(value: str) -> str:
    """Return a markdown-safe inline code span."""
    ticks = 1
    while "`" * ticks in value:
        ticks += 1
    fence = "`" * ticks
    return f"{fence}{value}{fence}"


def _list_input_files(input_dir: Path, *, non_empty_only: bool = False) -> list[Path]:
    if not input_dir.exists():
        return []
    files = sorted(f for f in input_dir.rglob("*") if f.is_file() and not f.name.startswith("."))
    if not non_empty_only:
        return files
    return [f for f in files if f.read_text(errors="replace").strip()]


def _install_skills(source_dir: Path, harness: str) -> None:
    """Copy skills from package data into source_dir/.claude/skills/, filling placeholders."""
    target_skills = source_dir / ".claude" / "skills"
    if not _SKILLS_DIR.exists():
        logger.warning("Skills directory not found: %s", _SKILLS_DIR)
        return

    for skill_dir in _SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        dest = target_skills / skill_dir.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
        # Fill {harness}, {source_dir} placeholders in SKILL.md
        skill_md = dest / "SKILL.md"
        if skill_md.exists():
            content = skill_md.read_text()
            content = content.replace("{harness}", harness)
            content = content.replace("{source_dir}", str(source_dir))
            skill_md.write_text(content)
        logger.info("Installed skill: %s", skill_dir.name)


def setup(source_dir: Path, config: dict) -> None:
    """One-time agent configuration.

    - Sets Claude-specific env vars (ANTHROPIC_BASE_URL, AUTH_TOKEN, IS_SANDBOX)
    - Writes .claude.json config
    - Writes global gitignore so CLAUDE.md never leaks into diffs
    """
    try:
        version_result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        logger.info(
            "Claude Code CLI version: %s",
            version_result.stdout.strip() or version_result.stderr.strip(),
        )
    except OSError as error:
        logger.warning("Failed to get Claude Code version: %s", error)

    llm_api_url = config.get("llm_api_url", "")
    llm_api_key = config.get("llm_api_key", "")

    os.environ["IS_SANDBOX"] = "1"

    if llm_api_url and llm_api_key:
        os.environ["ANTHROPIC_BASE_URL"] = llm_api_url
        os.environ["ANTHROPIC_AUTH_TOKEN"] = llm_api_key
        os.environ["ANTHROPIC_API_KEY"] = ""
        logger.info("Claude Code configured with LiteLLM proxy: %s", llm_api_url)
        logger.info("ANTHROPIC_MODEL: %s", os.environ.get("ANTHROPIC_MODEL", "(default)"))
        logger.info("CLAUDE_CODE_SUBAGENT_MODEL: %s", os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL", "(default)"))
        logger.info("ANTHROPIC_DEFAULT_OPUS_MODEL: %s", os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "(default)"))
        logger.info("ANTHROPIC_DEFAULT_SONNET_MODEL: %s", os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "(default)"))
        logger.info("ANTHROPIC_DEFAULT_HAIKU_MODEL: %s", os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "(default)"))
    else:
        logger.warning("No LLM API URL/key set, Claude Code may not work")

    # Write Claude JSON config
    claude_config = {
        "numStartups": 0,
        "autoUpdaterStatus": "disabled",
        "userID": "-",
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "1.0.0",
        "projects": {
            str(source_dir): {
                "hasTrustDialogAccepted": True,
                "hasCompletedProjectOnboarding": True,
            }
        },
    }
    claude_json = Path.home() / ".claude.json"
    claude_json.write_text(json.dumps(claude_config))
    claude_json.chmod(0o600)
    logger.info("Wrote Claude config to %s", claude_json)

    # Global gitignore so runtime instructions never leak into diffs
    global_gitignore = Path.home() / ".gitignore"
    existing = ""
    if global_gitignore.exists():
        existing = global_gitignore.read_text(errors="replace")
    lines = [line.rstrip("\n") for line in existing.splitlines()]
    if "CLAUDE.md" not in lines:
        lines.append("CLAUDE.md")
    global_gitignore.write_text("\n".join(lines).rstrip("\n") + "\n")
    git_cfg = subprocess.run(
        ["git", "config", "--global", "core.excludesFile", str(global_gitignore)],
        capture_output=True,
    )
    if git_cfg.returncode != 0:
        logger.warning(
            "Failed to set global git excludesFile: %s",
            git_cfg.stderr.decode(errors="replace") if isinstance(git_cfg.stderr, bytes) else git_cfg.stderr,
        )

    logger.info("Agent setup complete")


def run(
    source_dir: Path,
    build_dir: Path,
    pov_dir: Path,
    diff_dir: Path,
    seed_dir: Path,
    bug_candidate_dir: Path,
    harness: str,
    work_dir: Path,
    *,
    language: str = "c",
    sanitizer: str = "address",
) -> bool:
    """Launch Claude Code in agentic mode to autonomously find vulnerabilities.

    The agent analyzes the source code and crafts inputs that trigger crashes
    via libCRS run-pov. Verified POVs are written to pov_dir/ where the
    libCRS daemon auto-submits them.

    Returns True if the agent completed without error.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        templates = _load_prompt_templates()
    except OSError as e:
        logger.error("Failed to load prompt template(s): %s", e)
        return False

    _install_skills(source_dir, harness)

    diffs = _list_input_files(diff_dir, non_empty_only=True)
    seeds = _list_input_files(seed_dir)
    bug_candidates = _list_input_files(bug_candidate_dir)

    # Build diff section
    if diffs:
        diff_list = "\n".join(f"- {_md_inline(str(p))}" for p in diffs)
        diff_section = templates["diff_present"].format(diff_list=diff_list)
    else:
        diff_section = templates["diff_absent"]

    # Build seeds section
    if seeds:
        seed_section = templates["seeds_present"].format(seed_dir=_md_inline(str(seed_dir)))
    else:
        seed_section = ""

    # Build bug-candidate section
    if bug_candidates:
        bc_list = "\n".join(f"- {_md_inline(str(p))}" for p in bug_candidates)
        bug_candidate_section = (
            "## Bug-Candidate Reports\n\n"
            "Static analysis reports are available:\n\n"
            f"{bc_list}\n\n"
            "Use these to prioritize which code paths to target.\n"
        )
    else:
        bug_candidate_section = ""

    pre_submit_section = templates["pre_submit"]

    claude_md = templates["agents_md"].format(
        language=language,
        sanitizer=sanitizer,
        source_dir=source_dir,
        build_dir=build_dir,
        work_dir=work_dir,
        harness=harness,
        pov_dir=pov_dir,
        workflow_section=templates["workflow_find"],
        diff_section=diff_section,
        seed_section=seed_section,
        bug_candidate_section=bug_candidate_section,
        pre_submit_section=pre_submit_section,
    )
    (source_dir / "CLAUDE.md").write_text(claude_md)

    target = os.environ.get("OSS_CRS_TARGET", source_dir.name)

    prompt_lines = [
        f"Find vulnerabilities in project {_md_inline(target)} through harness {_md_inline(harness)}.",
        f"Write crashing inputs (POVs) to {_md_inline(str(pov_dir))}.",
        "",
        "Available evidence:",
        f"- Diff files: {len(diffs)}",
        f"- Seed files: {len(seeds)}",
        f"- Bug-candidate files: {len(bug_candidates)}",
    ]
    if diffs:
        diff_files = " ".join(_md_inline(str(p)) for p in diffs)
        prompt_lines.append(f"- Diff files: {diff_files}")
    if seeds:
        prompt_lines.append(f"- Seed directory: {_md_inline(str(seed_dir))}")
    if bug_candidates:
        bug_files = " ".join(_md_inline(str(p)) for p in bug_candidates)
        prompt_lines.append(f"- Bug-candidate report files: {bug_files}")
    prompt_lines.extend([
        "",
        "Read CLAUDE.md for workflow, environment, and submission instructions.",
        "Keep going until killed — find as many distinct vulnerabilities as possible.",
    ])
    prompt = "\n".join(prompt_lines)

    stdout_log = work_dir / "claude_stdout.log"
    stderr_log = work_dir / "claude_stderr.log"

    system_prompt = (
        f"You are an expert security researcher finding {sanitizer} vulnerabilities in `{target}` ({language}). "
        "Read and follow CLAUDE.md."
    )

    cmd = [
        "claude",
        "-p",
        "--verbose",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--append-system-prompt", system_prompt,
    ]

    # Save agent inputs for debugging/inspection
    (work_dir / "agent_prompt.txt").write_text(prompt)
    (work_dir / "agent_system_prompt.txt").write_text(system_prompt)
    (work_dir / "agent_claude_md.md").write_text(claude_md)
    (work_dir / "agent_cmd.txt").write_text(" ".join(cmd) + "\n")
    logger.info("Agent inputs saved to %s", work_dir)

    try:
        with open(stdout_log, "w") as out_f, open(stderr_log, "w") as err_f:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=out_f,
                stderr=err_f,
                text=True,
                cwd=source_dir,
                start_new_session=True,
            )
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
                proc.wait(timeout=AGENT_TIMEOUT or None)
                logger.info("Claude Code exit code: %d", proc.returncode)
            except subprocess.TimeoutExpired:
                logger.warning("Claude Code timed out (%ds), killing process tree", AGENT_TIMEOUT)
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    time.sleep(2)
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
    except Exception as e:
        logger.error("Error running Claude Code: %s", e)
        return False

    subprocess.run(
        ["chmod", "-R", "og+rX", str(Path.home() / ".claude")],
        capture_output=True,
    )

    if proc.returncode != 0:
        logger.warning("Claude Code failed (rc=%d), see %s", proc.returncode, stderr_log)

    # Check if any POVs were produced
    pov_files = list(pov_dir.glob("*")) if pov_dir.exists() else []
    pov_files = [f for f in pov_files if f.is_file() and not f.name.startswith(".")]
    if pov_files:
        logger.info("Agent produced %d POV(s): %s", len(pov_files), [f.name for f in pov_files])
        return True

    logger.info("Agent did not produce any POVs")
    return False
