import os
import io
import json
import ast
import base64
import re
from typing import Dict, List, Any, Tuple
import requests
import streamlit as st
import qrcode
from PIL import Image

# ---------------------------------------------------------
# Streamlit Page Config & Theme
# ---------------------------------------------------------
st.set_page_config(
    page_title="Parchi-Pay | Voice-to-UPI Bill Settlement",
    page_icon="🧾",
    layout="wide"
)

# Custom Styling
st.markdown("""
<style>
    .title-banner {
        font-size: 2.3rem;
        font-weight: 800;
        background: linear-gradient(135deg, #60A5FA 0%, #3B82F6 50%, #34D399 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-banner {
        font-size: 1.05rem;
        color: var(--text-color);
        opacity: 0.85;
        margin-bottom: 1.5rem;
    }
    .section-header {
        font-size: 1.35rem;
        font-weight: 700;
        color: var(--text-color) !important;
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-top: 1.8rem;
        margin-bottom: 0.8rem;
    }
    .section-tag {
        background-color: rgba(59, 130, 246, 0.18);
        color: #60A5FA !important;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        border: 1px solid rgba(96, 165, 250, 0.4);
    }
    .sub-section-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--text-color) !important;
        margin-top: 1.5rem;
        margin-bottom: 0.8rem;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid rgba(148, 163, 184, 0.25);
    }
    .settlement-card {
        background: var(--secondary-background-color);
        border: 1px solid rgba(148, 163, 184, 0.25);
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .card-title {
        margin: 0;
        font-size: 1.15rem;
        font-weight: 700;
        color: #60A5FA !important;
    }
    .card-amount {
        margin: 0.3rem 0;
        font-size: 1.65rem;
        font-weight: 800;
        color: #34D399 !important;
    }
    .hindi-box {
        background: rgba(37, 99, 235, 0.12);
        border-left: 5px solid #3B82F6;
        padding: 1rem 1.2rem;
        border-radius: 0 8px 8px 0;
        font-size: 1.15rem;
        font-weight: 600;
        color: var(--text-color) !important;
        margin: 0.8rem 0;
    }
    .english-box {
        background: rgba(16, 185, 129, 0.12);
        border-left: 5px solid #10B981;
        padding: 0.8rem 1.2rem;
        border-radius: 0 8px 8px 0;
        font-size: 1.0rem;
        color: var(--text-color) !important;
        margin-bottom: 1rem;
    }
    .upi-btn {
        display: inline-block;
        background-color: #2563EB;
        color: #FFFFFF !important;
        padding: 0.55rem 1.2rem;
        border-radius: 8px;
        text-decoration: none !important;
        font-weight: 600;
        margin-top: 0.5rem;
    }
    .upi-btn:hover {
        background-color: #1D4ED8;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# API Key Resolver
# ---------------------------------------------------------
def get_sarvam_api_key() -> str:
    """Read API key from os.environ.get('SARVAM_API_KEY') with local fallback."""
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not key:
        if os.path.exists("api_key.txt"):
            try:
                with open("api_key.txt", "r", encoding="utf-8") as f:
                    key = f.read().strip()
            except Exception:
                pass
        elif os.path.exists(".env"):
            try:
                with open(".env", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("SARVAM_API_KEY="):
                            key = line.strip().split("=", 1)[1].strip()
            except Exception:
                pass
        if key:
            os.environ["SARVAM_API_KEY"] = key
    return key


# ---------------------------------------------------------
# Deterministic Python Settlement Engine
# ---------------------------------------------------------
def compute_net_settlements(parsed_expenses: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, float], Dict[str, float]]:
    """
    Computes mathematically rigorous, zero-sum net settlements deterministically.
    
    Returns:
        (settlements, net_balances, total_paid, total_owed)
    """
    # 1. Determine all unique participants across all expenses
    participants = set()
    for exp in parsed_expenses:
        payer = (exp.get("paid_by") or exp.get("payer") or "").strip()
        if payer:
            participants.add(payer)
        for p in exp.get("split_between", []):
            if isinstance(p, str) and p.strip():
                participants.add(p.strip())

    # 2. For each person, calculate total_paid and total_owed
    total_paid = {p: 0.0 for p in participants}
    total_owed = {p: 0.0 for p in participants}

    for exp in parsed_expenses:
        payer = (exp.get("paid_by") or exp.get("payer") or "").strip()
        amt = float(exp.get("amount", 0))
        split_between = [p.strip() for p in exp.get("split_between", []) if isinstance(p, str) and p.strip()]
        
        # If split_between is empty, assume split equally among all participants
        if not split_between:
            split_between = list(participants) if participants else ([payer] if payer else [])
        if not split_between:
            continue

        if payer:
            total_paid[payer] += amt

        share_per_person = amt / len(split_between)
        for p in split_between:
            total_owed[p] += share_per_person

    # 3. Compute net_balance = total_paid - total_owed
    net_balances = {p: round(total_paid[p] - total_owed[p], 2) for p in participants}

    # 4. Separate participants into creditors (balance > 0.01) and debtors (balance < -0.01)
    creditors = [{"person": p, "balance": net_balances[p]} for p in participants if net_balances[p] > 0.01]
    debtors = [{"person": p, "balance": net_balances[p]} for p in participants if net_balances[p] < -0.01]

    # Sort creditors descending and debtors ascending (most negative first)
    creditors.sort(key=lambda x: x["balance"], reverse=True)
    debtors.sort(key=lambda x: x["balance"])

    # 5. Greedy debt minimization
    settlements = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        debtor = debtors[i]
        creditor = creditors[j]
        debt = min(-debtor["balance"], creditor["balance"])
        debt = round(debt, 2)

        if debt > 0.01:
            debtor_target_vpa = (re.sub(r'[^a-zA-Z0-9]', '', creditor["person"].lower()) or "merchant") + "@upi"
            creditor_name = creditor["person"]
            upi_uri = 'upi://pay?pa=' + debtor_target_vpa + '&pn=' + creditor_name + '&am=' + f"{debt:.2f}" + '&tn=ParchiPay'

            settlements.append({
                "from_person": debtor["person"],
                "to_person": creditor_name,
                "amount": debt,
                "upi_uri": upi_uri
            })

        debtor["balance"] += debt
        creditor["balance"] -= debt

        if abs(debtor["balance"]) <= 0.01:
            i += 1
        if abs(creditor["balance"]) <= 0.01:
            j += 1

    return settlements, net_balances, total_paid, total_owed


def generate_settlement_summaries(settlements: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Generate deterministic Hindi and English summaries directly from calculated settlements."""
    if not settlements:
        return "सभी हिसाब बराबर हैं, किसी को कोई भुगतान नहीं करना है।", "All balances are settled. No payments required."

    hi_parts = []
    en_parts = []
    for s in settlements:
        from_p = s["from_person"]
        to_p = s["to_person"]
        amt = s["amount"]
        amt_str = f"{int(amt)}" if amt.is_integer() else f"{amt:.2f}"
        hi_parts.append(f"{from_p}, {to_p} को ₹{amt_str} भेजेंगे")
        en_parts.append(f"{from_p} pays {to_p} ₹{amt:.2f}")

    summary_hindi = " और ".join(hi_parts) + "।"
    summary_english = ", and ".join(en_parts) + "."
    return summary_hindi, summary_english


# ---------------------------------------------------------
# QR Code Generator
# ---------------------------------------------------------
def create_upi_qr(upi_uri: str) -> bytes:
    """Generate scannable UPI QR code PNG bytes using python qrcode."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(upi_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------
# Sarvam AI API Calls
# ---------------------------------------------------------
def run_stt(audio_bytes: bytes, api_key: str) -> str:
    """
    STT Endpoint: POST https://api.sarvam.ai/speech-to-text
    Multipart files={'file': ('audio.wav', audio_bytes, 'audio/wav')}
    data={'model': 'saaras:v4', 'mode': 'codemix'}
    """
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": api_key}
    files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
    data = {"model": "saaras:v4", "mode": "codemix"}

    response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"STT Error ({response.status_code}): {response.text}")
    
    return response.json().get("transcript", "").strip()


def robust_parse_expenses(raw_text: str) -> List[Dict[str, Any]]:
    """
    Multi-strategy resilient JSON parser for LLM outputs.
    Recovers from missing commas, trailing commas, single quotes,
    comments, and uses deterministic regex item extraction as ultimate fallback.
    """
    if not raw_text or not raw_text.strip():
        return []

    cleaned = raw_text.strip()

    # Step 1: Strip markdown code blocks
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

    # Step 2: Strip comments // and /* */
    cleaned = re.sub(r"//.*?\n", "\n", cleaned)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

    def extract_expense_list(obj):
        if isinstance(obj, dict):
            if "parsed_expenses" in obj and isinstance(obj["parsed_expenses"], list):
                return obj["parsed_expenses"]
            for v in obj.values():
                if isinstance(v, list) and v and isinstance(v[0], dict) and ("amount" in v[0] or "item" in v[0]):
                    return v
        elif isinstance(obj, list):
            if obj and isinstance(obj[0], dict):
                return obj
        return None

    # Strategy 1: Direct json.loads
    try:
        data = json.loads(cleaned)
        res = extract_expense_list(data)
        if res is not None:
            return res
    except Exception:
        pass

    # Strategy 2: Pre-repair common JSON syntax errors
    repaired = cleaned
    # Remove trailing commas
    repaired = re.sub(r",\s*([\]}])", r"\1", repaired)
    # Add missing comma between }{
    repaired = re.sub(r"\}\s*\{", "},{", repaired)
    # Add missing comma between ][
    repaired = re.sub(r"\]\s*\[", "],[", repaired)
    # Fix missing commas after numbers before next property: e.g. "amount": 1200 "paid_by"
    repaired = re.sub(r'(\d+(?:\.\d+)?)\s*\n*\s*"([a-zA-Z_]+)"\s*:', r'\1, "\2":', repaired)
    # Fix missing commas after strings before next property
    repaired = re.sub(r'(")\s*\n*\s*"([a-zA-Z_]+)"\s*:', r'\1, "\2":', repaired)
    # Fix missing commas after array closing ] before next property
    repaired = re.sub(r'(\])\s*\n*\s*"([a-zA-Z_]+)"\s*:', r'\1, "\2":', repaired)

    try:
        data = json.loads(repaired)
        res = extract_expense_list(data)
        if res is not None:
            return res
    except Exception:
        pass

    # Strategy 3: Regex match outermost { ... } or [ ... ]
    for pattern in [r"\{.*\}", r"\[.*\]"]:
        match = re.search(pattern, repaired, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                res = extract_expense_list(data)
                if res is not None:
                    return res
            except Exception:
                pass

    # Strategy 4: Python ast.literal_eval (handles single quotes and unquoted values)
    try:
        py_str = repaired.replace("true", "True").replace("false", "False").replace("null", "None")
        data = ast.literal_eval(py_str)
        res = extract_expense_list(data)
        if res is not None:
            return res
    except Exception:
        pass

    # Strategy 5: Deterministic Regex Item Extractor (The Bulletproof Layer)
    expenses = []
    blocks = re.findall(r"\{[^{}]*\}", cleaned)
    for block in blocks:
        item_match = re.search(r'["\']?item["\']?\s*:\s*["\']([^"\']+)["\']', block, re.IGNORECASE)
        amt_match = re.search(r'["\']?amount["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)', block, re.IGNORECASE)
        payer_match = re.search(r'["\']?(?:paid_by|payer)["\']?\s*:\s*["\']([^"\']+)["\']', block, re.IGNORECASE)
        split_match = re.search(r'["\']?split_between["\']?\s*:\s*\[([^\]]*)\]', block, re.IGNORECASE)

        if amt_match:
            item_name = item_match.group(1).strip() if item_match else "Expense"
            try:
                amount_val = float(amt_match.group(1))
            except ValueError:
                continue
            paid_by_val = payer_match.group(1).strip() if payer_match else "Unknown"

            split_list = []
            if split_match:
                raw_split = split_match.group(1)
                names = re.findall(r'["\']([^"\']+)["\']', raw_split)
                if not names:
                    names = [n.strip() for n in raw_split.split(",") if n.strip()]
                split_list = names

            expenses.append({
                "item": item_name,
                "amount": amount_val,
                "paid_by": paid_by_val,
                "split_between": split_list
            })

    return expenses


def run_expense_extraction(transcript: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Chat Endpoint: POST https://api.sarvam.ai/v1/chat/completions
    Uses Sarvam-105B strictly to extract parsed expenses (item, amount, paid_by, split_between).
    No arithmetic is offloaded to the LLM.
    """
    url = "https://api.sarvam.ai/v1/chat/completions"
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json"
    }

    system_content = (
        "You are Parchi-Pay, an expert Indian expense-parsing assistant.\n"
        "Your ONLY job is to extract the expense items from the transcribed speech.\n"
        "Interpret Indian numerals accurately ('dedh sau'=150, 'dhai sau'=250, 'paune do sau'=175, 'paune char sau'=375, 'dedh hazaar'=1500, 'dhai hazaar'=2500, etc.).\n"
        "Format as valid JSON with key 'parsed_expenses':\n"
        "{\n"
        '  "parsed_expenses": [\n'
        '    {"item": "chai", "amount": 150, "paid_by": "Rahul", "split_between": ["Rahul", "Priya"]}\n'
        "  ]\n"
        "}\n"
        "Ensure all keys and strings are in double quotes with commas between items. Return RAW JSON ONLY."
    )

    models_to_try = ["sarvam-105b", "sarvam-105b-conversations"]
    raw_response = ""
    last_err = ""

    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": transcript}
            ],
            "temperature": 0.1,
            "max_tokens": 2048
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"].get("content")
                if content and content.strip():
                    raw_response = content.strip()
                    break
                else:
                    last_err = f"Model {model} returned empty content (finish_reason: {data['choices'][0].get('finish_reason')})"
            else:
                last_err = f"Model {model} failed ({resp.status_code}): {resp.text}"
        except Exception as e:
            last_err = f"Model {model} error: {str(e)}"

    if not raw_response:
        raise RuntimeError(f"Chat completion failed: {last_err}")

    # Use robust multi-tiered parser
    expenses = robust_parse_expenses(raw_response)

    # Normalize paid_by / payer
    for exp in expenses:
        if "payer" in exp and "paid_by" not in exp:
            exp["paid_by"] = exp["payer"]
        if "split_between" not in exp or not exp["split_between"]:
            payer_name = exp.get("paid_by", "")
            exp["split_between"] = [payer_name] if payer_name else []

    return expenses


def run_tts(summary_hindi: str, api_key: str) -> bytes:
    """
    TTS Endpoint: POST https://api.sarvam.ai/text-to-speech
    JSON payload={'text': summary_hindi, 'language_code': 'hi-IN', 'speaker': 'shubh', 'model': 'bulbul:v3'}
    Response has 'audios': [base64_string]
    """
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": summary_hindi,
        "language_code": "hi-IN",
        "speaker": "shubh",
        "model": "bulbul:v3"
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        # Fallback to inputs array if needed
        alt_payload = {
            "inputs": [summary_hindi],
            "target_language_code": "hi-IN",
            "speaker": "shubh",
            "model": "bulbul:v3"
        }
        resp = requests.post(url, headers=headers, json=alt_payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"TTS Error ({resp.status_code}): {resp.text}")

    audios = resp.json().get("audios", [])
    if not audios:
        raise RuntimeError("TTS returned empty audio list")

    return base64.b64decode(audios[0])


# ---------------------------------------------------------
# Streamlit Main App
# ---------------------------------------------------------
def main():
    st.markdown("<div class='title-banner'>Parchi-Pay (पर्ची-पे)</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-banner'>Voice-to-UPI Bill Settlement Tool with Deterministic Python Settlement Engine & Sarvam AI</div>", unsafe_allow_html=True)

    # API Key Configuration
    api_key = get_sarvam_api_key()
    with st.sidebar:
        st.markdown("### Configuration")
        user_key = st.text_input(
            "SARVAM_API_KEY",
            value=api_key,
            type="password",
            help="Read automatically from os.environ.get('SARVAM_API_KEY')"
        )
        if user_key:
            api_key = user_key.strip()
            os.environ["SARVAM_API_KEY"] = api_key
            st.success("● API Key Connected")
        else:
            st.error("SARVAM_API_KEY missing")

        st.markdown("---")
        st.markdown("""
        **Architecture & Execution:**
        - **STT:** `saaras:v4` (`mode='codemix'`)
        - **LLM Extraction:** `sarvam-105b` (Indian numerals & items only)
        - **Math Engine:** Pure Python deterministic zero-sum debt solver
        - **TTS:** `bulbul:v3` (`speaker='shubh'`, `hi-IN`)
        """)

    # Audio Input Selection
    col_input, col_preset = st.columns([2, 1])

    with col_input:
        # 1. Use st.audio_input('Record expense breakdown') to capture voice
        audio_clip = st.audio_input("Record expense breakdown")

    with col_preset:
        st.markdown("**Or test with sample audio:**")
        sample_choice = st.selectbox(
            "Select pre-recorded clip:",
            [
                "None",
                "Chai & Samosa (dedh sau / dhai sau)",
                "Dinner & Cab (paune char sau / dedh hazaar)",
                "Movie & Popcorn (paune do sau / saadhe teen sau)"
            ]
        )
        sample_audio_bytes = None
        if sample_choice.startswith("Chai") and os.path.exists("samples/chai_samosa.wav"):
            with open("samples/chai_samosa.wav", "rb") as f:
                sample_audio_bytes = f.read()
        elif sample_choice.startswith("Dinner") and os.path.exists("samples/dinner_cab.wav"):
            with open("samples/dinner_cab.wav", "rb") as f:
                sample_audio_bytes = f.read()
        elif sample_choice.startswith("Movie") and os.path.exists("samples/popcorn_tickets.wav"):
            with open("samples/popcorn_tickets.wav", "rb") as f:
                sample_audio_bytes = f.read()

    # Determine Active Audio
    active_audio_bytes = None
    if audio_clip is not None:
        active_audio_bytes = audio_clip.read()
    elif sample_audio_bytes is not None:
        active_audio_bytes = sample_audio_bytes
        st.info("Using selected sample audio clip.")

    # 2. Add a 'Settle Bill' button
    st.markdown("---")
    settle_clicked = st.button("Settle Bill", type="primary", use_container_width=True, disabled=(active_audio_bytes is None))

    if settle_clicked:
        if not api_key:
            st.error("❌ Please provide a SARVAM_API_KEY in environment or sidebar.")
            return

        # 3. Show progress spinner through STT -> Sarvam-105B -> TTS
        with st.spinner("Processing expense through Sarvam AI & Python Settlement Engine..."):
            try:
                # Step 1: STT
                stt_progress = st.empty()
                stt_progress.info("🎙️ Transcribing audio via Saaras v4 (codemix mode)...")
                transcript = run_stt(active_audio_bytes, api_key)
                stt_progress.empty()

                if not transcript:
                    st.error("No speech detected in audio clip. Please try speaking again.")
                    return

                # Step 2: Sarvam-105B expense extraction
                llm_progress = st.empty()
                llm_progress.info("🧠 Parsing Indian numerals & extracting expenses via Sarvam-105B...")
                parsed_expenses = run_expense_extraction(transcript, api_key)
                llm_progress.empty()

                if not parsed_expenses:
                    st.warning("No expense items were recognized from the speech.")
                    return

                # Step 3: Pure Python deterministic debt minimization
                settlements, net_balances, total_paid, total_owed = compute_net_settlements(parsed_expenses)
                summary_hindi, summary_english = generate_settlement_summaries(settlements)

                # Step 4: TTS confirmation on deterministic summary
                tts_progress = st.empty()
                tts_progress.info("🔊 Synthesizing Hindi confirmation voice via Bulbul v3...")
                tts_audio_bytes = run_tts(summary_hindi, api_key)
                tts_progress.empty()

                st.session_state["result"] = {
                    "transcript": transcript,
                    "parsed_expenses": parsed_expenses,
                    "net_settlements": settlements,
                    "net_balances": net_balances,
                    "total_paid": total_paid,
                    "total_owed": total_owed,
                    "summary_hindi": summary_hindi,
                    "summary_english": summary_english,
                    "tts_audio_bytes": tts_audio_bytes
                }
                st.success("🎉 Bill Settled Deterministically with Exact Zero-Sum Math!")

            except Exception as e:
                st.error(f"Pipeline error: {str(e)}")
                st.exception(e)
                return

    # Render Results
    if "result" in st.session_state and st.session_state["result"]:
        res = st.session_state["result"]
        st.markdown("---")

        # 5. Play the base64-decoded Bulbul audio response via st.audio()
        st.markdown("<div class='section-header'><span class='section-tag'>Voice Note</span> Spoken Confirmation (Bulbul v3)</div>", unsafe_allow_html=True)
        audio_col, text_col = st.columns([1, 2])
        with audio_col:
            st.audio(res["tts_audio_bytes"], format="audio/wav")
        with text_col:
            st.markdown(f"<div class='hindi-box'><b>Hindi:</b> {res['summary_hindi']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='english-box'><b>English:</b> {res['summary_english']}</div>", unsafe_allow_html=True)

        st.caption(f"Transcribed Text (Saaras v4): *\"{res['transcript']}\"*")

        # Expense Breakdown Table
        st.markdown("<div class='section-header'><span class='section-tag'>Step 1</span> Parsed Expenses Breakdown</div>", unsafe_allow_html=True)
        if res["parsed_expenses"]:
            exp_rows = []
            for e in res["parsed_expenses"]:
                split_list = e.get("split_between", [])
                split_str = ", ".join(split_list) if split_list else "All"
                amt = float(e.get("amount", 0))
                per_head = amt / len(split_list) if split_list else amt
                exp_rows.append({
                    "Item": e.get("item", "Expense"),
                    "Amount (₹)": f"₹{amt:,.2f}",
                    "Paid By": e.get("paid_by", "-"),
                    "Split Between": split_str,
                    "Per Person (₹)": f"₹{per_head:,.2f}"
                })
            st.dataframe(exp_rows, use_container_width=True)

        # Net Balances Summary Table
        st.markdown("<div class='section-header'><span class='section-tag'>Step 2</span> Participant Balances (Zero-Sum Accounting)</div>", unsafe_allow_html=True)
        balance_rows = []
        for person in res["net_balances"]:
            t_paid = res["total_paid"].get(person, 0.0)
            t_owed = res["total_owed"].get(person, 0.0)
            net_b = res["net_balances"].get(person, 0.0)
            status_label = "Creditor (Receives)" if net_b > 0.01 else ("Debtor (Pays)" if net_b < -0.01 else "Settled")
            balance_rows.append({
                "Participant": person,
                "Total Paid (₹)": f"₹{t_paid:,.2f}",
                "Fair Share Owed (₹)": f"₹{t_owed:,.2f}",
                "Net Balance (₹)": f"₹{net_b:,.2f}",
                "Status": status_label
            })
        st.dataframe(balance_rows, use_container_width=True)

        # 6. For each debt settlement, render an instant QR code using the python 'qrcode' library for the upi_uri, along with metric cards showing who owes whom.
        st.markdown("<div class='section-header'><span class='section-tag'>Step 3</span> Net Debt Settlements & Instant UPI QR Codes</div>", unsafe_allow_html=True)
        settlements = res["net_settlements"]

        if not settlements:
            st.success("All balances are settled! No debts owed.")
        else:
            # Metric cards showing who owes whom
            st.markdown("<div class='sub-section-title'>Who Owes Whom (Minimized Pairwise Settlements)</div>", unsafe_allow_html=True)
            metric_cols = st.columns(min(len(settlements), 4))
            for idx, s in enumerate(settlements):
                m_col = metric_cols[idx % min(len(settlements), 4)]
                with m_col:
                    from_p = s.get("from_person", "Debtor")
                    to_p = s.get("to_person", "Creditor")
                    amt = float(s.get("amount", 0))
                    st.metric(
                        label=f"{from_p} ➔ {to_p}",
                        value=f"₹{amt:,.2f}",
                        help=f"{from_p} pays ₹{amt:,.2f} to {to_p}"
                    )

            st.markdown("<div class='sub-section-title'>Instant Scannable UPI QR Codes</div>", unsafe_allow_html=True)
            qr_cols = st.columns(min(len(settlements), 3))
            for idx, s in enumerate(settlements):
                q_col = qr_cols[idx % min(len(settlements), 3)]
                with q_col:
                    from_p = s.get("from_person", "Debtor")
                    to_p = s.get("to_person", "Creditor")
                    amt = float(s.get("amount", 0))
                    raw_upi = s.get("upi_uri", f"upi://pay?pa={to_p.lower()}@upi&pn={to_p}&am={amt:.2f}&tn=ParchiPay")

                    qr_png = create_upi_qr(raw_upi)
                    
                    st.markdown(f"""
                    <div class='settlement-card'>
                        <div class='card-title'>{from_p} pays {to_p}</div>
                        <div class='card-amount'>₹{amt:,.2f}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.image(qr_png, caption=f"Scan to pay {to_p} (₹{amt:,.2f})", use_container_width=True)
                    st.markdown(f"<div style='text-align:center;'><a href='{raw_upi}' class='upi-btn' target='_blank'>⚡ Pay ₹{amt:,.2f} via UPI</a></div>", unsafe_allow_html=True)
                    with st.expander("UPI Link Details"):
                        st.code(raw_upi, language="text")

        # Developer Debug Expander
        with st.expander("🛠️ Developer Inspector: Deterministic State"):
            st.json({
                "parsed_expenses": res["parsed_expenses"],
                "total_paid": res["total_paid"],
                "total_owed": res["total_owed"],
                "net_balances": res["net_balances"],
                "net_settlements": res["net_settlements"],
                "summary_hindi": res["summary_hindi"],
                "summary_english": res["summary_english"]
            })


if __name__ == "__main__":
    main()
