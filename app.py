# app.py — Pest detector (visual refresh to match reference screenshot)

import os
import io
import json
import base64
from typing import List, Dict, Any

import streamlit as st
from PIL import Image
from gtts import gTTS
from dotenv import load_dotenv
import google.generativeai as genai

# ==== Secrets / Env ====
load_dotenv()
def secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

GEMINI_API_KEY = secret("GEMINI_API_KEY")
st.set_page_config(page_title="Pest detector", layout="centered")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found. Add it to .streamlit/secrets.toml or .env")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-1.5-flash"

# ==== Design ====
st.markdown("""
<style>
/* Page */
html, body, .stApp { background:#f7fafc !important; color:#0f172a; }

/* Top green strip (like your screenshot) */
.stApp::before{
  content:"";
  position:fixed; left:0; top:0; right:0; height:48px;
  background:#2e7d32; z-index:0;
}

/* tokens */
:root{
  --ink:#0f172a; --muted:#6b7280; --card:#ffffff; --border:rgba(15,23,42,.10);
  --shadow:0 10px 26px rgba(15,23,42,.08);
  --brand:#2563eb;      /* analyze button (blue) */
  --accent:#10b981;     /* emerald for product buttons if needed */
  --accent2:#34d399;
  --warn:#f59e0b; --warmpanel:#fff7ed; /* orange + warm canvas */
}

/* header */
.header{ position:relative; z-index:1; margin:10px 0 14px; }
.header h2{ margin:0; font-weight:800; letter-spacing:.2px; }
.header .tag{ color:var(--muted); }

/* cards */
.card{ background:var(--card); border:1px solid var(--border); border-radius:16px; box-shadow:var(--shadow); }
.card-body{ padding:16px 18px; }
.card + .card{ margin-top:14px; }
hr.sep{ border:none; border-top:1px solid var(--border); margin:12px 0; }

/* tabs (clean, light) */
.stTabs [data-baseweb="tab-list"]{ gap:8px; padding:6px; border-radius:12px; background:#fff; border:1px solid var(--border); box-shadow:var(--shadow); }
.stTabs [data-baseweb="tab"]{ border-radius:10px; padding:10px 14px; font-weight:600; color:#1f2937; background:#f8fafc; border:1px solid #e5e7eb; }
.stTabs [aria-selected="true"]{ color:#0b1220 !important; background:#fff !important; border:1px solid #93c5ae !important; }

/* primary (Analyze) */
.stButton > button[kind="primary"]{
  background:linear-gradient(135deg, var(--brand), #3b82f6) !important;
  color:#fff !important; border:0 !important; border-radius:12px !important;
  padding:.7rem 1.25rem !important; font-weight:700 !important;
  box-shadow:0 14px 28px rgba(37,99,235,.28) !important;
}

/* secondary reset (kept working + green gradient look) */
.secbtn button{
  background:linear-gradient(135deg,#10b981,#34d399) !important;
  color:#fff !important; border:0 !important; border-radius:12px !important;
  padding:.70rem 1.15rem !important; font-weight:700 !important;
  box-shadow:0 12px 24px rgba(16,185,129,.25) !important;
  width:100%;
}

/* "Detected Issues" panel — warm, with orange rail */
.issue-panel{
  background:var(--warmpanel);
  border:1px solid #fde7c7;
  border-left:6px solid var(--warn);
  border-radius:14px;
  padding:14px;
  box-shadow:0 6px 14px rgba(245,158,11,.12);
}

/* badges + progress */
.badge{ display:inline-block; padding:4px 10px; border-radius:999px; font-weight:700; font-size:.78rem; }
.badge-type{ background:#e0f2fe; color:#075985; border:1px solid #bae6fd; }
.badge-low{ background:#dcfce7; color:#166534; border:1px solid #86efac; }
.badge-med{ background:#fef9c3; color:#92400e; border:1px solid #fde68a; }
.badge-high{ background:#fee2e2; color:#991b1b; border:1px solid #fecaca; }

.progress-wrap{ width:100%; background:#f1f5f9; border-radius:10px; border:1px solid #e5e7eb; height:12px; overflow:hidden; }
.progress-bar{ height:100%; border-radius:10px; background:linear-gradient(90deg,#f59e0b,#f97316); }

/* image preview on summary (non-overlapping) */
.summary-img{ max-width: 340px; }
.summary-img img{ width:100%; height:auto; display:block; border-radius:12px; border:1px solid #e5e7eb; }
.caption{ color:#64748b; font-size:.9rem; margin-top:6px; text-align:center; }

/* product card tweaks */
.pcard{ background:#fff; border:1px solid var(--border); border-radius:14px; box-shadow:var(--shadow); padding:12px 12px 10px; }
.pcard h5{ margin:2px 0 6px; font-size:1rem; }
.pbtn a{
  display:inline-block; margin-top:8px; padding:6px 12px; border-radius:12px; text-decoration:none; color:#fff;
  background:linear-gradient(135deg,#10b981,#34d399); font-weight:800; box-shadow:0 12px 24px rgba(16,185,129,.25);
}
</style>
""", unsafe_allow_html=True)

# ==== helpers ====
def encode_image_bytes(img_bytes: bytes) -> str:
    return base64.b64encode(img_bytes).decode("utf-8")

def to_jpeg_bytes(raw_bytes: bytes) -> bytes:
    try:
        im = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
    except Exception:
        return raw_bytes

def image_html(img_bytes: bytes, alt: str = "plant"):
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    st.markdown(f"""
    <div class="summary-img">
      <img src="data:image/jpeg;base64,{b64}" alt="{alt}">
      <div class="caption">{alt}</div>
    </div>
    """, unsafe_allow_html=True)

# OSU links
def osu_extension_links(plant: str, disease: str) -> List[Dict[str, str]]:
    q = "+".join([plant.strip(), disease.strip()]) if plant and disease else (plant or disease or "plant disease")
    return [
        {"title":"OSU Extension fact sheets (search)",
         "link": f"https://www.google.com/search?q=site:ohioline.osu.edu+{q}",
         "snippet":"Ohio State University Extension fact sheets related to your query."},
        {"title":"OSU CFAES plant problem resources (search)",
         "link": f"https://www.google.com/search?q=site:u.osu.edu+{q}+plant+problem",
         "snippet":"Additional OSU resources and diagnostics."},
    ]

# curated catalog (unchanged)
CATALOG = {
    "bacterial":[{"active":"copper","title":"Copper Fungicide (Bonide / Southern Ag) — search",
                  "link":"https://www.amazon.com/s?k=Copper+Fungicide+Bonide+Southern+Ag",
                  "snippet":"Copper (fixed copper, copper soap) for bacterial leaf spots and cankers."}],
    "fungal":[
        {"active":"chlorothalonil","title":"Daconil (chlorothalonil) — search",
         "link":"https://www.amazon.com/s?k=Daconil+chlorothalonil+fungicide",
         "snippet":"Broad-spectrum protectant for many leaf blights and fruit rots."},
        {"active":"mancozeb","title":"Mancozeb (with zinc) — search",
         "link":"https://www.amazon.com/s?k=mancozeb+fungicide+zinc",
         "snippet":"Protectant fungicide—often rotated with other modes of action."},
        {"active":"sulfur","title":"Sulfur (wettable / dust) — search",
         "link":"https://www.amazon.com/s?k=sulfur+fungicide+garden",
         "snippet":"(OMRI/Organic) Effective for powdery mildew; avoid near oils/heat per label."},
        {"active":"potassium bicarbonate","title":"Potassium bicarbonate (e.g., GreenCure) — search",
         "link":"https://www.amazon.com/s?k=potassium+bicarbonate+fungicide",
         "snippet":"(OMRI/Organic) Contact fungicide for powdery mildew; rotate actives."},
    ],
    "insect":[
        {"active":"spinosad","title":"Monterey Garden Insect Spray (Spinosad) — search",
         "link":"https://www.amazon.com/s?k=Monterey+Garden+Insect+Spray+Spinosad",
         "snippet":"(OMRI/Organic) Thrips, leafminers, caterpillars; avoid spraying during bloom."},
        {"active":"bt","title":"Bt (Bacillus thuringiensis kurstaki) — search",
         "link":"https://www.amazon.com/s?k=Bt+kurstaki+garden",
         "snippet":"(OMRI/Organic) Caterpillar-specific bioinsecticide."},
        {"active":"insecticidal soap","title":"Insecticidal soap (potassium salts) — search",
         "link":"https://www.amazon.com/s?k=insecticidal+soap+Safer+Brand",
         "snippet":"(OMRI/Organic) Soft-bodied pests like aphids/whiteflies; good coverage needed."},
        {"active":"horticultural oil","title":"Horticultural oil (All Seasons) — search",
         "link":"https://www.amazon.com/s?k=horticultural+oil+all+seasons+spray",
         "snippet":"(OMRI/Organic) Smothers eggs/soft-bodied insects & some mites."},
        {"active":"pyrethrin","title":"Pyrethrin concentrate — search",
         "link":"https://www.amazon.com/s?k=pyrethrin+concentrate+garden",
         "snippet":"Quick knockdown; rotate to reduce resistance."},
        {"active":"azadirachtin","title":"Azadirachtin / Neem (cold-pressed) — search",
         "link":"https://www.amazon.com/s?k=azadirachtin+neem+oil+concentrate",
         "snippet":"(OMRI/Organic) Growth regulator/repellent; check PHI/REI."},
    ]
}
ACTIVE_KEYWORDS = {c["active"] for group in CATALOG.values() for c in group}

def extract_actives(text: str) -> List[str]:
    text_l = (text or "").lower()
    found, seen = [], set()
    for active in ACTIVE_KEYWORDS:
        if active in text_l and active not in seen:
            seen.add(active); found.append(active)
    return found

def detect_category(disease_text: str, treatment_text: str) -> str:
    dl = (disease_text or "").lower() + " " + (treatment_text or "").lower()
    if any(w in dl for w in ["bacteria","bacterial","canker","ooze"]): return "bacterial"
    if any(w in dl for w in ["rust","blight","mildew","anthracnose","rot","fung"]): return "fungal"
    if any(w in dl for w in ["aphid","whitefly","thrip","mite","borer","worm","caterpillar","beetle","leafminer","insect"]): return "insect"
    return "insect"

def curated_products(recommendation: str, disease_name: str) -> List[Dict[str, str]]:
    category = detect_category(disease_name, recommendation)
    actives = extract_actives(recommendation)
    catalog_list = CATALOG.get(category, [])
    if not catalog_list: return []
    if actives:
        chosen = []
        for a in actives:
            for item in catalog_list:
                if item["active"] == a: chosen.append(item)
        if len(chosen) < 2:
            for item in catalog_list:
                if item not in chosen:
                    chosen.append(item)
                    if len(chosen) >= 2: break
        return chosen[:4]
    return catalog_list[:2]

# ==== Gemini ====
def analyze_plant(image_b64: str, plant_name: str) -> Dict[str, Any]:
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = f"""
    Analyze this image of a {plant_name} plant (United States context).
    Return ONLY valid JSON in this exact shape:
    {{
      "results": [
        {{"type":"disease|pest","name":"...","probability":"%","symptoms":"...","causes":"...","severity":"Low|Medium|High","spreading":"...","treatment":"Short, precise treatment text with active ingredients if possible","prevention":"..."}}
      ],
      "is_healthy": true|false,
      "confidence": "%"
    }}
    If the plant looks healthy, set "is_healthy": true and "results": [].
    """
    parts = [{"mime_type":"image/jpeg","data": image_b64}]
    resp = model.generate_content([prompt] + parts)
    text = resp.text or ""
    s, e = text.find("{"), text.rfind("}") + 1
    if s < 0 or e <= 0:
        return {"error":"Failed to parse the model response","raw":text}
    try:
        return json.loads(text[s:e])
    except Exception as ex:
        return {"error": f"Invalid JSON: {ex}", "raw": text[s:e]}

# ==== Audio ====
def synthesize_summary(analysis: Dict[str, Any], plant_name: str) -> bytes:
    if analysis.get("is_healthy"):
        summary = f"Your {plant_name} plant appears healthy. Keep doing what you are doing."
    elif analysis.get("results"):
        parts = []
        for r in analysis["results"]:
            parts.append(
                f"{r.get('name','Unknown')}. Symptoms: {r.get('symptoms','')}. "
                f"Treatment: {r.get('treatment','')}. Prevention: {r.get('prevention','')}."
            )
        summary = "Detected issues: " + " ".join(parts)
    else:
        summary = "Analysis inconclusive."
    fp = io.BytesIO()
    try:
        gTTS(text=summary, lang="en", slow=False).write_to_fp(fp)
        fp.seek(0); return fp.read()
    except Exception:
        return b""

# ==== small UI helpers ====
def severity_badge(sev: str) -> str:
    s = (sev or "").lower()
    if s.startswith("high"): cls = "badge-high"
    elif s.startswith("low"): cls = "badge-low"
    else: cls = "badge-med"
    return f'<span class="badge {cls}">{sev or "—"} Severity</span>'

def type_badge(tp: str) -> str:
    return f'<span class="badge badge-type">{tp or "—"}</span>'

def progress_bar(pct: str) -> str:
    try:
        v = int(str(pct).replace("%","").strip())
    except Exception:
        v = 0
    v = max(0, min(100, v))
    return f'''
      <div class="progress-wrap"><div class="progress-bar" style="width:{v}%"></div></div>
      <div class="small" style="margin-top:4px;"><strong>{v}%</strong></div>
    '''

# ==== Header ====
st.markdown("""
<div class="header">
  <h2>Pest detector</h2>
  <div class="tag">Image-based diagnosis with OSU-aligned guidance & product actives.</div>
</div>
""", unsafe_allow_html=True)

# ==== Inputs (preview width=240 for 50% smaller) ====
with st.container():
    st.markdown('<div class="card"><div class="card-body">', unsafe_allow_html=True)
    plant_name = st.text_input("Plant name", placeholder="e.g., Tomato, Apple, Corn")

    tab1, tab2 = st.tabs(["Upload", "Camera"])
    image_bytes: bytes = b""

    with tab1:
        c1, c2 = st.columns([1, 2])
        with c1:
            file = st.file_uploader("Upload a plant image", type=["jpg","jpeg","png"])
        with c2:
            if file:
                image_bytes = file.read()
                st.image(image_bytes, caption="Preview", width=240, output_format="JPEG")
    with tab2:
        c1, c2 = st.columns([1, 2])
        with c1:
            pic = st.camera_input("Take a photo (mobile friendly)")
        with c2:
            if pic:
                image_bytes = pic.getvalue()
                st.image(image_bytes, caption="Preview", width=240, output_format="JPEG")

    run_btn = st.button("Analyze", type="primary", disabled=not (plant_name and image_bytes))
    st.markdown('</div></div>', unsafe_allow_html=True)

# ==== Results ====
if run_btn and plant_name and image_bytes:
    with st.spinner("Analyzing image..."):
        jpeg_bytes = to_jpeg_bytes(image_bytes)
        b64 = encode_image_bytes(jpeg_bytes)
        result = analyze_plant(b64, plant_name)

    if "error" in result:
        st.error(result["error"]); st.stop()

    st.success("Analysis complete.")

    left, right = st.columns([1.0, 2.0])

    with left:
        st.markdown('<div class="card"><div class="card-body">', unsafe_allow_html=True)
        image_html(jpeg_bytes, alt=plant_name or "plant")

        st.markdown("### Analysis Summary")
        is_healthy = result.get("is_healthy", False)
        conf = result.get("confidence", "—")
        st.markdown(f"**Plant:** {plant_name or '—'}")
        st.markdown(f"**Status:** {'No issues detected' if is_healthy else 'Issues Detected'}")
        st.markdown(f"**Confidence:** {conf}")

        audio = synthesize_summary(result, plant_name or "your plant")
        if audio:
            st.markdown("**Audio Summary:**")
            st.audio(audio, format="audio/mp3")

        # Working reset button (kept)
        st.markdown('<div class="secbtn">', unsafe_allow_html=True)
        if st.button("Analyze another plant", key="reset_btn"):
            st.session_state.clear()
            st.experimental_rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div></div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="card"><div class="card-body">', unsafe_allow_html=True)
        st.markdown("### Detected Issues")

        if result.get("results"):
            for idx, r in enumerate(result["results"], start=1):
                name = r.get("name","Unknown")
                tp = r.get("type","—")
                prob = r.get("probability","0%")
                sev = r.get("severity","—")

                st.markdown(f'<div class="issue-panel">', unsafe_allow_html=True)
                st.markdown(f"**{idx}. {name}**  &nbsp; {type_badge(tp)}  &nbsp; {severity_badge(sev)}", unsafe_allow_html=True)
                st.markdown("**Probability:**")
                st.markdown(progress_bar(prob), unsafe_allow_html=True)

                st.markdown("**Symptoms:**");   st.write(r.get("symptoms","—"))
                st.markdown("**Causes:**");     st.write(r.get("causes","—"))
                st.markdown("**Spreading:**");  st.write(r.get("spreading","—"))
                st.markdown("**Treatment:**");  st.write(r.get("treatment","—"))
                st.markdown("**Prevention:**"); st.write(r.get("prevention","—"))
                st.markdown('</div>', unsafe_allow_html=True)
                st.markdown(' ', unsafe_allow_html=True)

            first_name = result["results"][0].get("name", plant_name)
            st.markdown("#### OSU Extension reading")
            for link in osu_extension_links(plant_name, first_name):
                st.markdown(f"- [{link['title']}]({link['link']})  \n  {link.get('snippet','')}")

            st.markdown('<hr class="sep"/>', unsafe_allow_html=True)
            st.markdown("#### Recommended products (OSU-aligned actives)")

            seen, items = set(), []
            for r in result["results"]:
                for p in curated_products(r.get("treatment",""), r.get("name","")):
                    if p["title"] not in seen:
                        seen.add(p["title"]); items.append(p)

            if items:
                for i in range(0, len(items), 2):
                    cols = st.columns(2)
                    for j in range(2):
                        if i+j < len(items):
                            p = items[i+j]
                            with cols[j]:
                                st.markdown(f"""
                                <div class="pcard">
                                  <h5>{p['title']}</h5>
                                  <div class="small">{p['snippet']}</div>
                                  <div class="pbtn"><a href="{p['link']}" target="_blank" rel="noopener">View product</a></div>
                                </div>
                                """, unsafe_allow_html=True)
            else:
                st.caption("No pesticide products recommended (e.g., viral issues). Focus on sanitation/prevention.")
        else:
            st.info("No issues detected.")

        st.markdown('</div></div>', unsafe_allow_html=True)
else:
    st.caption("Tip: On Streamlit Cloud this page is HTTPS, so the Camera tab works on phones.")




