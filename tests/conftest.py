import os

# Packs and personas must stay deterministic. The live SLM is exercised
# via /api/health and /api/checkup, not the pytest suite.
os.environ["CLINIC_NO_MODEL"] = "1"
