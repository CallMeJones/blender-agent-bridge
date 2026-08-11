# Generation Providers

Blender Agent Bridge can import existing assets and can route image-to-3D jobs through hosted, local, or self-hosted providers. Every provider is optional. Scene inspection, reversible helper edits, trusted scripts, project tools, rendering, and the five-tool MCP gateway work without any generation provider configured.

## Provider Summary

| Provider | What the bridge supports | Setup | Network, cost, and quality |
| --- | --- | --- | --- |
| [Poly Haven](https://polyhaven.com/) | Search and import HDRIs, PBR textures, and models with source metadata. | None. | Downloads from Poly Haven's open API; assets are CC0. |
| [Sketchfab](https://sketchfab.com/) | Public model search plus authenticated glTF downloads and imports with author, source, and license provenance. | Search needs no key. Downloads need your Sketchfab API token. | Asset licenses vary; attribution and the model's license follow the imported asset. |
| [Tripo](https://platform.tripo3d.ai/) | Hosted single-image and calibrated multi-view image-to-3D jobs, option-aware spend estimates, polling recovery, cached results, import, and provenance. | Tripo API key plus **Allow Third-Party Uploads**. | Uploads references and consumes Tripo API credits. Best hosted route when multiple views are available. |
| [Meshy](https://docs.meshy.ai/en/api) | Hosted single-image and multi-image jobs with Meshy 7, Meshy T2 Smart Topology, native remeshing, PBR textures, provider thumbnails, polling recovery, cached artifacts, import, and provenance. | Meshy API key plus **Allow Third-Party Uploads**. | Uploads references and consumes Meshy account credits. The approval shows the option-aware estimate and normalized source paths. Generated topology still needs evaluation after import. |
| [TripoSR](https://github.com/VAST-AI-Research/TripoSR) | Direct local single-image reconstruction, persistent tuning defaults, Z-up import normalization, cleanup, and evaluation renders. | A separate Python environment with TripoSR and CUDA-capable PyTorch, plus the local checkout path. | No vendor key, upload, or API credits. Treat it as a fast blockout route: one image cannot reveal hidden side or back structure. |
| **Studio endpoint** | Self-hosted single-view or multi-view generation through a small bridge-compatible HTTP API, with polling, cached import, and provenance. | A service base URL and optional bearer token under **Set Up Providers**. The inference service itself is not bundled. | Counts as local/self-hosted, so no third-party-upload or vendor-spend approval is required. Plain HTTP is limited to localhost/private-network hosts; public hostnames require HTTPS. |

## Provider Choice And Approval

When more than one generation provider is ready, the bridge asks which provider to use and starts nothing until the user answers. It does not silently prefer local, hosted, cheap, or fast.

Hosted Tripo and Meshy jobs require an explicit spend approval in Blender before a request is sent. The agent can poll the exact approval request and detect **Approve**, **Decline**, or expiry without asking the user to report the click. Approval is single-use and bound to the provider, resolved cost/output controls, and SHA-256 identity of every reference, so replacing an image at the same path requires a new decision.

Local TripoSR and the self-hosted studio endpoint do not create spend requests. A sole local provider may be selected automatically; a hosted provider never is. Provider pricing can change, so treat Blender's resolved estimate as a preflight aid and review the provider's billing page before approving paid work.

Generation references are validated and read through one bounded path before a job starts: 20 MiB per image, 64 MiB total, provider-specific image counts, and PNG/JPEG/WebP signature checks where supported. The same identities are verified again immediately before upload or local encoding. Studio bearer tokens are sent for same-origin artifact downloads only; signed cross-origin CDN downloads use the unauthenticated hosted-download path.

Current live evidence is tracked in [Next On The Roadmap](ROADMAP_NEXT.md). The [Meshy vehicle report](assets/meshy-vehicle-multiview-report.md) documents a paid four-reference generation/import run with topology findings, texture-atlas verification, orientation review, and an explicit warning that provider output is not automatically production topology.

## Configure Poly Haven And Sketchfab

Poly Haven works immediately. For Sketchfab downloads:

1. In Blender's `Agent Bridge` sidebar, expand `Image-To-3D Generation` and press `Set Up Providers`.
2. Copy your token from [Sketchfab account settings](https://sketchfab.com/settings/password) into **Sketchfab API Token**.
3. Leave **Remember Keys On This Machine** enabled to use the operating system credential store where available, or turn it off to keep the token only until Blender closes. The panel identifies the storage mechanism it selected.

The token field blanks itself after accepting the value; the status line below it confirms whether the token is set. As an alternative for automated MCP environments, set `SKETCHFAB_API_TOKEN` or `BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN` in the MCP server process.

## Configure Hosted Tripo And Meshy

1. Create a key in the [Tripo API portal](https://platform.tripo3d.ai/api-keys) and/or [Meshy API settings](https://www.meshy.ai/settings/api).
2. Open `Agent Bridge > Image-To-3D Generation > Set Up Providers`.
3. Enable **Allow Third-Party Uploads**.
4. Paste the key into **Tripo API Key** or **Meshy API Key**. The field clears after secure capture and the status line reports that the key is set.
5. Ask the agent to check generation provider diagnostics before starting the first job.

Keys entered here are held in session memory. With **Remember Keys On This Machine** enabled, they use the operating system credential facility where available; otherwise the panel reports a private user-only file fallback without describing it as encrypted. Keys are never written to `userpref.blend`, project `.blend` files, manifests, or audit logs. Tripo and Meshy use separate API billing from this extension, so review the provider's current credit pricing before approval.

Meshy jobs default to the recommended `blender_working` preset: Meshy 7/latest, native triangle remeshing near 100,000 faces, preservation of the original pre-remesh GLB, PBR 4K texturing, automatic bottom-origin sizing, and cached transparent/cardinal thumbnails. Use `raw_high_detail` to retain the previous unremeshed result or `editable_quad` for a 50,000-face quad-dominant target.

Advanced calls can override these through `meshy_options`, including `ai_model`, Smart Topology, Ultra, texturing, remeshing, adaptive decimation, enhancement, sizing, origin, and thumbnail controls. Invalid model/endpoint combinations are rejected before approval.

For Meshy 7 multi-image jobs, put the primary/front reference in `front`; the remaining one to three images may be supporting angles in any order. Tripo's multi-view slots remain positional. Successful Meshy jobs retain the final GLB, optional pre-remesh GLB, thumbnails, available PBR maps, resolved options, expiry, and actual consumed credits before signed provider URLs expire.

## Configure Local TripoSR

TripoSR runs outside Blender's bundled Python. The official project requires Python 3.8 or newer, a platform-compatible PyTorch installation, and approximately 6 GB of VRAM at its default settings. Create a dedicated environment rather than installing Torch into Blender:

```text
git clone https://github.com/VAST-AI-Research/TripoSR.git
python -m venv .venv-triposr

# Replace TRIPOSR_PYTHON below with:
# Windows: .venv-triposr\Scripts\python.exe
# macOS/Linux: .venv-triposr/bin/python
TRIPOSR_PYTHON -m pip install --upgrade pip setuptools
TRIPOSR_PYTHON -m pip install -r TripoSR/requirements.txt
```

Install the CUDA-compatible PyTorch build recommended by the [official PyTorch selector](https://pytorch.org/get-started/locally/) into that same environment. Then open **Set Up Providers** and set:

- **Generation Python** to the environment's Python executable.
- **TripoSR Folder** to the cloned directory containing `run.py`.
- **TripoSR Defaults** only when you need to trade detail, VRAM, background removal, or texture behavior for a particular machine.

Verify the environment independently before using the bridge:

```text
cd TripoSR
TRIPOSR_PYTHON run.py examples/chair.png --output-dir output
```

The provider diagnostics should then report TripoSR as runnable. For final assets with meaningful unseen structure, use calibrated multi-view input with Tripo or Meshy, or author and refine the model in Blender.

## Configure A Self-Hosted Studio Endpoint

The studio route is for an image-to-3D service running on this computer, another machine on the local network, or an HTTPS server your studio controls. The bridge does not install or operate that service. In **Set Up Providers**, enter its base URL under **Studio Endpoint** and, when required, enter an **Endpoint Token**. The token follows the same session/credential-store rules as the hosted provider keys.

The service contract is intentionally small:

```text
POST /image-to-3d
  {"views": [{"name": "front", "image_url": "data:..."}], ...}
  -> {"task_id": "..."}

GET /tasks/{task_id}
  -> {"status": "...", "progress": 0, "model_url": "..."}

GET /balance
  -> optional; the job continues when the service does not expose it
```

Task creation may also include `model`, `face_limit`, and `texture`. Status responses may return the GLB URL as `model_url` or `model_urls.glb`. Plain HTTP is accepted only for localhost, private/link-local IPs, single-label hosts, or `.local`/`.localhost` names; use HTTPS for a public domain.

The bridge treats this route as local/self-hosted and does not show a vendor spend prompt, so the service owner remains responsible for its compute and billing policy. A Hunyuan3D or TRELLIS server can eventually sit behind this contract even though direct launchers are not currently included.
