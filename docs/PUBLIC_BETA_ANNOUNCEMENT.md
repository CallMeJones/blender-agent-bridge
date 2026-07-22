# Blender Agent Bridge v0.3.1: Public Open-Source Beta

Today I’m opening **Blender Agent Bridge** to the public as an open-source beta.

Blender Agent Bridge connects Blender to external AI agents through the Model Context Protocol (MCP). It lets tools such as Codex, Claude Desktop, Claude Code, Cursor, and other MCP-capable clients inspect an open Blender scene, gather visual evidence, use structured editing tools, and help with longer animation and rendering workflows—while keeping Blender, and the artist, in control.

![Two aircraft in a Blender dogfight scene created and reviewed while testing Blender Agent Bridge](https://raw.githubusercontent.com/CallMeJones/blender-agent-bridge/v0.3.1/docs/assets/egypt-dogfight-hero.jpg)

This beta is for Blender artists, technical artists, animators, developers, and curious builders who want to explore what agent-assisted 3D work can look like without placing a hidden chat system or a provider API key inside Blender.

## Why I Built It

The project started while I was helping my girlfriend, who is an animator, through some very tight deadlines. We tried other AI tools, and some of them produced helpful videos or useful starting points. The problem came when she needed to make a small, precise change. A generated video could not give her the control she had inside Blender, and it did not come with the raw models, animation data, scene setup, or editable project files needed to continue the work properly.

That experience changed the question for me. Instead of asking, “Can AI generate something that looks finished?”, I started asking, “Can AI work inside an artist’s real production process while leaving the artist in control of every useful part?” Blender Agent Bridge grew from that question.

AI agents are becoming good at planning, using tools, and iterating on complex tasks. Blender, however, is not a text editor. A small instruction can affect hundreds of objects, frames, materials, files, or render settings. Useful AI integration therefore needs more than arbitrary Python execution: it needs scene awareness, visual feedback, clear boundaries, and a way to undo or reject changes.

Blender Agent Bridge separates those responsibilities:

- **Blender remains the execution layer.** It owns the scene, files, previews, approvals, checkpoints, visual captures, and local resources.
- **Your existing AI client remains the agent host.** It owns the conversation, model connection, planning, and memory.
- **Structured tools come first.** The bridge exposes bounded helpers for common Blender operations instead of defaulting to generated code.
- **You remain the decision-maker.** Helper edits appear as live previews that can be committed, reverted, or undone. Generated Python is staged for review unless you explicitly grant temporary session trust.

The bridge is local-first: its Blender connection binds to localhost, and Blender Agent Bridge does not store model-provider credentials.

## What Can It Do?

The v0.3.1 beta includes a canonical registry of 189 tool contracts covering scene inspection, editing, animation, rendering, project health, bounded project-directory files, and external asset workflows.

An agent can, among other things:

- inspect objects, selections, materials, lights, cameras, rigs, animation data, render settings, compositor nodes, Geometry Nodes, collections, shape keys, curves, and scene health;
- capture viewport images, sampled playblast frames, inspection renders, and render thumbnails so it can evaluate visual results instead of relying only on scene metadata;
- apply reversible helper edits for transforms, materials, lighting, cameras, primitives, keyframes, constraints, render settings, scene organization, procedural object kits, and directed animation shots;
- plan and run animation workflows, compare playblasts with a brief, propose repairs, and iterate with visible evidence;
- start longer renders in a background Blender process, report progress, assemble image sequences into MP4 files, and validate the result;
- search Poly Haven and Sketchfab, cache assets through asynchronous jobs, and queue imports with source and license information;
- inspect `.blend` file health, autosave an already-saved project, and request user-confirmed paths for opening or creating project files; and
- stage custom Blender Python in a visible Text datablock for approval when a task falls outside the structured helper set.

One of the test projects was an Egypt dogfight sequence. The agent inspected the scene, captured playblasts and renders, repaired visual problems, managed longer render jobs, and checked the output through the bridge.

![Short playblast-style preview from the Egypt dogfight test project](https://raw.githubusercontent.com/CallMeJones/blender-agent-bridge/v0.3.1/docs/assets/egypt-dogfight-preview.gif)

## Safety Is Part of the Workflow

I do not want “AI for Blender” to mean giving an agent silent, unrestricted control over a production file.

Blender Agent Bridge uses several layers of friction where they matter:

- Safe helper edits become visible preview transactions with **Commit**, **Revert**, and Blender undo support.
- Generated Python uses a binary runtime switch: trust off refuses it; **Trust Agent Scripts** runs ordinary static-check-passing scripts for the current Blender session. Privileged generated scripts remain disabled.
- Scripts involving custom external assets or project-file operations require a declared capability manifest and fresh approval.
- Save-as, open, and new-project operations require a path confirmed by the user.
- Tool calls produce local, redacted audit events.
- External asset downloads use bounded background jobs and hardened URL, redirect, archive, and cache handling.
- A compatibility handshake prevents mismatched add-on and MCP runtimes from silently working against different tool registries.

These controls reduce risk, but they do not turn generated Python into a security sandbox. During the beta, use copies or version control for important projects, enable script trust only for agents you trust, and keep backups of valuable `.blend` files.

## Provider-Neutral and Client-Friendly

The project began under the name “Claude for Blender,” which is why some internal identifiers still use `claude_blender` for compatibility. The public project is now **Blender Agent Bridge** because it is not tied to one model provider.

It can work with Codex, Claude, Cursor, VS Code-based MCP hosts, ChatGPT-compatible MCP setups, Gemini CLI, OpenCode, Ollama-based hosts, and other clients that can run a local MCP server. Client-specific setup guides are included in the repository.

The extension includes a bundled MCP runtime for the simplest installation. Advanced users can instead run the exact matching `blender-bridge` package from PyPI with `uvx`. Both modes expose the same contracts and perform the same compatibility check.

## Install the Public Beta

Blender Agent Bridge supports Blender 4.2 or newer and is continuously tested against Blender 4.2 LTS, 4.5 LTS, and 5.1.

The recommended installation path is Blender’s extension repository:

1. In Blender, open **Edit → Preferences → Get Extensions**.
2. Add this remote repository:

   ```text
   https://callmejones.github.io/blender-agent-bridge/index.json
   ```

3. Sync the repository, search for **Blender Agent Bridge**, and install it.
4. Open the 3D View sidebar, select **Agent Bridge**, and press **Start**.
5. Press **Copy MCP Config**, paste the generated configuration into your AI client, and restart or refresh that client.

You can also download the packaged extension ZIP from the [v0.3.1 GitHub Release](https://github.com/CallMeJones/blender-agent-bridge/releases/tag/v0.3.1). Do not use GitHub’s automatically generated “Source code” ZIP as the Blender extension.

Once connected, try:

> List the objects in the current Blender scene and tell me which Blender Agent Bridge tools are available.

Then select an object and try a reversible edit:

> Move the selected object up one Blender unit, give it a red material, and leave the change as a preview.

## Why Call It a Beta?

The bridge already has substantial automated coverage, including tagged-release tests against multiple Blender versions, installed-extension checks, package tests, and public artifact verification. I am still calling it a beta because real artists will find workflows and failure modes that a test suite cannot.

During the beta, you should expect:

- some client-specific setup rough edges;
- tool descriptions and workflows to improve as real usage patterns emerge;
- large or unusual Blender projects to expose performance and compatibility issues;
- external asset services to have their own availability, authentication, and licensing constraints; and
- the latest tagged release to be the supported version while older beta releases move out of support.

That is exactly why I am releasing it openly now: I want the next stage to be shaped by real scenes, real artists, and transparent technical feedback.

## How to Help

The project is licensed under **GPL-3.0-or-later**, and contributions are welcome.

The most helpful beta feedback includes:

- your Blender version, operating system, and AI client;
- the prompt or workflow you attempted;
- what you expected and what happened instead;
- relevant bridge status or redacted audit details; and
- screenshots or a small reproducible `.blend` file that you have the right to share.

Please use [GitHub Discussions](https://github.com/CallMeJones/blender-agent-bridge/discussions) for ideas, questions, and examples; [GitHub Issues](https://github.com/CallMeJones/blender-agent-bridge/issues) for reproducible bugs; and [GitHub Security Advisories](https://github.com/CallMeJones/blender-agent-bridge/security/advisories/new) for vulnerabilities that should not be disclosed publicly.

If the bridge helps you make something interesting, I would love to see it. The repository includes a [community showcase](https://github.com/CallMeJones/blender-agent-bridge/blob/main/docs/SHOWCASE.md) and a submission path for work that demonstrates useful, reversible, or safety-aware agent workflows.

## Try It, Test It, and Help Shape It

Blender Agent Bridge is an experiment in giving AI agents meaningful creative tools without removing the artist from the loop. The goal is not a one-click replacement for Blender knowledge. The goal is a capable collaborator that can inspect, act, show its work, and wait for a human decision when the stakes are higher.

If that direction sounds useful, install the beta, connect the MCP client you already use, and try it on a copy of a real project.

- [GitHub repository](https://github.com/CallMeJones/blender-agent-bridge)
- [v0.3.1 release and downloads](https://github.com/CallMeJones/blender-agent-bridge/releases/tag/v0.3.1)
- [Installation guide](https://github.com/CallMeJones/blender-agent-bridge/blob/main/docs/INSTALL_FROM_GITHUB.md)
- [Safety model](https://github.com/CallMeJones/blender-agent-bridge/blob/main/docs/SAFETY_MODEL.md)
- [Contributing guide](https://github.com/CallMeJones/blender-agent-bridge/blob/main/CONTRIBUTING.md)

I’m looking forward to seeing where people take it—and to learning what needs to improve next.
