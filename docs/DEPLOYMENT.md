# Deploying RAWRS at zero cost

**Frontend:** Vercel (Hobby) · **Backend:** Oracle Cloud Always Free · **Gate:** Cloudflare Access
Everything below stays inside a permanently free tier. No card is charged; Oracle asks for one to verify identity.

---

## Why the backend is not on Vercel

| the backend needs | Vercel serverless allows |
|---|---|
| `torch`, `transformers`, `docling`, `surya-ocr` — several GB | 250 MB unzipped function |
| minutes per document with OCR/AI | 10–60 s per request |
| `outputs/` — 612 MB of jobs, sidecars, images, DOCX | ephemeral `/tmp` |
| one process holding in-memory job state | stateless per request |

Not a tuning problem. The frontend is a perfect fit for Vercel; the API needs a real machine.

---

## 1. Backend — Oracle Cloud Always Free

Create the VM: cloud.oracle.com → **Compute → Instances → Create**. Shape **VM.Standard.A1.Flex**, **4 OCPU / 24 GB RAM**, image **Ubuntu 22.04**, boot volume 200 GB. Save the SSH key.

```bash
ssh ubuntu@<vm-ip>
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && exit          # re-login for the group

git clone https://github.com/winvinayainfosystemsindia/RAWRS---V1.git rawrs
cd rawrs
```

Create `.env` next to `docker-compose.yml` — **never commit it**:

```
TUNNEL_TOKEN=<from step 2>
RAWRS_ALLOWED_ORIGINS=https://<your-project>.vercel.app
```

```bash
docker compose up -d --build     # first ARM build: 20-40 min, mostly torch
docker compose logs -f api       # wait for "Application startup complete"
```

No firewall rule and no open port are needed — the tunnel dials out.

---

## 2. Exposure — Cloudflare Tunnel (free)

one.dash.cloudflare.com → **Networks → Tunnels → Create a tunnel** → *Cloudflared*. Copy the token into `.env`. Add a public hostname:

| field | value |
|---|---|
| Subdomain / domain | `api` · your domain (a free `*.trycloudflare.com` works for testing only) |
| Service | `HTTP` → `api:8001` |

HTTPS is issued automatically. `https://api.<domain>/api/health` should return OK.

---

## 3. Login for the team — Cloudflare Access (free, ≤50 users)

Zero Trust → **Access → Applications → Add a self-hosted application**, domain `api.<domain>`. Policy: *Allow* → **Emails** (list your reviewers) or **Email domain**. Identity provider: Google or GitHub, both free.

Repeat for the Vercel domain to gate the UI as well. **This is the only access control that exists — RAWRS itself has no login (see Known gaps).**

---

## 4. Frontend — Vercel

vercel.com → **Add New → Project** → import the repo → set **Root Directory** to `frontend`. Add one environment variable:

| name | value |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://api.<domain>` |

Deploy. Then put the resulting domain into `RAWRS_ALLOWED_ORIGINS` on the VM and run `docker compose up -d` again.

> Vercel's Hobby plan is for **non-commercial** use. If RAWRS becomes company work, move the frontend to Cloudflare Pages — also free, and commercial use is permitted.

---

## 5. Updating

```bash
cd rawrs && git pull && docker compose up -d --build
```

`outputs/` lives in the `rawrs-outputs` volume, so rebuilds never discard a reviewer's work. The frontend redeploys itself on push.

---

## Known gaps — deployment does not fix these

| gap | consequence | where |
|---|---|---|
| **No authentication in RAWRS** | any request reaching the API can edit any document; Cloudflare Access guards the perimeter only, and there is no per-user identity inside the app | `src/api/routes.py` |
| **In-memory job state** | exactly one backend instance; `--workers 1` is deliberate, and a second worker would serve a different view of the same jobs | `src/api/jobs.py` |
| **No concurrency control** | two reviewers editing one document overwrite each other — corrections are transactional per object, but there is no locking or presence | correction rail |
| **First ARM build is the risk** | `torch`/`docling`/`surya` wheels on aarch64 are the one step likely to need attention | `Dockerfile` |

Each is real product work, not a hosting setting.
