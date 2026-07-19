# Install From GitHub

This is the recommended install path for Blender users who want Blender Agent Bridge to update cleanly from GitHub.

Blender Agent Bridge does not host an LLM provider inside Blender. Install the extension in Blender, start the local bridge, then connect from an external MCP-capable client such as Codex, Claude Desktop, Claude Code, Cursor, or another agent host.

## Recommended: Remote Extension Repository

Use this URL as the Blender remote extension repository:

```text
https://callmejones.github.io/blender-agent-bridge/index.json
```

In Blender:

1. Install Blender `4.2.0` or newer.
2. Open `Edit > Preferences > Get Extensions`.
3. Enable online access if Blender asks for it.
4. Add a remote repository named `Blender Agent Bridge`.
5. Paste the repository URL above.
6. Sync the repository.
7. Search for `Blender Agent Bridge`.
8. Install and enable the extension.
9. Open the 3D View sidebar, find `Agent Bridge`, then press `Start Bridge`.
10. Press `Copy MCP` and paste the generated config into your external MCP client.

To update later, sync the same repository and use Blender's extension update flow.

## Manual Fallback: GitHub Release ZIP

If you do not want to add a remote repository:

1. Open the latest release:
   <https://github.com/CallMeJones/blender-agent-bridge/releases/latest>
2. Download the release asset named `claude_blender-<version>.zip`.
3. Download the matching `.zip.sha256` file if you want to verify the checksum.
4. In Blender, open `Edit > Preferences > Get Extensions`.
5. Use `Install from Disk` and choose the downloaded ZIP.
6. Enable `Blender Agent Bridge`.

Do not install GitHub's generated `Source code` ZIP. It is the repository checkout, not the packaged Blender extension.

On Windows, verify a downloaded ZIP with:

```powershell
Get-FileHash .\claude_blender-<version>.zip -Algorithm SHA256
Get-Content .\claude_blender-<version>.zip.sha256
```

The hash printed by `Get-FileHash` should match the first value in the `.sha256` file.

## Confirm The Install

After enabling the extension:

1. Open the 3D View sidebar.
2. Find the `Agent Bridge` panel.
3. Confirm the panel shows the add-on, bridge, MCP, and config versions.
4. Press `Start Bridge`.
5. Press `Copy MCP`.
6. Paste the generated config into your external MCP client.
7. Restart or refresh the MCP client so stale tool caches are cleared.

Once connected, `guardrail_warnings` in catalog, schema, or tool results are expected advisory hints. They steer clients toward async external asset jobs, queued imports, background render/MP4 polling, user-confirmed paths, and Blender approval/preview controls without requiring extra prompts.

Useful smoke prompt once connected:

```text
List the objects in the current Blender scene, then tell me which Blender Agent Bridge tools are available for animation.
```

For animation routing, test with script trust off:

```text
Make the selected cube bounce twice and get smaller each bounce. Check it against the brief and leave it as a preview.
```

The client should use `run_animation_task` or the animation workflow tools before considering `draft_script`.

For external asset routing, test the async job path:

```text
Search Poly Haven for a sunset HDRI, cache it as an external asset job, poll until it is ready, then queue the import into the world as a preview.
```

## Troubleshooting

- If Blender cannot sync the repository, confirm online access is enabled and the URL ends in `/index.json`.
- If the extension does not appear, open the URL in a browser and confirm the generated page loads.
- If your MCP client still shows old tools, replace the copied MCP config and restart or refresh the client.
- If manual ZIP install fails, confirm you downloaded `claude_blender-<version>.zip` from release assets, not GitHub's source-code ZIP.
- If the bridge starts but the client cannot connect, confirm Blender is still open, the bridge panel says `Bridge: On`, and no local firewall rule is blocking `127.0.0.1`.

## Maintainer Release Flow

Local release build:

```powershell
$Version = python -c "import tomllib; print(tomllib.load(open('addon/claude_blender/blender_manifest.toml','rb'))['version'])"
blender --command extension validate addon\claude_blender
python scripts\build_extension_zip.py --blender blender
blender --command extension validate "dist\claude_blender-$Version.zip"
python tests\smoke_release_consistency.py
python tests\smoke_build_extension_zip.py
python tests\smoke_extension_repository.py
python scripts\build_extension_repository.py --zip-path "dist\claude_blender-$Version.zip" --repo-dir public
python tests\smoke_release_artifact_identity.py
```

Publish a tagged GitHub release:

```powershell
$Version = python -c "import tomllib; print(tomllib.load(open('addon/claude_blender/blender_manifest.toml','rb'))['version'])"
git tag -a "v$Version" -m "Blender Agent Bridge $Version"
git push origin "v$Version"
```

The GitHub workflow runs the complete Blender suite and clean installed-extension smoke for `v*` tags. After those gates pass, it publishes one official ZIP and `.sha256` to the GitHub Release and builds the Pages repository from that exact archive, then downloads both public copies to verify byte identity. Ordinary `main` pushes do not change the public Pages package.

Clean CLI install smoke with a temporary Blender profile:

```powershell
$profile = Join-Path $env:TEMP "bab-clean-profile"
$env:BLENDER_USER_CONFIG = Join-Path $profile "config"
$env:BLENDER_USER_SCRIPTS = Join-Path $profile "scripts"
$env:BLENDER_USER_CACHE = Join-Path $profile "cache"
$env:BLENDER_USER_EXTENSIONS = Join-Path $profile "extensions"
New-Item -ItemType Directory -Force -Path $env:BLENDER_USER_CONFIG,$env:BLENDER_USER_SCRIPTS,$env:BLENDER_USER_CACHE,$env:BLENDER_USER_EXTENSIONS
blender --online-mode --command extension repo-add blender_agent_bridge --name "Blender Agent Bridge" --directory "$env:BLENDER_USER_EXTENSIONS" --url "https://callmejones.github.io/blender-agent-bridge/index.json" --clear-all
blender --online-mode --command extension sync
blender --online-mode --command extension install -s -e claude_blender
blender --online-mode --command extension list -s
```
