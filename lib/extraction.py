"""
Label field extraction via Claude's vision capability.

Why a single multimodal call instead of a traditional OCR pipeline:
- The discovery notes are explicit that the prior vendor pilot died because
  of 30-40 second processing times -- agents abandoned it for eyeballing
  labels by hand. A single structured-output call to a fast model keeps us
  in a ~2-4 second budget per label, which is the actual hard requirement.
- Traditional OCR (Tesseract, etc.) struggles with stylized label fonts,
  angled/glare-affected photos (Jenny's note), and doesn't natively
  understand "is this in bold" or "is this all caps" the way a vision
  model reasoning over the image directly can.
- Trade-off, documented here on purpose: this sends label images to
  Anthropic's API. For a real production deployment behind Marcus's
  firewall/PII constraints, this would need an approved egress path or an
  on-prem/VPC model -- noted as a known limitation for this prototype.
"""

import base64
import json
import time
from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"  # fast model, chosen to hit the <5s/label budget

EXTRACTION_SYSTEM_PROMPT = """You are extracting structured data from a photo of an alcohol beverage label for a federal compliance tool. Read every line of visible text carefully, including small print.

Return ONLY a JSON object with exactly these keys (use "" if a field is not visible on the label):
{
  "brand_name": string,
  "class_type": string,
  "abv": string,
  "net_contents": string,
  "producer_name_address": string,
  "country_of_origin": string,
  "government_warning_text": string,
  "warning_lead_in_is_all_caps": boolean,
  "image_quality_issue": string
}

Rules:
- "government_warning_text" must be the COMPLETE warning statement exactly as printed, character for character, including the "GOVERNMENT WARNING:" lead-in exactly as it appears (preserve its actual casing so the caller can check it).
- "warning_lead_in_is_all_caps" is true only if the literal text "GOVERNMENT WARNING:" appears in all capital letters on the label.
- "image_quality_issue" should be a short note like "glare on lower label" or "angled photo, partial text cut off" if applicable, otherwise "".
- Do not guess or auto-correct values. Transcribe exactly what is printed.
- Respond with raw JSON only -- no markdown fences, no commentary.
"""


def _media_type_for(path: str) -> str:
    ext = path.lower().rsplit(".", 1)[-1]
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp",
    }.get(ext, "image/jpeg")


def extract_label_fields(image_bytes: bytes, media_type: str, api_key: str) -> dict:
    """Returns extracted dict plus '_latency_seconds' and optional '_error'."""
    client = Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    start = time.time()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64",
                                                  "media_type": media_type,
                                                  "data": b64}},
                    {"type": "text", "text": "Extract the label fields as JSON."}
                ]
            }],
        )
        raw = response.content[0].text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        data["_latency_seconds"] = round(time.time() - start, 2)
        return data
    except json.JSONDecodeError:
        return {"_error": "Model did not return valid JSON.",
                "_latency_seconds": round(time.time() - start, 2)}
    except Exception as e:
        return {"_error": str(e),
                "_latency_seconds": round(time.time() - start, 2)}
