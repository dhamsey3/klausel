"""Klausel: self-hosted, GDPR-compliant document AI and contract reviewer."""

import os

# Enforce "no US cloud at runtime" as soon as any klausel module is imported,
# before Hugging Face libraries read their config. Only scripts/download_model.py
# overrides this, deliberately.
for _var, _val in {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "ZENML_ANALYTICS_OPT_IN": "false",
}.items():
    os.environ.setdefault(_var, _val)

__version__ = "0.1.0"
