# Unreal MCP

> **Status (2026-11-07):** Frozen vendored copy, and it doesn't start as configured. This folder
> arrived in `9d133d6` (2026-07-03) and hasn't changed since. Everything below this note is unedited
> upstream text. **The upstream source and licence are unknown:** the commit doesn't name them, the
> plugin's `UnrealMCP.uplugin` still says "Your Name", and the repo has no licence file. Settle that
> before any public release.
>
> What is actually true here:
>
> - **Engine version:** UE 5.8, not 5.5. The plugin in `unreal/plugin-UnrealMCP/` was patched for
>   5.8 in the same commit.
> - **How it connects:** the server speaks MCP (Model Context Protocol) over stdio and reaches the
>   editor over TCP at `127.0.0.1:55557`, through the C++ bridge in
>   `unreal/plugin-UnrealMCP/Source/UnrealMCP/Private/UnrealMCPBridge.cpp`. There is no HTTP API and
>   no `UnrealMCPBridge.py`, so the Development section below is wrong. Tools live in `tools/`.
> - **How it's registered:** the repo's `.mcp.json` starts this server with bare `python` and an
>   absolute Windows path. The "Configuring your MCP Client" section linked below doesn't exist.
> - **Why it fails:** neither the system Python nor the repo's `.venv` has the `mcp` package, and
>   this folder has no virtualenv of its own, so the server errors when a session starts.
>
> The Unreal client this served is frozen too. See [docs/unreal-port.md](../../docs/unreal-port.md)
> and [docs/project-status.md](../../docs/project-status.md).

Python bridge for interacting with Unreal Engine 5.5 using the Model Context Protocol (MCP).

## Setup

1. Make sure Python 3.10+ is installed
2. Install `uv` if you haven't already:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Create and activate a virtual environment:
   ```bash
   uv venv
   source .venv/bin/activate  # On Unix/macOS
   # or
   .venv\Scripts\activate     # On Windows
   ```
4. Install dependencies:
   ```bash
   uv pip install -e .
   ```

At this point, you can configure your MCP Client (Claude Desktop, Cursor, Windsurf) to use the Unreal MCP Server as per the [Configuring your MCP Client](README.md#configuring-your-mcp-client).

## Testing Scripts

There are several scripts in the [scripts](./scripts) folder. They are useful for testing the tools and the Unreal Bridge via a direct connection. This means that you do not need to have an MCP Server running.

You should make sure you have installed dependencies and/or are running in the `uv` virtual environment in order for the scripts to work.


## Troubleshooting

- Make sure Unreal Engine editor is loaded loaded and running before running the server.
- Check logs in `unreal_mcp.log` for detailed error information

## Development

To add new tools, modify the `UnrealMCPBridge.py` file to add new command handlers, and update the `unreal_mcp_server.py` file to expose them through the HTTP API. 