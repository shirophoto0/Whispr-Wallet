# =============================================================
# auth.py
# ระบบ Login แยกผู้ใช้ (คนละบัญชี เห็นแค่ข้อมูลตัวเอง) — รูปแบบเดียวกับที่ใช้ใน stock-scanner
# =============================================================
import streamlit as st


def check_login():
    """
    เช็คว่า login แล้วหรือยัง ถ้ายัง แสดงฟอร์ม login แล้วคืนค่า False (ให้ App.py หยุดทำงานต่อ)
    ถ้า login แล้ว คืนค่า True ให้ทำงานต่อได้ตามปกติ
    """
    if st.session_state.get('logged_in'):
        return True

    st.title("🔐 เข้าสู่ระบบ")
    with st.form("login_form"):
        username = st.text_input("ชื่อผู้ใช้")
        password = st.text_input("รหัสผ่าน", type="password")
        submitted = st.form_submit_button("เข้าสู่ระบบ", type="primary", use_container_width=True)

    if submitted:
        # อ่านรายชื่อผู้ใช้ที่ตั้งไว้ใน Streamlit Secrets (ดูรูปแบบตั้งค่าท้ายไฟล์)
        users = st.secrets.get("users", {})
        if username in users and str(users[username]) == password:
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.rerun()
        else:
            st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้องครับ")

    return False


def show_user_bar():
    """แสดงชื่อผู้ใช้ที่ login อยู่ + ปุ่มออกจากระบบ ไว้ที่แถบด้านข้าง"""
    with st.sidebar:
        st.markdown(f"👤 เข้าสู่ระบบในชื่อ: **{st.session_state.get('username', '')}**")
        if st.button("🚪 ออกจากระบบ (Logout)", use_container_width=True):
            logout()


def logout():
    st.session_state['logged_in'] = False
    st.session_state.pop('username', None)
    st.rerun()
