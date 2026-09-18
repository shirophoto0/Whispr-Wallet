# =============================================================
# backend_functions.py
# รวมฟังก์ชันเบื้องหลังทั้งหมด: เชื่อม Firebase Firestore (เก็บข้อมูล), Groq (แปลงเสียงเป็น
# ข้อความ), Claude (จัดหมวดหมู่รายการอัตโนมัติ)
# =============================================================
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, date
import json
import re

# หมวดหมู่เริ่มต้น — ใช้ตอนสร้างฐานข้อมูลครั้งแรก (ถ้ายังไม่มีเลยในระบบ)
DEFAULT_EXPENSE_CATEGORIES = [
    "อาหาร", "เดินทาง", "ที่พัก/บ้าน", "ช้อปปิ้ง", "บันเทิง",
    "สุขภาพ", "การศึกษา", "ค่าน้ำค่าไฟ/สาธารณูปโภค", "อื่นๆ"
]
DEFAULT_INCOME_CATEGORIES = [
    "เงินเดือน", "รายได้จากขายภาพสต็อก", "รายได้เสริมอื่นๆ", "อื่นๆ"
]


# =============================================================
# ส่วนที่ 1: เชื่อมต่อ Firebase Firestore
# =============================================================
@st.cache_resource
def get_firestore_client():
    """
    เชื่อมต่อ Firebase Firestore (แคชการเชื่อมต่อไว้ ไม่ต้องเชื่อมใหม่ทุกครั้งที่หน้าเว็บรันซ้ำ)
    อ่าน Service Account JSON จาก Streamlit Secrets (ต้องตั้งค่าไว้ก่อนใช้งาน — ดูคำแนะนำท้ายไฟล์)
    """
    if not firebase_admin._apps:
        cred_dict = dict(st.secrets["firebase_service_account"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()


# =============================================================
# ส่วนที่ 2: จัดการหมวดหมู่ (Categories)
# =============================================================
def load_categories(category_type):
    """
    โหลดรายชื่อหมวดหมู่ทั้งหมดจาก Firestore (แยกตามประเภท 'income' หรือ 'expense')
    ถ้ายังไม่เคยมีเลย จะสร้างหมวดหมู่เริ่มต้นให้อัตโนมัติในครั้งแรก
    """
    db = get_firestore_client()
    categories_ref = db.collection('categories').where('type', '==', category_type)
    docs = list(categories_ref.stream())

    if not docs:
        # ยังไม่เคยมีหมวดหมู่เลย สร้างชุดเริ่มต้นให้อัตโนมัติ
        default_list = DEFAULT_EXPENSE_CATEGORIES if category_type == 'expense' else DEFAULT_INCOME_CATEGORIES
        for name in default_list:
            db.collection('categories').add({'name': name, 'type': category_type})
        return default_list

    return sorted([doc.to_dict()['name'] for doc in docs])


def add_category_if_new(name, category_type):
    """เพิ่มหมวดหมู่ใหม่ลง Firestore ถ้ายังไม่มีอยู่แล้ว (กันหมวดหมู่ซ้ำ)"""
    db = get_firestore_client()
    existing = load_categories(category_type)
    if name not in existing:
        db.collection('categories').add({'name': name, 'type': category_type})


# =============================================================
# ส่วนที่ 3: บันทึก/โหลด/ลบ รายการรายรับ-รายจ่าย
# =============================================================
def save_transaction(trans_date, trans_type, amount, category, description, source):
    """
    บันทึกรายการลง Firestore
    trans_type: 'income' หรือ 'expense'
    source: 'manual' (พิมพ์เอง) หรือ 'voice' (พูดบันทึก)
    """
    db = get_firestore_client()
    db.collection('transactions').add({
        'date': str(trans_date),
        'type': trans_type,
        'amount': float(amount),
        'category': category,
        'description': description,
        'source': source,
        'created_at': datetime.now().isoformat(),
    })


@st.cache_data(ttl=30, show_spinner=False)
def load_transactions():
    """โหลดรายการทั้งหมด เรียงจากล่าสุดไปเก่าสุด (แคช 30 วินาที กันโหลดซ้ำถี่เกินไป)"""
    db = get_firestore_client()
    docs = db.collection('transactions').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id
        results.append(d)
    return results


def delete_transaction(doc_id):
    """ลบรายการออกจาก Firestore ตาม document ID"""
    db = get_firestore_client()
    db.collection('transactions').document(doc_id).delete()
    st.cache_data.clear()


# =============================================================
# ส่วนที่ 4: แปลงเสียงเป็นข้อความ (Groq Whisper API)
# =============================================================
def transcribe_audio(audio_bytes):
    """
    ส่งไฟล์เสียง (bytes) ไปให้ Groq แปลงเป็นข้อความ คืนค่าเป็นข้อความที่แปลงได้
    ใช้โมเดล whisper-large-v3-turbo (เร็วและรองรับภาษาไทยได้ดี)
    """
    from groq import Groq
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])

    # Groq API ต้องการไฟล์เป็น tuple (ชื่อไฟล์, ข้อมูลไฟล์)
    transcription = client.audio.transcriptions.create(
        file=("audio.wav", audio_bytes),
        model="whisper-large-v3-turbo",
        language="th",  # ระบุภาษาไทยตรงๆ ช่วยให้แปลงแม่นยำขึ้น
        response_format="text",
    )
    return str(transcription).strip()


# =============================================================
# ส่วนที่ 5: ให้ Claude วิเคราะห์ข้อความ แล้วแยกจำนวนเงิน + จัดหมวดหมู่อัตโนมัติ
# =============================================================
CATEGORIZE_PROMPT_TEMPLATE = """คุณเป็นผู้ช่วยจัดการบัญชีรายรับ-รายจ่ายส่วนตัว
อ่านข้อความนี้แล้วแยกข้อมูลออกมา: "{user_text}"

ประเภทที่เป็นไปได้: "income" (รายรับ) หรือ "expense" (รายจ่าย)

หมวดหมู่รายจ่ายที่มีอยู่แล้ว: {expense_categories}
หมวดหมู่รายรับที่มีอยู่แล้ว: {income_categories}

กรุณาตอบกลับเป็น JSON เท่านั้น ห้ามมีข้อความอื่นนอกเหนือจาก JSON เลยแม้แต่คำเดียว ห้ามใส่ ```json ครอบ
ตอบเริ่มต้นด้วยเครื่องหมาย {{ ทันที ตามโครงสร้างนี้เป๊ะๆ:

{{
  "type": "income หรือ expense",
  "amount": <ตัวเลขจำนวนเงิน ไม่มีหน่วย ไม่มีคอมมา>,
  "category": "<ชื่อหมวดหมู่ — เลือกจากรายการที่มีอยู่แล้วถ้าตรงกัน ถ้าไม่ตรงเลยให้ตั้งชื่อหมวดหมู่ใหม่ที่เหมาะสมสั้นๆ กระชับ>",
  "is_new_category": <true หรือ false — true ถ้าหมวดหมู่นี้ไม่เคยมีอยู่ในรายการเดิมเลย>,
  "description": "<คำอธิบายรายการสั้นๆ ตามที่ผู้ใช้พูด/พิมพ์มา>"
}}

หากแยกจำนวนเงินไม่ได้เลย ให้ใส่ amount เป็น 0"""


def categorize_with_ai(user_text, expense_categories, income_categories):
    """
    ส่งข้อความไปให้ Claude วิเคราะห์ แยกจำนวนเงิน+ประเภท+หมวดหมู่ คืนค่าเป็น dict
    ถ้า AI เห็นว่าควรสร้างหมวดหมู่ใหม่ จะไม่สร้างให้อัตโนมัติทันที — ให้ผู้ใช้ยืนยันก่อนเสมอ
    (แสดงในหน้ายืนยันรายการ) เพื่อกันหมวดหมู่ใหม่ที่ไม่ตั้งใจ/สะกดผิดเพี้ยนเข้าไปในระบบ
    """
    import anthropic
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

    # ใช้ .replace() แทน .format() เพราะข้อความที่ผู้ใช้พิมพ์/พูดมา อาจมีเครื่องหมายปีกกา {} ปนอยู่
    # โดยบังเอิญ ซึ่งจะไปชนกับ syntax ของ .format() ทำให้ error ได้
    prompt = (
        CATEGORIZE_PROMPT_TEMPLATE
        .replace("{user_text}", user_text)
        .replace("{expense_categories}", ", ".join(expense_categories))
        .replace("{income_categories}", ", ".join(income_categories))
    )

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    result_text = "".join(block.text for block in response.content if block.type == "text")

    # แกะ JSON ออกจากคำตอบด้วย Regex (ทนทานกว่าการเช็คแค่ว่าขึ้นต้นด้วย ```json)
    json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
    if not json_match:
        raise ValueError(f"AI ไม่ได้ตอบกลับมาเป็น JSON: {result_text[:200]}")

    parsed = json.loads(json_match.group(0))
    return parsed
