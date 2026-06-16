# TTB Label Verification Prototype

AI-assisted tool that compares an alcohol beverage label photo against the
submitted application data and flags mismatches, built from the discovery
notes (Sarah Chen, Marcus Williams, Dave Morrison, Jenny Park).

## What this is and isn't

This is a **standalone proof-of-concept**, not connected to COLA. It doesn't
persist anything to a database -- uploaded images and data live only in the
browser session, per the "don't store anything sensitive for this exercise"
note from IT. It's meant to inform a future procurement/integration
decision, not to go into production as-is.

## Setup

```bash
git clone <this-repo>
cd ttb-label-verifier
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

You'll need an Anthropic API key (console.anthropic.com → API Keys). Either:
- Paste it into the sidebar field when the app is running, or
- Set it as an environment variable before launching: `export ANTHROPIC_API_KEY=sk-...`

## Run locally

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Generate sample test labels (optional)

No real bottle photography was available for this exercise, so
`lib/generate_test_labels.py` renders six synthetic labels with Pillow,
including ones deliberately built to exercise the edge cases from the
interviews (casing mismatch, title-case warning, ABV mismatch, an import
label with country-of-origin, and a glare/rotated "bad photo").

```bash
python lib/generate_test_labels.py
```

This (re)writes `test_labels/*.png` and `sample_data/applications.csv`. For
batch mode, zip the `test_labels` folder and upload it alongside the CSV.

## Deploying so Treasury/TTB can access it

Easiest free path, no infra to manage:

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, "New app",
   point it at this repo and `app.py`.
3. In the app's **Settings → Secrets**, add:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
4. Deploy. You get a public `*.streamlit.app` URL within a couple of minutes.

(Render, Railway, or Fly.io work too if a non-Streamlit-branded URL is
preferred -- same `requirements.txt` and `streamlit run app.py --server.port $PORT`
start command.)

## Approach

**Why vision-model extraction instead of traditional OCR:** the prior
vendor pilot reportedly took 30-40 seconds per label and agents abandoned it
for eyeballing labels by hand. The hard requirement that actually matters is
turnaround time, not extraction method. A single multimodal call to a fast
model (`claude-haiku-4-5`) returning structured JSON keeps each label in a
roughly 2-4 second budget, and handles stylized fonts and the all-caps/bold
check on the warning statement in a way that plain OCR + regex would
struggle with.

**Why fields get different matching strictness:** Dave's "STONE'S THROW" vs
"Stone's Throw" example is the whole reason most fields use a normalized,
case/whitespace-insensitive comparison with a fuzzy-similarity fallback
flagged as "needs review" rather than auto-rejected. The Government Warning
field is the deliberate exception -- Jenny's title-case rejection example
means that field gets zero leniency: exact wording, exact all-caps lead-in,
or it fails. This mirrors how the two agents actually described doing their
own jobs differently field-by-field, rather than applying one matching rule
uniformly.

**Why batch mode is CSV + ZIP instead of one-at-a-time:** directly answers
Sarah/Janet's complaint about 200-300 label dumps from importers needing to
be processed one at a time today.

**UI choices for the "my 73-year-old mother" bar:** one visible mode toggle,
large status pills with color, no nested menus, no jargon in the labels
shown to the user (statuses are PASS / NEEDS REVIEW / MISMATCH / MISSING ON
LABEL, not raw similarity scores front-and-center).

## Assumptions

- Field strictness levels (which fields get fuzzy matching vs. exact) were
  inferred from the interview transcripts, not from a formal TTB style
  guide. A real deployment should have Compliance Division sign off on
  these thresholds field-by-field.
- The Government Warning comparison checks against the standard 27 CFR
  §16.21 statement text. Beer/wine/spirits have minor statutory variations
  in some other field requirements (e.g., ABV disclosure exceptions for
  certain wines/beers) that this prototype doesn't branch on by beverage
  type -- it treats all labels generically.
- "Bold" formatting on the warning statement is not verified, only the
  all-caps lead-in and exact wording, since reliably detecting font-weight
  from a photo is unreliable; this is flagged as a known gap below.
- Batch CSV matches images by filename, not by some application ID scheme
  that would exist in a real COLA integration.

## Known limitations / trade-offs (time-boxed take-home)

- **No production security review.** Sending label images to Anthropic's
  API would need an approved egress path through Marcus's firewall and a
  data-handling review before any real deployment -- this is a known
  blocker for productionizing, not solved here.
- **No bold-text detection** on the Government Warning (see above).
- **No retry/backoff logic** on API failures; a transient error just shows
  as an error row instead of auto-retrying.
- **No authentication** on the app itself -- anyone with the URL can use it.
  Fine for an internal eval prototype, not fine for production.
- **Not integration-tested against real bottle photography** (angled
  shots, glare, low light) -- only against synthetic labels and one
  deliberately glare/rotated synthetic example. Real-world label photos
  from the field would likely surface extraction issues this didn't catch.
- **English-language labels only** -- no testing against labels with
  non-English producer text (relevant for some imports).

## Tools used

Python, Streamlit, Anthropic API (`claude-haiku-4-5` for vision extraction),
Pillow (synthetic test label generation), pandas (batch results table).
