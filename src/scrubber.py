import re
from db import store_secret

# Basic Regex patterns for standard secrets
# In a robust system, this could be replaced by a full NER / Presidio library 
PATTERNS = {
    "API_KEY": r"(?i)(?:key|token|secret)[\s=:]+([a-zA-Z0-9_\-]{20,})",
    "CREDIT_CARD": r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b",
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "PASSWORD": r"(?i)(?:password|pwd)[\s=:]+([^\s]+)"
}

def scrub_text(text: str) -> str:
    """
    Scans text for sensitive PII and API keys, extracts them into the secure Vault,
    and replaces them with a redacted marker in the original text.
    Returns the scrubbed text.
    """
    scrubbed_text = text
    
    for secret_type, pattern in PATTERNS.items():
        matches = re.finditer(pattern, scrubbed_text)
        
        # Process in reverse order so replacements don't mess up string indices
        for match in reversed(list(matches)):
            # If there's a capturing group, that's the actual secret, else the whole match
            secret_value = match.group(1) if match.groups() else match.group(0)
            
            # Use part of the text for a unique key if needed, or just let DB generate ID 
            # We'll generate a unique key for the vault reference
            vault_key = f"{secret_type}_{hash(secret_value)}"
            
            store_secret(vault_key, secret_value, f"Auto-extracted {secret_type} from ingestion")
            
            # Replace the secret in the text with a safe vault reference
            replacement = f"[REDACTED {secret_type}: Reference ID {vault_key}]"
            start, end = match.span()
            if match.groups():
                # Replace only the captured group section
                start, end = match.span(1)
            
            scrubbed_text = scrubbed_text[:start] + replacement + scrubbed_text[end:]
            
    return scrubbed_text
