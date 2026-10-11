# 🧾 Parchi-Pay (पर्ची-पे)

> **Voice-to-UPI Bill Settlement Tool powered by Sarvam AI**

Parchi-Pay is a single-file Streamlit application that allows friends and groups to speak their group expenses naturally in code-mixed **Hinglish/Hindi**, automatically parses Indian numerals (*"dedh sau"*, *"dhai sau"*, *"paune do sau"*), calculates zero-sum net debts, and generates **scannable UPI QR codes** and spoken voice settlement confirmations.

Built for the **Sarvam AI Hackathon**.

---

## 🏛️ Pipeline Architecture

```text
[Spoken Audio Clip]
       │
       ▼ (POST https://api.sarvam.ai/speech-to-text)
1. Saaras v4 (mode="codemix")
   Transcribes code-mixed Hinglish speech, Indian numerals, and colloquial slang
       │
       ▼ Raw Transcript
2. Sarvam-105B (POST https://api.sarvam.ai/v1/chat/completions)
   Extracts expenses, calculates zero-sum net debts, and generates UPI deep links
       │
       ▼ JSON Payload (summary_hindi)
3. Bulbul v3 (POST https://api.sarvam.ai/text-to-speech)
   Synthesizes an immediate spoken settlement confirmation audio note
       │
       ▼
[Interactive Dashboard: UPI QR Codes + Settlement Table + Audio Playback]
```

---

## ✨ Features

- 🎙️ **Voice Expense Recording**: Capture spoken expense breakdowns using `st.audio_input()`.
- 🇮🇳 **Indian Numeral Understanding**: Intelligently handles colloquial numbers like *dedh sau* (150), *dhai sau* (250), *paune do sau* (175), *dedh hazaar* (1500), etc.
- ⚖️ **Zero-Sum Debt Settlement**: Minimizes transactions and computes exact net dues.
- 📱 **Instant UPI QR Codes & Deep Links**: Generates scannable QR codes for PhonePe, Google Pay, Paytm, and BHIM with `upi://pay?pa={name}@upi&pn={name}&am={amount}&tn=ParchiPay`.
- 🔊 **Voice Confirmation (Bulbul v3)**: Speaks out crisp Hindi confirmation audio (`speaker='shubh'`).
- 🎧 **Pre-recorded Samples**: Includes test audio clips for quick testing.

---

## 🚀 Quickstart

### 1. Clone the repository
```bash
git clone https://github.com/soumil-kumar/parchi-pay.git
cd parchi-pay
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set your Sarvam AI API Key
```bash
export SARVAM_API_KEY="your_api_key_here"  # On Linux/macOS
# or
$env:SARVAM_API_KEY="your_api_key_here"     # On Windows PowerShell
```

### 4. Run the Streamlit Application
```bash
streamlit run app.py
```

The app will be available at `http://localhost:8501`.

---

## 📂 Project Structure

```
├── app.py                # Main single-file Streamlit application
├── requirements.txt      # Project dependencies
├── samples/              # Pre-recorded test Hinglish expense clips
│   ├── chai_samosa.wav
│   ├── dinner_cab.wav
│   └── popcorn_tickets.wav
├── .env.example          # Sample environment file
└── README.md             # Project documentation
```
