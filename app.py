import streamlit as st
import json
import requests
from google import genai
import PyPDF2
import time
from google.genai import Client

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="AI-Powered Document Orchestrator", layout="wide")
st.title("AI-Powered Document Orchestrator")

# Load secrets
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
N8N_WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]

# ✅ Initialize the Gemini client (new syntax for google-genai v1.49.0)
client = Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------
# EXTRACT TEXT FUNCTION
# ---------------------------------------------------------
def extract_text(file):
    """Extract text from PDF or text file."""
    if file.type == "application/pdf":
        reader = PyPDF2.PdfReader(file)
        return " ".join([(page.extract_text() or "") for page in reader.pages])
    else:
        return file.read().decode("utf-8", errors="ignore")

# ---------------------------------------------------------
# FILE UPLOAD
# ---------------------------------------------------------
uploaded_file = st.file_uploader("📁 Upload PDF or Text Document", type=["pdf", "txt"])
raw_text = ""

if uploaded_file:
    raw_text = extract_text(uploaded_file)
    #st.subheader("📝 Extracted Text (Preview)")
    #st.write(raw_text[:2000] + ("..." if len(raw_text) > 2000 else ""))

# ---------------------------------------------------------
# QUESTION INPUT
# ---------------------------------------------------------
#question = st.text_input("Ask a question about the document")

if uploaded_file:
    st.subheader("⚙️ Processing with AI...")

    with st.spinner("Analyzing document and generating structured data..."):
        # Create the AI prompt
        prompt = f"""
You are an AI Resume Parser and Analyzer. 
Read the following résumé and return output strictly in JSON format with this schema:

{{
  "candidate_name": "string",
  "years_of_experience": "float or int",
  "skills": ["list", "of", "skills"],
  "current_role": "string",
  "education": "string",
  "email": "string",
  "summary": "string (short professional summary)",
  "recommendation": "string (AI-generated recommendation paragraph)"
}}

Resume Text:
\"\"\"{raw_text}\"\"\"

Rules:
- Extract only real information from the text.
- Do not invent any details.
- Keep the response as pure JSON (no explanation text).
"""

        # ✅ Call Gemini API (new format)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model="models/gemini-2.0-flash",
                    contents=[prompt]
                )
                break
            except Exception as e:
                if "RESOURCE_EXHAUSTED" in str(e):
                    st.warning("⏳ API limit reached. Retrying in 10 seconds...")
                    time.sleep(10)
                else:
                    st.error(f"❌ Unexpected error: {e}")
                    raise

        # Extract the text safely
        raw_output = getattr(response, "text", None)
        if not raw_output:
            try:
                raw_output = response.candidates[0].content.parts[0].text
            except Exception:
                st.error("⚠️ Could not extract AI response text.")
                raw_output = "{}"

        raw_output = raw_output.strip()

        # Try to parse JSON safely
        try:
            extracted_json = json.loads(raw_output)
        except:
            start = raw_output.find("{")
            end = raw_output.rfind("}")
            extracted_json = json.loads(raw_output[start:end + 1])

    # ---------------------------------------------------------
    # DISPLAY STRUCTURED OUTPUT
    # ---------------------------------------------------------
    st.subheader("📄 Extracted Candidate Profile")
    st.json(extracted_json)

    # Candidate Selection Criteria
    st.markdown("### 🧮 Candidate Selection Criteria")
    min_exp = st.slider("Minimum Required Experience (Years)", 0, 10, 1)
    required_skills = st.multiselect(
        "Required Skills (Candidate must have at least TWO):",
        ["Python", "SQL", "Power BI", "Tableau", "Deep Learning", "Excel"]
    )
    target_role = st.text_input("Target Role (optional - resume must mention this role)")
    candidate_skills = [s.lower().replace(" ", "") for s in extracted_json.get("skills", [])]
    required_lower = [s.lower().replace(" ", "") for s in required_skills]

    # Count how many required skills match candidate skills
    matches = sum(1 for skill in required_lower if skill in candidate_skills)

    meets_criteria = (
    extracted_json.get("years_of_experience", 0) >= min_exp and
    matches >= 2
    )

    if meets_criteria:
        st.success("✅ Candidate meets your selected criteria.")
    else:
        st.warning("⚠️ Candidate does not meet your selected criteria.")

    # Candidate Summary
    st.markdown("### 🧾 Candidate Summary")
    st.write(extracted_json.get("summary", "---"))

    # Recommendation
    st.markdown("### 🌟 Recommendation")
    st.write(extracted_json.get("recommendation", "---"))

    # Ask Question About Candidate
    st.markdown("### 💬 Ask Questions About This Candidate")
    user_question = st.text_input("Ask anything (e.g., 'What projects has this candidate worked on?')")

    # Send to Recruitment Workflow
    st.markdown("### 📨 Send Candidate to Recruitment Workflow")
    if st.button("Send to n8n Recruitment Workflow"):
        payload = {
            "candidate_data": extracted_json,
            "meets_criteria": meets_criteria,
            "question": user_question
        }
        if meets_criteria:
          with st.spinner("Sending candidate data to n8n workflow..."):
            resp = requests.post(N8N_WEBHOOK_URL, json=payload)
            try:
               result = resp.json()  # parse JSON returned from Respond to Webhook
            except:
               result = {"status": "❌ No valid JSON response"}

            if resp.status_code == 200:
               st.success(f"✅ Workflow completed: {result.get('status')}")
               #st.info(f"ℹ️ Message from n8n: {result}")
            else:
               st.error(f"❌ Failed to send to n8n (HTTP {resp.status_code}).")
               st.write(result)
        else:
          st.warning("⚠️ Candidate does not meet your selected criteria. No email sent.")