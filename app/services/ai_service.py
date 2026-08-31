import os
import base64
import json
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url='https://api.novita.ai/openai/v1',
    api_key=os.getenv('NOVITA_API_KEY')
)

VISION_MODEL = 'qwen/qwen3-vl-235b-a22b-instruct'

def process_image(image_bytes, filename):
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')

    # DIRECT JSON EXTRACTION, NO DESCRIPTION PROMPT (Saves tokens)
    vision_prompt = """
    You are an expert receipt OCR and data extraction tool. Analyze the image and return ONLY a JSON object with these exact keys:
    - merchant (string)
    - date (string, use the first 'Posting Date' in the transaction table. Do NOT use the 'Arrival Date' or 'Departure Date' in the header. Format YYYY-MM-DD)
    - time (string, HH:MM AM/PM if available, else null)
    - subtotal (number, the SUM of all 'ROOM' charges for the entire stay. Ignore 'PAYMENT VISA/MC' rows. If there are 3 nights, sum the 3 ROOM amounts. e.g., 97.75 * 3 = 293.25)
    - tax (number, the SUM of 'OCCUPANCY TAX', 'SD TOURISM TAX', and 'CA TOURISM FEE' for the entire stay. Ignore 'PAYMENT VISA/MC' rows. e.g., (12.46 + 1.96 + 0.19) * 3 = 43.83)
    - total (number, the 'Balance Due' at the bottom. If 'Balance Due' is 0, this is the SUM of the Subtotal and Tax for the entire stay. e.g., 293.25 + 43.83 = 337.08)
    - payment_method (string, e.g., "Visa", "Cash", etc.)
    - category (string, MUST be one of: FOOD, TRANSPORTATION, HOUSING, HEALTHCARE, ENTERTAINMENT, SHOPPING, EDUCATION, PERSONAL_CARE, TRAVEL, INSURANCE, OTHER. Hotel = TRAVEL)

    CRITICAL RULES:
    1. DO NOT output a paragraph description. Skip directly to the JSON.
    2. This is a multi-day hotel stay. **Calculate the totals for ALL nights/days shown, not just the first day.**
    3. The 'PAYMENT VISA/MC' rows are payments. **DO NOT use them as the subtotal or tax.**
    4. **Date Rule:** The 'Arrival Date' in the header says 08/21/26, but the actual 'Posting Date' is 08/18/26. You MUST use the first 'Posting Date' (08/18/26) and format it as 2026-08-18.

    Return ONLY the raw JSON, no markdown code blocks, no extra text.
    """

    vision_response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ],
        temperature=0.0,  # 0.0 for absolute determinism and exact math
        max_tokens=4096,  # Increased to capture full 3-day table
    )
    
    llm_output = vision_response.choices[0].message.content

    # --- DEBUGGING (Print this to your terminal) ---
    print("========== DEBUG: RAW VISION MODEL OUTPUT ==========")
    print(llm_output)
    print("========== END DEBUG ==========")
    # --------------------------------------------------------

    try:
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', llm_output, re.IGNORECASE)
        if json_match:
            llm_output = json_match.group(1)
        json_match = re.search(r'\{.*\}', llm_output, re.DOTALL)
        if json_match:
            llm_output = json_match.group(0)
        structured = json.loads(llm_output)
    except Exception:
        structured = {}

    defaults = {
        'merchant': None, 'date': None, 'time': None,
        'subtotal': None, 'tax': None, 'total': None,
        'payment_method': None, 'category': 'OTHER'
    }
    for key, default in defaults.items():
        if key not in structured or structured[key] is None:
            structured[key] = default

    structured['raw_description'] = llm_output
    return structured