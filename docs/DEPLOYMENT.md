# Deploying RAWRS

**Status 2026-10-21:** the **frontend** is live on Vercel Hobby at **https://rawrs-v1.vercel.app** (the previous Vercel project had been deleted, so the URL returned `DEPLOYMENT_NOT_FOUND`; it was recreated). The **backend** is not hosted. It runs on the owner's laptop on request (see *Hosted frontend + laptop server* below), and while it is off the site shows an "offline — request access from the project owner" notice (`frontend/components/BackendStatusNotice.tsx`).

**Status 2026-09-30:** nothing is deployed. The earlier plan (Vercel + Oracle Always Free + Cloudflare) cannot be completed without a payment card, and Oracle's free allowance has since shrunk. Prices and limits below were fetched on 2026-09-30 — see `STATUS_REPORT_2026-09-30.md` §6–7 for sources and the questions the company must answer first.

---

## Why the backend is not on Vercel

| the backend needs | Vercel serverless allows |
|---|---|
| `torch`, `transformers`, `docling`, `surya-ocr` — several GB | 250 MB unzipped function |
| minutes per document with OCR/AI | 10–60 s per request |
| `outputs/` — 682 MB of jobs, sidecars, images, DOCX | ephemeral `/tmp` |
| one process holding in-memory job state | stateless per request |

The frontend fits Vercel; the API needs a real machine.

---

## Choose a route

| Route | Cost | Needs a card | Up when | Use for |
|---|---|---|---|---|
| **A. Your PC + Cloudflare quick tunnel** | $0 | No | PC is on | Demo, pilot |
| **B. Paid VPS (Hetzner CX43, x86, 16 GB)** | €15.99/mo + ~€0.50 IPv4 | Yes (payment method) | 24×7 | Team use, after auth exists |
| **C. Oracle Always Free** | $0 | **Yes** — identity verification | 24×7 | Only if the company supplies a card; allowance is now **2 OCPU / 12 GB** (was 4 / 24) |

The machine needs ≥ 8 GB RAM to run at all (API ~4 GB + Ollama `qwen2.5vl:3b` ~3 GB, per earlier measurements — not re-measured). 16 GB is comfortable; the 7.7 GB development laptop runs out of memory on full-corpus runs.

---

## Hosted frontend + laptop server (current setup)

The Vercel build is made with `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001`, so the hosted site talks to **the server on the computer viewing it**.

| Who opens the site | What happens |
|---|---|
| The owner, with the server running on their laptop | Full RAWRS: upload, review, export, insights |
| Anyone else, or the owner with the server stopped | The interface loads; a notice at the top states the processing service is offline and that access must be requested from the project owner, and links to the sample document |
| Anyone, at `/documents/demo` | The full review workspace for one sample (the Brinkman benchmark paper: tables, figures, endnotes), read-only, served from `frontend/public/demo/` with no server |

To make the hosted site live on your laptop:

```powershell
$env:RAWRS_ALLOWED_ORIGINS = "https://rawrs-v1.vercel.app"   # CORS: allow the hosted site
uvicorn src.api.main:app --port 8001
```

Then open https://rawrs-v1.vercel.app on the same laptop. Chrome may ask to allow the site to access devices on the local network; allow it, because that is the browser letting the hosted page reach `127.0.0.1`. Without the `RAWRS_ALLOWED_ORIGINS` line the browser blocks every request and the offline notice stays up even though the server is running.

To show RAWRS to someone on another computer, use Route A below: a tunnel, plus a redeploy with the tunnel URL.

Redeploy after frontend changes: `cd frontend; vercel --prod`. The project is not connected to GitHub, so a push does not deploy.

**Sample document.** `frontend/public/demo/` holds the API responses for the sample job, captured from a real RAWRS run with the job id rewritten to `demo`. `lib/api.ts` (`demoFile`, `fileUrl`) serves the `demo` job from these files and refuses every edit. To refresh it after a pipeline change, run RAWRS on the PDF (in a Codespace if the laptop runs short of memory, with Ollama `qwen2.5vl:3b`), generate alt text for the two figures, check each draft against the figure and approve it (edited where the draft is wrong, as a reviewer would; the 2026-10-21 Figure 1 draft misread the chart), then save each `GET /api/documents/{id}/…` response as `<endpoint>.json`, the source PDF, downloads and image files under the same names, then replace the id with `demo`.

---

## Route A — your PC, no card

1. Start the backend with the frontend's origin allowed (comma-separated list):

   ```powershell
   $env:RAWRS_ALLOWED_ORIGINS = "https://<your-project>.vercel.app"
   uvicorn src.api.main:app --port 8001
   ```

2. In a second terminal, publish it: `cloudflared tunnel --url http://localhost:8001`. It prints a random `https://….trycloudflare.com` URL that **changes every run**.
3. Deploy `frontend/` to Vercel (Root Directory `frontend`) with `NEXT_PUBLIC_API_BASE_URL` = that URL. The variable is fixed at build time, so each new tunnel URL needs a redeploy.

Limits: availability is the PC's; the tunnel URL is unstable; **no login** (see known gaps). Alternative: serve the frontend from the same PC and tunnel only that, which needs a small proxy change in the frontend (not built).

---

## Route B / C — a VM with Docker

Both use the repository's `Dockerfile` and `docker-compose.yml` (API + Ollama + Cloudflare tunnel). The Dockerfile builds on x86_64 and aarch64; **the aarch64 build has never been run** (torch/docling/surya wheels are the risk). Prefer x86 (Route B) unless the VM is an Oracle Ampere one.

```bash
ssh <user>@<vm-ip>
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && exit          # re-login for the group

git clone https://github.com/winvinayainfosystemsindia/RAWRS---V1.git rawrs
cd rawrs
```

Create `.env` next to `docker-compose.yml` — **never commit it**:

```
TUNNEL_TOKEN=<from the Cloudflare step below>
RAWRS_ALLOWED_ORIGINS=https://<your-project>.vercel.app
```

```bash
docker compose up -d --build     # first build is long, mostly torch
docker compose logs -f api       # wait for "Application startup complete"
docker compose exec ollama ollama pull qwen2.5vl:3b   # ~3 GB, kept in the ollama-models volume
```

Without the model RAWRS still exports; images are flagged for a human to write alt text. No firewall rule or open port is needed — the tunnel dials out.

Oracle only: create the instance under **Compute → Instances**, shape **VM.Standard.A1.Flex**, **at most 2 OCPU / 12 GB** (Always Free), Ubuntu 22.04, boot volume up to 200 GB (the free total). The allowance and card requirement are documented at <https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm>.

### Cloudflare Tunnel (free) and Access (free ≤ 50 users)

one.dash.cloudflare.com → **Networks → Tunnels → Create a tunnel** → *Cloudflared*; copy the token into `.env`. Add a public hostname pointing `api.<your-domain>` at `HTTP` → `api:8001`. A named tunnel needs a domain on Cloudflare; without one use Route A's quick tunnel.

Zero Trust → **Access → Applications → Add a self-hosted application** for `api.<domain>`, policy *Allow* → the reviewers' emails, identity provider Google or GitHub. **This is the only access control that exists — RAWRS itself has no login.**

### Frontend — Vercel

vercel.com → **Add New → Project** → import the repo → Root Directory `frontend`; set `NEXT_PUBLIC_API_BASE_URL` = `https://api.<domain>`. Put the resulting domain into `RAWRS_ALLOWED_ORIGINS` and run `docker compose up -d` again.

> Vercel Hobby is for **non-commercial** use. If RAWRS becomes company work, use Vercel Pro ($20/seat/month) or Cloudflare Pages (free; commercial terms not re-checked).

### Updating

```bash
cd rawrs && git pull && docker compose up -d --build
```

`outputs/` (including saved Markdown edits in `outputs/edits/`) lives in the `rawrs-outputs` volume, so rebuilds never discard a reviewer's work.

---

## Known gaps — hosting does not fix these

| gap | consequence | where |
|---|---|---|
| **No authentication in RAWRS** | any request reaching the API can edit any document; Cloudflare Access guards the perimeter only, and there is no per-user identity inside the app | `src/api/routes.py` |
| **In-memory job state** | exactly one backend instance; `--workers 1` is deliberate | `src/api/jobs.py` |
| **No concurrency control** | two reviewers editing one document overwrite each other | correction rail |
| **First ARM build is unproven** | `torch`/`docling`/`surya` wheels on aarch64 may need attention | `Dockerfile` |
| **Licences** | PyMuPDF (AGPL), Surya weights and `qwen2.5vl:3b` have terms that may restrict networked or commercial use | `STATUS_REPORT_2026-09-30.md` §7 |

Each is real product work or a company decision, not a hosting setting.
