# =============================================================================
# crs-bug-finding-claude-code Finder Module
# =============================================================================
# RUN phase: Analyzes source code and crafts POV inputs using Claude Code.
#
# Uses pre-built ASAN harness from the build phase — no builder sidecar needed.
# =============================================================================

# These ARGs are required by the oss-crs framework template
ARG target_base_image
ARG crs_version

FROM claude-code-bug-finding-base:cli-2.0.17

# Install libCRS (CLI + Python package)
COPY --from=libcrs . /libCRS
RUN pip3 install /libCRS \
    && python3 -c "from libCRS.base import DataType; print('libCRS OK')"

# Install crs-bug-finding-claude-code package (finder + agents)
COPY pyproject.toml /opt/crs-bug-finding-claude-code/pyproject.toml
COPY finder.py /opt/crs-bug-finding-claude-code/finder.py
COPY agents/ /opt/crs-bug-finding-claude-code/agents/
RUN pip3 install /opt/crs-bug-finding-claude-code

CMD ["run_finder"]
