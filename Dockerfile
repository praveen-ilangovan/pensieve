# Container image for the Pensieve MCP server.
#
# Pensieve speaks the Model Context Protocol over stdio. This image installs the
# package and launches `pensieve-mcp`, which is enough for registries (e.g. Glama)
# to start the server and issue an MCP introspection (tools/list) request.
#
# The memory store lives at $HOME/.pensieve and is created/migrated on first use;
# introspection does not touch it, so no volume is required just to list tools.
FROM python:3.12-slim

WORKDIR /app

# Install the package and its dependencies (build backend: poetry-core).
COPY . /app
RUN pip install --no-cache-dir .

# The MCP server communicates over stdio.
ENTRYPOINT ["pensieve-mcp"]
