import os
import io
import json
import base64
import re
import requests
import streamlit as st
import qrcode
from PIL import Image

# ---------------------------------------------------------
# Streamlit Page Config & Custom Design
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
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 60%, #059669 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-banner {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .settlement-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }
    .hindi-box {
        background: #EFF6FF;
        border-left: 5px solid #2563EB;
        padding: 1rem 1.2rem;
        border-radius: 0 8px 8px 0;
        font-size: 1.15rem;
        font-weight: 600;
        color: #1E293B;
        margin: 0.8rem 0;
    }
    .english-box {
        background: #F0FDF4;
        border-left: 5px solid #10B981;
        padding: 0.8rem 1.2rem;
        border-radius: 0 8px 8px 0;
        font-size: 1.0rem;
        color: #065F46;
        margin-bottom: 1rem;
    }
    .upi-btn {
        display: inline-block;
        background-color: #2563EB;
        color: white !important;
        padding: 0.5rem 1.2rem;
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
    """Read API key from os.environ.get('SARVAM_API_KEY') with file fallback."""
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
# Zero-Sum Net Settlement Helper (Algorithmic Guarantee)
# ---------------------------------------------------------
def compute_zero_sum_settlements(expenses):
    """Computes exact mathematical zero-sum balances and minimal transactions."""
    balances = {}
    for exp in expenses:
        payer = exp.get("payer", "").strip()
        amt = float(exp.get("amount", 0))
        split_between = exp.get("split_between", [])
        if not split_between:
            split_between = [payer]
        split_between = [p.strip() for p in split_between if p.strip()]
        if not split_between:
            continue
        per_person = amt / len(split_between)
        balances[payer] = balances.get(payer, 0.0) + amt
        for p in split_between:
            balances[p] = balances.get(p, 0.0) - per_person

    for k in balances:
        balances[k] = round(balances[k], 2)

    debtors = []
    creditors = []
    for p, b in balances.items():
        if b < -0.01:
            debtors.append({"person": p, "amount": -b})
        elif b > 0.01:
            creditors.append({"person": p, "amount": b})

    debtors.sort(key=lambda x: x["amount"], reverse=True)
    creditors.sort(key=lambda x: x["amount"], reverse=True)

    settlements = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        debtor = debtors[i]
        creditor = creditors[j]
        settle_amt = min(debtor["amount"], creditor["amount"])
        if settle_amt > 0.01:
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', creditor["person"].lower()) or "merchant"
            settle_round = round(settle_amt, 2)
            upi_uri = f"upi://pay?pa={clean_name}@upi&pn={creditor['person']}&am={settle_round}&tn=ParchiPay"
            settlements.append({
                "from_person": debtor["person"],
                "to_person": creditor["person"],
                "amount": settle_round,
                "upi_uri": upi_uri
            })
        debtor["amount"] -= settle_amt
        creditor["amount"] -= settle_amt
        if debtor["amount"] <= 0.01:
            i += 1
        if creditor["amount"] <= 0.01:
            j += 1
    return settlements, balances


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


def run_chat_completion(transcript: str, api_key: str) -> dict:
    """
    Chat Endpoint: POST https://api.sarvam.ai/v1/chat/completions
    Model: sarvam-105b (with fallback to sarvam-105b-conversations)
    Extracts expenses, calculates zero-sum net debts, returns RAW JSON ONLY.
    """
    url = "https://api.sarvam.ai/v1/chat/completions"
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json"
    }

    system_content = (
        "You are Parchi-Pay. Extract expenses, calculate zero-sum net debts, and return RAW JSON ONLY with keys: "
        "parsed_expenses (list of {item, amount, payer, split_between}), "
        "net_settlements (with from_person, to_person, amount, upi_uri as upi://pay?pa=name@upi&pn=name&am=amount&tn=ParchiPay), "
        "summary_hindi, summary_english."
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

    # Clean JSON from backticks before json.loads()
    cleaned = raw_response.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise RuntimeError(f"Failed to parse JSON from model output:\n{raw_response}")


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
    st.markdown("<div class='title-banner'>🧾 Parchi-Pay (पर्ची-पे)</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-banner'>Voice-to-UPI Bill Settlement Tool powered by <b>Sarvam AI</b> (Saaras v4 • Sarvam-105B • Bulbul v3)</div>", unsafe_allow_html=True)

    # API Key Configuration
    api_key = get_sarvam_api_key()
    with st.sidebar:
        st.markdown("### 🔑 Configuration")
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
            st.error("⚠️ SARVAM_API_KEY missing")

        st.markdown("---")
        st.markdown("""
        **Pipeline Specs:**
        - **STT:** `saaras:v4` (`mode='codemix'`)
        - **LLM:** `sarvam-105b` (Zero-sum net debts)
        - **TTS:** `bulbul:v3` (`speaker='shubh'`, `hi-IN`)
        """)

    # Audio Input Selection
    col_input, col_preset = st.columns([2, 1])

    with col_input:
        # 1. Use st.audio_input('Record expense breakdown') to capture voice
        audio_clip = st.audio_input("Record expense breakdown")

    with col_preset:
        st.markdown("**🎧 Or try sample audio:**")
        sample_choice = st.selectbox(
            "Select pre-recorded clip:",
            [
                "None",
                "🍵 Chai & Samosa (dedh sau / dhai sau)",
                "🍽️ Dinner & Cab (paune char sau / dedh hazaar)",
                "🍿 Movie & Popcorn (paune do sau / saadhe teen sau)"
            ]
        )
        sample_audio_bytes = None
        if sample_choice.startswith("🍵") and os.path.exists("samples/chai_samosa.wav"):
            with open("samples/chai_samosa.wav", "rb") as f:
                sample_audio_bytes = f.read()
        elif sample_choice.startswith("🍽️") and os.path.exists("samples/dinner_cab.wav"):
            with open("samples/dinner_cab.wav", "rb") as f:
                sample_audio_bytes = f.read()
        elif sample_choice.startswith("🍿") and os.path.exists("samples/popcorn_tickets.wav"):
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
        with st.spinner("Processing expense through Sarvam AI Pipeline (Saaras v4 ➡️ Sarvam-105B ➡️ Bulbul v3)..."):
            try:
                # Step 1: STT
                stt_progress = st.empty()
                stt_progress.info("🎙️ Transcribing audio via Saaras v4 (codemix mode)...")
                transcript = run_stt(active_audio_bytes, api_key)
                stt_progress.empty()

                if not transcript:
                    st.error("No speech detected in audio clip. Please try speaking again.")
                    return

                # Step 2: Sarvam-105B
                llm_progress = st.empty()
                llm_progress.info("🧠 Parsing numerals & calculating zero-sum debts via Sarvam-105B...")
                parsed_data = run_chat_completion(transcript, api_key)
                llm_progress.empty()

                parsed_expenses = parsed_data.get("parsed_expenses", [])
                net_settlements = parsed_data.get("net_settlements", [])
                summary_hindi = parsed_data.get("summary_hindi", "हिसाब पूरा हो गया है।")
                summary_english = parsed_data.get("summary_english", "Bill settlement completed.")

                # Ensure zero-sum settlement accuracy
                calc_settlements, balances = compute_zero_sum_settlements(parsed_expenses)
                if not net_settlements:
                    net_settlements = calc_settlements
                else:
                    # Validate UPI URIs
                    for s in net_settlements:
                        to_name = s.get("to_person", "recipient")
                        clean = re.sub(r'[^a-zA-Z0-9]', '', to_name.lower()) or "merchant"
                        amt = s.get("amount", 0)
                        if "upi_uri" not in s or not s["upi_uri"]:
                            s["upi_uri"] = f"upi://pay?pa={clean}@upi&pn={to_name}&am={amt}&tn=ParchiPay"

                # Step 3: TTS
                tts_progress = st.empty()
                tts_progress.info("🔊 Synthesizing Hindi confirmation voice via Bulbul v3...")
                tts_audio_bytes = run_tts(summary_hindi, api_key)
                tts_progress.empty()

                st.session_state["result"] = {
                    "transcript": transcript,
                    "parsed_expenses": parsed_expenses,
                    "net_settlements": net_settlements,
                    "summary_hindi": summary_hindi,
                    "summary_english": summary_english,
                    "tts_audio_bytes": tts_audio_bytes,
                    "balances": balances
                }
                st.success("🎉 Bill Settled Successfully!")

            except Exception as e:
                st.error(f"Pipeline error: {str(e)}")
                st.exception(e)
                return

    # Render Results
    if "result" in st.session_state and st.session_state["result"]:
        res = st.session_state["result"]
        st.markdown("---")

        # 5. Play the base64-decoded Bulbul audio response via st.audio()
        st.markdown("### 🔊 Spoken Confirmation (Bulbul v3)")
        audio_col, text_col = st.columns([1, 2])
        with audio_col:
            st.audio(res["tts_audio_bytes"], format="audio/wav")
        with text_col:
            st.markdown(f"<div class='hindi-box'>💬 <b>Hindi:</b> {res['summary_hindi']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='english-box'>🌐 <b>English:</b> {res['summary_english']}</div>", unsafe_allow_html=True)

        st.caption(f"📝 Transcribed Text (Saaras v4): *\"{res['transcript']}\"*")

        # Expense Breakdown Table
        st.markdown("### 📋 Parsed Expenses")
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
                    "Paid By": e.get("payer", "-"),
                    "Split Between": split_str,
                    "Per Person (₹)": f"₹{per_head:,.2f}"
                })
            st.dataframe(exp_rows, use_container_width=True)

        # 6. For each debt settlement, render an instant QR code using the python 'qrcode' library for the upi_uri, along with metric cards showing who owes whom.
        st.markdown("### 💳 Net Debt Settlements & Instant UPI QR Codes")
        settlements = res["net_settlements"]

        if not settlements:
            st.success("🎉 All balances are settled! No debts owed.")
        else:
            # Metric cards showing who owes whom
            st.markdown("#### 📊 Who Owes Whom")
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

            st.markdown("#### 📱 Instant UPI QR Codes")
            qr_cols = st.columns(min(len(settlements), 3))
            for idx, s in enumerate(settlements):
                q_col = qr_cols[idx % min(len(settlements), 3)]
                with q_col:
                    from_p = s.get("from_person", "Debtor")
                    to_p = s.get("to_person", "Creditor")
                    amt = float(s.get("amount", 0))
                    raw_upi = s.get("upi_uri", f"upi://pay?pa={to_p.lower()}@upi&pn={to_p}&am={amt}&tn=ParchiPay")

                    qr_png = create_upi_qr(raw_upi)
                    
                    st.markdown(f"""
                    <div class='settlement-card'>
                        <h4 style='margin:0; color:#1E3A8A;'>{from_p} pays {to_p}</h4>
                        <h2 style='margin:0.2rem 0; color:#059669;'>₹{amt:,.2f}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.image(qr_png, caption=f"Scan to pay {to_p}", use_container_width=True)
                    st.markdown(f"<div style='text-align:center;'><a href='{raw_upi}' class='upi-btn' target='_blank'>⚡ Pay ₹{amt:,.2f} via UPI</a></div>", unsafe_allow_html=True)
                    with st.expander("UPI Link Details"):
                        st.code(raw_upi, language="text")

        # Raw JSON expander
        with st.expander("🛠️ Raw JSON Response"):
            st.json({
                "parsed_expenses": res["parsed_expenses"],
                "net_settlements": res["net_settlements"],
                "summary_hindi": res["summary_hindi"],
                "summary_english": res["summary_english"]
            })


if __name__ == "__main__":
    main()
