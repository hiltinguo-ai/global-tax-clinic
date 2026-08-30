# AiriTax - the Global Tax Clinic

A privacy-first compliance check-up for individuals, LLCs, and C-corps. Small models (optional) extract a profile; versioned jurisdiction packs decide the obligations; the model only narrates what the packs decided.

**Models talk. Code counts.**

This is a clinic, not a preparer. It does not file.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn clinic.api:app --reload --port 8000
```

Open http://127.0.0.1:8000

## Live demo

**https://global-tax-clinic.onrender.com**

The public host runs packs only (`CLINIC_NO_MODEL=1`). Personas and heuristics still open a full file; Ollama stays on your machine. The first open after idle can take about 30 seconds.

Redeploy: https://render.com/deploy?repo=https://github.com/hiltinguo-ai/global-tax-clinic

Two local SLMs sit under the clinic. Packs still compute every number; the models only extract a profile and narrate findings.

| Desk | Model | Why |
| --- | --- | --- |
| Bilingual extract / HK–CN memo | **Qwen 3.5 4B** | 200+ languages, schema-friendly, CJK intake |
| US-tax extract / English memo | **Phi-4 Mini** | English-first, strong structured reasoning, MIT |

Routing is local: CJK or Hong Kong / China mainland facts go to Qwen; English US-federal and state files go to Phi. Ollama loads one at a time (~3.4 GB + ~2.5 GB on disk, not both in RAM).

```bash
brew install ollama          # once
ollama serve                 # keep running
ollama pull qwen3.5:4b       # bilingual desk
ollama pull phi4-mini        # US-tax desk
```

The clinic header reads **Live · qwen3.5:4b + phi4-mini** when both are up. Without Ollama, gold personas and heuristics still run the full checkup.

```bash
pytest -q
```

## Hackathon slice

- US federal, Massachusetts, Hong Kong IRD, China STA, Europe, Australia ATO, Singapore IRAS, Canada CRA, UK HMRC
- Property tax, wine/alcohol excise, and GST/VAT are pack-driven (YAML + engine). The model does not invent millage, duty, or a GST bill
- Personas: Mei, Luis, Sichuan Garden LLC, NimbusFlow, Inc., Nori Robotics Inc.
- Agency layer (`hack_Justin`): Counsel → Accountant + Compliance → Counsel review. Packs still decide; desks only narrate.
- Three-valued triggers: true / false / **unknown** — facts the intake never established become follow-up questions, not silent misses
- Findings show the actual matched conditions with real values ("accounts total $15,000, > the $10,000 threshold")
- Number firewall on every explanation
- Report footer lists pack versions that actually ran
- Ollama is used automatically when running. CJK / Hong Kong / China mainland intake uses Qwen; English US-tax files use Phi-4 Mini. Set `OLLAMA_HOST` if it is not on localhost. Heuristics fill any gaps and everything still works with no model at all
