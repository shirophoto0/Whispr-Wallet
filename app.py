# =============================================================
# App.py
# แอปบันทึกรายรับ-รายจ่ายส่วนตัว — รองรับพิมพ์เอง + พูดบันทึก + อ่านจากรูปภาพ (AI แปลงเสียง/รูปภาพ
# + จัดหมวดหมู่อัตโนมัติ) มีระบบ Login แยกผู้ใช้ (คนละบัญชี เห็นแค่ข้อมูลตัวเอง)
# 🆕 ปรับโครงสร้างเมนูจากแท็บแนวนอนด้านบน มาเป็นเมนู Sidebar แนวตั้งด้านซ้ายแทน (เหมือนที่ปรับให้
# stock-scanner ไปแล้วก่อนหน้านี้) และแยก "บันทึกรายการ" เป็น 2 แท็บย่อยแนวนอน (รายรับ/รายจ่าย)
# =============================================================
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from auth import check_login, show_user_bar
from theme import apply_theme, render_metric_card, get_theme_colors, style_plotly
from backend_functions import (
    load_categories, add_category_if_new, save_transaction,
    load_transactions, delete_transaction, update_transaction,
    delete_transactions_by_month, delete_all_transactions,
    transcribe_audio, categorize_with_ai, extract_transactions_from_image,
    load_categories_with_group, update_category_group,
    CATEGORY_GROUP_GENERAL, CATEGORY_GROUP_PAYROLL,
)

st.set_page_config(page_title="บันทึกรายรับ-รายจ่าย", page_icon="💰", layout="wide")
apply_theme()

# เช็ค Login ก่อนเสมอ — ถ้ายังไม่ได้ login จะแสดงฟอร์ม login แล้วหยุดทำงานตรงนี้เลย
if not check_login():
    st.stop()

show_user_bar()
current_user = st.session_state['username']

# โหลดหมวดหมู่ทั้งหมดไว้ล่วงหน้า (เฉพาะของผู้ใช้คนนี้เท่านั้น — ใช้ทุกส่วนของแอป)
expense_categories = load_categories('expense', current_user)
income_categories = load_categories('income', current_user)


# =============================================================
# 🆕 เมนู Sidebar แนวตั้ง (แทนแท็บแนวนอนเดิม)
# =============================================================
from streamlit_option_menu import option_menu

with st.sidebar:
    selected_menu = option_menu(
        menu_title="💰 เมนูหลัก",
        options=["บันทึกรายการ", "ประวัติรายการ", "สรุปภาพรวม"],
        icons=["pencil-square", "clock-history", "bar-chart-line"],
        default_index=0,
        key="main_menu",
    )


# =============================================================
# ฟังก์ชันย่อย: ฟอร์มบันทึกรายการแบบพิมพ์เอง (ใช้ร่วมกันทั้งแท็บรายรับ/รายจ่าย)
# fixed_type ถูกกำหนดตายตัวตามแท็บที่เรียกใช้ ('income' หรือ 'expense') — ผู้ใช้เลือกแท็บเองอยู่
# แล้ว จึงไม่ต้องมีตัวเลือก "ประเภท" ซ้ำอีกในฟอร์ม ลดขั้นตอนความสับสนลง
# =============================================================
def render_manual_entry(fixed_type, fixed_type_label):
    category_list = income_categories if fixed_type == 'income' else expense_categories

    with st.form(f"manual_entry_form_{fixed_type}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            trans_date = st.date_input("วันที่", value=date.today(), key=f"date_{fixed_type}")
            amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=10.0, format="%.2f", key=f"amount_{fixed_type}")
        with c2:
            category_choice = st.selectbox("หมวดหมู่", ["🤖 ให้ AI เลือกให้อัตโนมัติ"] + category_list, key=f"cat_{fixed_type}")
            description = st.text_area("รายละเอียด", placeholder="เช่น ค่าข้าวเที่ยงกับเพื่อน", key=f"desc_{fixed_type}")

        submitted = st.form_submit_button(f"💾 บันทึก{fixed_type_label}", type="primary", use_container_width=True)

    if submitted:
        if amount <= 0:
            st.warning("กรุณาระบุจำนวนเงินมากกว่า 0 ครับ")
            return

        if category_choice == "🤖 ให้ AI เลือกให้อัตโนมัติ":
            with st.spinner("AI กำลังเลือกหมวดหมู่ให้..."):
                try:
                    ai_result = categorize_with_ai(
                        description or f"{fixed_type_label} {amount} บาท",
                        expense_categories, income_categories
                    )
                    final_category = ai_result.get('category', 'อื่นๆ')
                    if ai_result.get('is_new_category'):
                        st.info(f"🆕 AI สร้างหมวดหมู่ใหม่ให้: **{final_category}**")
                        add_category_if_new(final_category, fixed_type, current_user)
                except Exception as e:
                    st.warning(f"AI จัดหมวดหมู่ไม่สำเร็จ ใช้หมวด 'อื่นๆ' แทน: {e}")
                    final_category = "อื่นๆ"
        else:
            final_category = category_choice

        save_transaction(trans_date, fixed_type, amount, final_category, description, "manual", current_user)
        st.cache_data.clear()
        st.success(f"✅ บันทึกสำเร็จ! {fixed_type_label} {amount:,.2f} บาท ({final_category})")
        st.rerun()


# =============================================================
# ฟังก์ชันย่อย: พูดบันทึก (ใช้ร่วมกันทั้งแท็บรายรับ/รายจ่าย)
# 🔧 ปรับปรุง: fixed_type มาจากแท็บที่เลือกไว้แล้วเสมอ (ไม่ให้ AI เดาประเภทจากคำพูดอีกต่อไป เพราะ
# ผู้ใช้เลือกแท็บ "รายรับ"/"รายจ่าย" ไว้ล่วงหน้าแล้ว บ่งบอกเจตนาชัดเจนกว่าให้ AI เดาจากคำพูด)
# =============================================================
def render_voice_entry(fixed_type, fixed_type_label):
    st.caption(f"กดปุ่มแล้วพูดบรรยายรายการ{fixed_type_label} เช่น \"ค่าข้าวเที่ยง 80 บาท\"")

    from streamlit_mic_recorder import mic_recorder

    # 🆕 ทำให้ปุ่มพูดบันทึกเป็น Floating Action Button ลอยอยู่กึ่งกลางด้านล่างจอ — เฉพาะตอนหน้าจอ
    # แคบ (มือถือ) เท่านั้น ผ่าน CSS media query (บนจอกว้าง/คอมพิวเตอร์ ยังคงแสดงแบบ inline ปกติ
    # เพราะลอยกลางจอกว้างจะดูแปลกและอาจบังเนื้อหาอื่น) ใช้ st.container(key=...) ซึ่ง Streamlit
    # จะสร้างคลาส CSS เฉพาะให้อัตโนมัติ (.st-key-{key}) ทำให้ style เจาะจงแค่ปุ่มนี้ตัวเดียวได้แม่นยำ
    # ไม่กระทบส่วนอื่นของหน้า — เว้นระยะจากขอบล่างด้วย env(safe-area-inset-bottom) เผื่อมือถือรุ่น
    # ใหม่ที่มี gesture bar ด้านล่างจอด้วย
    _fab_key = f"mic_fab_{fixed_type}"
    st.markdown(f"""
        <style>
        @media (max-width: 768px) {{
            div.st-key-{_fab_key} {{
                position: fixed;
                bottom: calc(20px + env(safe-area-inset-bottom, 0px));
                left: 50%;
                transform: translateX(-50%);
                z-index: 9999;
                background-color: white;
                border-radius: 50px;
                box-shadow: 0 4px 14px rgba(0,0,0,0.2);
                padding: 8px 14px;
                width: auto !important;
            }}
        }}
        </style>
    """, unsafe_allow_html=True)

    with st.container(key=_fab_key):
        audio = mic_recorder(start_prompt="🎤 เริ่มพูด", stop_prompt="⏹️ หยุดพูด", format="wav", key=f"voice_recorder_{fixed_type}")

    if not audio:
        return

    with st.spinner("กำลังแปลงเสียงเป็นข้อความ..."):
        try:
            transcribed_text = transcribe_audio(audio['bytes'])
        except Exception as e:
            st.error(f"❌ แปลงเสียงไม่สำเร็จ: {e}")
            return

    st.info(f"🗣️ ข้อความที่แปลงได้: \"{transcribed_text}\"")

    with st.spinner("AI กำลังวิเคราะห์และจัดหมวดหมู่..."):
        try:
            ai_result = categorize_with_ai(transcribed_text, expense_categories, income_categories)
        except Exception as e:
            st.error(f"❌ AI วิเคราะห์ไม่สำเร็จ: {e}")
            return

    # แสดงผลที่ AI วิเคราะห์ได้ ให้ผู้ใช้ตรวจสอบ/แก้ไขก่อนบันทึกจริงเสมอ
    st.markdown("##### ✅ ตรวจสอบก่อนบันทึก")
    with st.form(f"voice_confirm_form_{fixed_type}"):
        vc1, vc2 = st.columns(2)
        with vc1:
            confirm_date = st.date_input("วันที่", value=date.today(), key=f"vc_date_{fixed_type}")
            confirm_amount = st.number_input(
                "จำนวนเงิน (บาท)", min_value=0.0, step=10.0,
                value=float(ai_result.get('amount', 0)), format="%.2f", key=f"vc_amount_{fixed_type}"
            )
        with vc2:
            confirm_category_list = income_categories if fixed_type == 'income' else expense_categories
            _suggested = ai_result.get('category', 'อื่นๆ')
            _options = confirm_category_list + ([_suggested] if _suggested not in confirm_category_list else [])
            confirm_category = st.selectbox(
                "หมวดหมู่ (AI แนะนำไว้แล้ว แก้ไขได้)", _options,
                index=_options.index(_suggested) if _suggested in _options else 0,
                key=f"vc_cat_{fixed_type}"
            )
            confirm_description = st.text_area("รายละเอียด", value=ai_result.get('description', transcribed_text), key=f"vc_desc_{fixed_type}")

        voice_submitted = st.form_submit_button("💾 ยืนยันบันทึก", type="primary", use_container_width=True)

    if voice_submitted:
        if confirm_amount <= 0:
            st.warning("กรุณาระบุจำนวนเงินมากกว่า 0 ครับ")
        else:
            add_category_if_new(confirm_category, fixed_type, current_user)
            save_transaction(confirm_date, fixed_type, confirm_amount, confirm_category, confirm_description, "voice", current_user)
            st.cache_data.clear()
            st.success(f"✅ บันทึกสำเร็จ! {fixed_type_label} {confirm_amount:,.2f} บาท ({confirm_category})")
            st.rerun()


# =============================================================
# ฟังก์ชันย่อย: อ่านจากรูปภาพ (เฉพาะแท็บ "รายรับ" — เพราะเอกสารแบบสลิปเงินเดือนมีทั้ง 2 ฝั่งใน
# รูปเดียว AI จะแยกออกมาให้ทั้งรายรับและรายจ่าย/รายการหักพร้อมกันในครั้งเดียว)
# =============================================================
def render_image_entry():
    st.caption(
        "อัปโหลดรูปภาพเอกสารการเงิน เช่น สลิปเงินเดือน — AI จะแยกทั้งรายรับ (เงินเดือน, ค่าเบี้ยเลี้ยง) "
        "และรายการหัก (ประกันสังคม, PVD, ภาษี) ออกมาให้อัตโนมัติ บันทึกเป็นรายการแยกๆ ทั้งฝั่งรายรับและรายจ่าย"
    )

    uploaded_image = st.file_uploader("อัปโหลดรูปภาพ", type=["png", "jpg", "jpeg"], key="income_image_uploader")

    if uploaded_image and st.button("🔍 วิเคราะห์รูปภาพด้วย AI", type="primary"):
        with st.spinner("AI กำลังอ่านรูปภาพ... (อาจใช้เวลา 10-20 วินาที)"):
            try:
                extracted_items = extract_transactions_from_image(
                    uploaded_image.getvalue(), uploaded_image.type,
                    expense_categories, income_categories
                )
                if not extracted_items:
                    st.warning("AI อ่านรูปนี้ไม่ออก หรือไม่พบรายการทางการเงินเลยครับ")
                else:
                    st.session_state['extracted_items'] = extracted_items
            except Exception as e:
                st.error(f"❌ อ่านรูปภาพไม่สำเร็จ: {e}")

    if st.session_state.get('extracted_items'):
        st.markdown("##### ✅ ตรวจสอบรายการที่ AI อ่านได้ก่อนบันทึก (แก้ไขในตารางได้เลย)")
        shared_date = st.date_input("วันที่ของเอกสารนี้ (ใช้กับทุกรายการที่อ่านได้)", value=date.today(), key="image_shared_date")

        # 🆕 เพิ่มคอลัมน์ "group" ให้แก้ไขได้ในตารางด้วย (AI จัดกลุ่มมาให้อัตโนมัติแล้ว แต่ยัง
        # ปรับแก้เองได้ก่อนบันทึกจริง เผื่อ AI จัดผิดกลุ่มบางรายการ)
        _raw_extracted = pd.DataFrame(st.session_state['extracted_items'])
        if 'group' not in _raw_extracted.columns:
            _raw_extracted['group'] = CATEGORY_GROUP_GENERAL  # กันไว้เผื่อ AI ตอบมาไม่ครบ field

        edit_df = _raw_extracted[['description', 'amount', 'type', 'category', 'group']]
        edited_df = st.data_editor(
            edit_df, use_container_width=True, hide_index=True, key="image_edit_table",
            column_config={
                "description": st.column_config.TextColumn("รายละเอียด"),
                "amount": st.column_config.NumberColumn("จำนวนเงิน", format="%.2f", min_value=0.0),
                "type": st.column_config.SelectboxColumn("ประเภท", options=["income", "expense"]),
                "category": st.column_config.TextColumn("หมวดหมู่"),
                "group": st.column_config.SelectboxColumn(
                    "กลุ่ม", options=[CATEGORY_GROUP_GENERAL, CATEGORY_GROUP_PAYROLL]
                ),
            },
            num_rows="dynamic",  # ลบ/เพิ่มแถวเองได้ เผื่อ AI อ่านผิดหรือตกหล่นบางรายการ
        )

        total_income = edited_df[edited_df['type'] == 'income']['amount'].sum()
        total_expense = edited_df[edited_df['type'] == 'expense']['amount'].sum()
        st.caption(f"รวมรายรับ: {total_income:,.2f} ฿ | รวมรายการหัก/รายจ่าย: {total_expense:,.2f} ฿")

        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("💾 บันทึกทุกรายการ", type="primary", use_container_width=True):
                _count = 0
                for _, row in edited_df.iterrows():
                    if row['amount'] > 0 and row['description']:
                        add_category_if_new(row['category'], row['type'], current_user, group=row['group'])
                        save_transaction(shared_date, row['type'], row['amount'], row['category'], row['description'], "image", current_user)
                        _count += 1
                st.cache_data.clear()
                st.success(f"✅ บันทึกสำเร็จ {_count} รายการ!")
                st.session_state.pop('extracted_items', None)
                st.rerun()
        with bc2:
            if st.button("❌ ยกเลิก ไม่บันทึก", use_container_width=True):
                st.session_state.pop('extracted_items', None)
                st.rerun()


# =============================================================
# เมนู 1: บันทึกรายการ — แยกเป็น 2 แท็บย่อยแนวนอน (รายรับ/รายจ่าย)
# =============================================================
if selected_menu == "บันทึกรายการ":
    st.title("📝 บันทึกรายการ")

    # 🆕 เพิ่มหมวดหมู่เองได้โดยตรง — ไม่ต้องพึ่ง AI สร้างให้อัตโนมัติเท่านั้น เผื่ออยากเพิ่มหมวดหมู่
    # ที่รู้อยู่แล้วว่าจะใช้บ่อยไว้ล่วงหน้าเลย (เช่น หมวดหมู่ที่เพิ่งเปลี่ยนแปลงมาจากค่าเริ่มต้น แต่
    # บัญชีนี้เคยสร้างหมวดหมู่ไปแล้วก่อนหน้า ค่าเริ่มต้นใหม่จะไม่ถูกเพิ่มให้อัตโนมัติอีก)
    # 🆕 เพิ่มแท็บที่ 2 "จัดกลุ่มหมวดหมู่รายจ่าย" — สำหรับหมวดหมู่เก่าที่สร้างไว้ก่อนมีฟีเจอร์แยกกลุ่ม
    # (รายการหักจากเงินเดือน vs ค่าใช้จ่ายทั่วไป) ซึ่งยังไม่มีข้อมูลกลุ่มนี้เก็บไว้เลย ต้องมาจัดย้อนหลัง
    with st.expander("➕ จัดการหมวดหมู่ (เพิ่มใหม่ / จัดกลุ่ม)"):
        manage_tab1, manage_tab2 = st.tabs(["เพิ่มหมวดหมู่ใหม่", "จัดกลุ่มหมวดหมู่รายจ่าย"])

        with manage_tab1:
            with st.form("add_category_form", clear_on_submit=True):
                ac1, ac2 = st.columns([1, 2])
                with ac1:
                    new_cat_type = st.radio("ประเภท", ["รายรับ", "รายจ่าย"], horizontal=True, key="new_cat_type")
                with ac2:
                    new_cat_name = st.text_input("ชื่อหมวดหมู่ใหม่", placeholder="เช่น ปันผลหุ้น", key="new_cat_name")
                add_cat_submitted = st.form_submit_button("➕ เพิ่มหมวดหมู่นี้", type="primary")

            if add_cat_submitted:
                if not new_cat_name.strip():
                    st.warning("กรุณาพิมพ์ชื่อหมวดหมู่ก่อนครับ")
                else:
                    _type_code = "income" if new_cat_type == "รายรับ" else "expense"
                    add_category_if_new(new_cat_name.strip(), _type_code, current_user)
                    st.success(f"✅ เพิ่มหมวดหมู่ '{new_cat_name.strip()}' ({new_cat_type}) สำเร็จแล้ว")
                    st.cache_data.clear()
                    st.rerun()

        with manage_tab2:
            st.caption(
                "แยก \"รายการหักจากเงินเดือน\" (ประกันสังคม, PVD, ภาษี, สหกรณ์) ออกจาก \"ค่าใช้จ่ายทั่วไป\" "
                "(ใช้จ่ายจริงในชีวิตประจำวัน) เพื่อกรองดูแยกกันได้ในหน้าสรุปภาพรวม — เปลี่ยนตรงนี้แล้วบันทึกทันที"
            )
            _cats_with_group = load_categories_with_group('expense', current_user)
            if not _cats_with_group:
                st.caption("ยังไม่มีหมวดหมู่รายจ่ายเลยครับ")
            else:
                for _cat in _cats_with_group:
                    gc1, gc2 = st.columns([2, 2])
                    with gc1:
                        st.markdown(f"**{_cat['name']}**")
                    with gc2:
                        _new_group = st.selectbox(
                            "กลุ่ม", [CATEGORY_GROUP_GENERAL, CATEGORY_GROUP_PAYROLL],
                            index=0 if _cat['group'] == CATEGORY_GROUP_GENERAL else 1,
                            key=f"group_select_{_cat['doc_id']}",
                            label_visibility="collapsed"
                        )
                        if _new_group != _cat['group']:
                            update_category_group(_cat['doc_id'], _new_group)
                            st.cache_data.clear()
                            st.rerun()

    # 🔧 ปรับปรุง: สลับให้แท็บ "รายจ่าย" เป็นแท็บซ้ายสุด (Streamlit เปิดแท็บซ้ายสุดเป็นค่าเริ่มต้น
    # เสมอ) เพราะใช้บันทึกรายจ่ายบ่อยกว่ารายรับมากในชีวิตประจำวัน — สลับแค่ตำแหน่งการแสดงผล ตัวแปร
    # tab_expense/tab_income ยังอ้างอิงความหมายเดิมทุกจุด ไม่กระทบโค้ดด้านล่างเลย
    tab_expense, tab_income = st.tabs(["🔴 รายจ่าย", "🟢 รายรับ"])

    with tab_income:
        income_method = st.radio(
            "เลือกวิธีบันทึก", ["🎤 พูดบันทึก", "✍️ พิมพ์เอง", "📷 อ่านจากรูปภาพ"],
            horizontal=True, key="income_method"
        )
        st.divider()
        if income_method == "✍️ พิมพ์เอง":
            render_manual_entry("income", "รายรับ")
        elif income_method == "🎤 พูดบันทึก":
            render_voice_entry("income", "รายรับ")
        else:
            render_image_entry()

    with tab_expense:
        expense_method = st.radio(
            "เลือกวิธีบันทึก", ["🎤 พูดบันทึก", "✍️ พิมพ์เอง"],
            horizontal=True, key="expense_method"
        )
        st.divider()
        if expense_method == "✍️ พิมพ์เอง":
            render_manual_entry("expense", "รายจ่าย")
        else:
            render_voice_entry("expense", "รายจ่าย")


# =============================================================
# เมนู 2: ประวัติรายการ
# =============================================================
elif selected_menu == "ประวัติรายการ":
    st.title("📜 ประวัติรายการ")
    transactions = load_transactions(current_user)

    if not transactions:
        st.info("ยังไม่มีรายการบันทึกไว้เลยครับ")
    else:
        df = pd.DataFrame(transactions)
        df['date_parsed'] = pd.to_datetime(df['date'])

        # 🔧 ปรับปรุง: เดิมรวม "เดือน+ปี" ไว้ใน Dropdown เดียว พอใช้งานไปหลายปี ตัวเลือกจะยาวมาก
        # (เช่น ใช้ 3 ปี = 36 ตัวเลือก) ตอนนี้แยกเป็น 2 Dropdown อิสระ — "ปี" (มีแค่เท่าที่มีข้อมูล
        # จริง) กับ "เดือน" (คงที่แค่ 12 ตัวเลือกเสมอ ไม่ว่าจะใช้งานมากี่ปีก็ตาม)
        THAI_MONTHS = {
            1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน", 5: "พฤษภาคม", 6: "มิถุนายน",
            7: "กรกฎาคม", 8: "สิงหาคม", 9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
        }
        THAI_MONTHS_REVERSE = {v: k for k, v in THAI_MONTHS.items()}

        df['year'] = df['date_parsed'].dt.year
        df['month_num'] = df['date_parsed'].dt.month
        available_years = sorted(df['year'].unique().tolist(), reverse=True)

        fc1, fc2 = st.columns(2)
        with fc1:
            year_choice = st.selectbox(
                "📅 ปี", ["ทั้งหมด"] + [str(y) for y in available_years], key="history_year_filter"
            )
        with fc2:
            month_choice = st.selectbox(
                "🗓️ เดือน", ["ทั้งหมด"] + [THAI_MONTHS[m] for m in range(1, 13)], key="history_month_filter"
            )

        _mask = pd.Series([True] * len(df), index=df.index)
        if year_choice != "ทั้งหมด":
            _mask &= (df['year'] == int(year_choice))
        if month_choice != "ทั้งหมด":
            _mask &= (df['month_num'] == THAI_MONTHS_REVERSE[month_choice])

        # 🔧 สำคัญ: เก็บ index ดั้งเดิมของ transactions list ไว้คู่กับ df ที่กรองแล้ว เพื่อให้
        # "แถวที่ถูกเลือกในตาราง" ยังชี้กลับไปหารายการที่ถูกต้องใน transactions ได้เสมอ แม้จะกรอง
        # เหลือแค่บางเดือน/ปีแล้วก็ตาม
        filtered_df = df[_mask].reset_index(drop=True)
        filtered_transactions = [transactions[i] for i in df[_mask].index.tolist()]

        if filtered_df.empty:
            st.info("ไม่มีรายการในช่วงที่เลือกเลยครับ")
        else:
            filtered_df['type_label'] = filtered_df['type'].map({'income': '🟢 รายรับ', 'expense': '🔴 รายจ่าย'})
            filtered_df['source_label'] = filtered_df['source'].map({'manual': '✍️ พิมพ์', 'voice': '🎤 พูด', 'image': '📷 รูปภาพ'})

            display_df = filtered_df[['date', 'type_label', 'amount', 'category', 'description', 'source_label']].rename(columns={
                'date': 'วันที่', 'type_label': 'ประเภท', 'amount': 'จำนวนเงิน',
                'category': 'หมวดหมู่', 'description': 'รายละเอียด', 'source_label': 'ที่มา'
            })

            st.caption("💡 คลิกที่แถวในตารางเพื่อเลือกรายการที่ต้องการแก้ไขหรือลบ (คลิกหัวคอลัมน์เพื่อเรียงลำดับได้ด้วย)")
            # 🔧 ใช้ key แบบ dynamic ตามทั้งปีและเดือนที่เลือก — พอเปลี่ยนตัวกรองไหนก็ตาม widget
            # selection จะรีเซ็ตใหม่หมดทุกครั้งโดยอัตโนมัติ (Streamlit ถือว่า key ต่างกัน = widget
            # คนละตัว) กันปัญหา selection ค้าง index เกินขอบเขตข้ามการเปลี่ยนตัวกรอง
            table_key = f"history_table_{year_choice}_{month_choice}"
            event = st.dataframe(
                display_df, use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row", key=table_key
            )

            selected_rows = event.selection.rows if event and event.selection else []

            if selected_rows and selected_rows[0] < len(filtered_transactions):
                selected_idx = selected_rows[0]
                selected_transaction = filtered_transactions[selected_idx]

                st.divider()
                st.markdown("##### ✏️ แก้ไข/ลบรายการที่เลือก")

                with st.form("edit_transaction_form"):
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        edit_type = st.radio(
                            "ประเภท", ["รายจ่าย", "รายรับ"], horizontal=True,
                            index=0 if selected_transaction['type'] == 'expense' else 1,
                            key="edit_type"
                        )
                        edit_date = st.date_input(
                            "วันที่", value=pd.to_datetime(selected_transaction['date']).date(), key="edit_date"
                        )
                        edit_amount = st.number_input(
                            "จำนวนเงิน (บาท)", min_value=0.0, step=10.0,
                            value=float(selected_transaction['amount']), format="%.2f", key="edit_amount"
                        )
                    with ec2:
                        edit_category_list = expense_categories if edit_type == "รายจ่าย" else income_categories
                        _current_cat = selected_transaction['category']
                        _edit_options = edit_category_list + ([_current_cat] if _current_cat not in edit_category_list else [])
                        edit_category = st.selectbox(
                            "หมวดหมู่", _edit_options,
                            index=_edit_options.index(_current_cat) if _current_cat in _edit_options else 0,
                            key="edit_category"
                        )
                        edit_description = st.text_area(
                            "รายละเอียด", value=selected_transaction['description'], key="edit_description"
                        )

                    edit_col1, edit_col2 = st.columns(2)
                    with edit_col1:
                        save_edit = st.form_submit_button("💾 บันทึกการแก้ไข", type="primary", use_container_width=True)
                    with edit_col2:
                        delete_edit = st.form_submit_button("🗑️ ลบรายการนี้", use_container_width=True)

                if save_edit:
                    if edit_amount <= 0:
                        st.warning("กรุณาระบุจำนวนเงินมากกว่า 0 ครับ")
                    else:
                        edit_type_code = "expense" if edit_type == "รายจ่าย" else "income"
                        add_category_if_new(edit_category, edit_type_code, current_user)
                        update_transaction(
                            selected_transaction['id'], edit_date, edit_type_code,
                            edit_amount, edit_category, edit_description
                        )
                        st.session_state.pop(table_key, None)
                        st.success("✅ แก้ไขสำเร็จ!")
                        st.rerun()

                if delete_edit:
                    delete_transaction(selected_transaction['id'])
                    st.session_state.pop(table_key, None)
                    st.success("ลบสำเร็จ")
                    st.rerun()

        # =============================================================
        # 🆕 ปุ่มล้างข้อมูล (Danger Zone) — ปิดไว้เป็นค่าเริ่มต้น ไม่ให้เด่นเกินไปจนกดพลาดง่าย
        # ต้องยืนยันหลายชั้นก่อนลบจริงเสมอ (ติ๊กยืนยัน + สำหรับ "ล้างทั้งหมด" ต้องพิมพ์ชื่อผู้ใช้
        # ตัวเองด้วย) เพราะเป็นการลบข้อมูลถาวร ย้อนคืนไม่ได้เลย
        # =============================================================
        st.divider()
        with st.expander("🗑️ ล้างข้อมูล (ลบแล้วกู้คืนไม่ได้)"):
            danger_tab1, danger_tab2 = st.tabs(["ล้างเฉพาะเดือน", "ล้างข้อมูลทั้งหมด"])

            with danger_tab1:
                if year_choice == "ทั้งหมด" or month_choice == "ทั้งหมด":
                    st.caption(
                        "💡 เลือกทั้ง \"ปี\" และ \"เดือน\" ที่ต้องการลบจาก Dropdown ด้านบนก่อนครับ "
                        "(ต้องเจาะจงทั้งคู่ ไม่ใช่ \"ทั้งหมด\")"
                    )
                else:
                    st.warning(
                        f"กำลังจะลบรายการทั้งหมดของเดือน **{month_choice} {year_choice}** "
                        f"({len(filtered_transactions)} รายการ) — ไม่สามารถย้อนคืนได้"
                    )
                    confirm_month_delete = st.checkbox(
                        "ฉันเข้าใจว่าการลบนี้ไม่สามารถย้อนคืนได้", key="confirm_month_delete"
                    )
                    if st.button(
                        "🗑️ ลบข้อมูลเดือนนี้ทั้งหมด",
                        disabled=(not confirm_month_delete or len(filtered_transactions) == 0),
                        key="btn_delete_month"
                    ):
                        _deleted_count = delete_transactions_by_month(
                            current_user, int(year_choice), THAI_MONTHS_REVERSE[month_choice]
                        )
                        st.success(f"✅ ลบข้อมูลเดือน {month_choice} {year_choice} ไปแล้ว {_deleted_count} รายการ")
                        st.rerun()

            with danger_tab2:
                st.error(
                    f"⚠️ กำลังจะลบ **ทุกรายการทั้งหมด** ของบัญชี {current_user} "
                    f"({len(transactions)} รายการ) อย่างถาวร ไม่สามารถย้อนคืนได้"
                )
                confirm_all_check = st.checkbox(
                    "ฉันเข้าใจว่าการลบนี้จะลบทุกรายการทั้งหมดอย่างถาวร", key="confirm_all_check"
                )
                confirm_all_text = st.text_input(
                    f"พิมพ์ชื่อผู้ใช้ของคุณ ({current_user}) เพื่อยืนยัน", key="confirm_all_text"
                )
                if st.button(
                    "🗑️🔥 ลบข้อมูลทั้งหมด", type="primary",
                    disabled=(not confirm_all_check or confirm_all_text != current_user),
                    key="btn_delete_all"
                ):
                    _deleted_count = delete_all_transactions(current_user)
                    st.success(f"✅ ลบข้อมูลทั้งหมดไปแล้ว {_deleted_count} รายการ")
                    st.rerun()


# =============================================================
# เมนู 3: สรุปภาพรวม
# =============================================================
elif selected_menu == "สรุปภาพรวม":
    st.title("📊 สรุปภาพรวม")
    transactions = load_transactions(current_user)

    if not transactions:
        st.info("ยังไม่มีข้อมูลให้สรุปครับ")
    else:
        df = pd.DataFrame(transactions)
        df['date_parsed'] = pd.to_datetime(df['date'])

        # 🆕 ตัวกรองช่วงเวลา — 3 เดือน, 6 เดือน, 1 ปี, ทั้งหมด, หรือกำหนดเอง
        st.markdown("##### 🗓️ เลือกช่วงเวลา")
        range_choice = st.radio(
            "ช่วงเวลา", ["3 เดือนล่าสุด", "6 เดือนล่าสุด", "1 ปีล่าสุด", "ทั้งหมด", "กำหนดเอง"],
            horizontal=True, key="summary_range_choice", label_visibility="collapsed"
        )

        today_ts = pd.Timestamp(date.today())
        if range_choice == "3 เดือนล่าสุด":
            filtered_df = df[df['date_parsed'] >= today_ts - pd.DateOffset(months=3)]
        elif range_choice == "6 เดือนล่าสุด":
            filtered_df = df[df['date_parsed'] >= today_ts - pd.DateOffset(months=6)]
        elif range_choice == "1 ปีล่าสุด":
            filtered_df = df[df['date_parsed'] >= today_ts - pd.DateOffset(years=1)]
        elif range_choice == "ทั้งหมด":
            filtered_df = df
        else:  # กำหนดเอง
            dc1, dc2 = st.columns(2)
            with dc1:
                custom_start = st.date_input(
                    "จากวันที่", value=df['date_parsed'].min().date(), key="summary_custom_start"
                )
            with dc2:
                custom_end = st.date_input("ถึงวันที่", value=date.today(), key="summary_custom_end")
            filtered_df = df[
                (df['date_parsed'] >= pd.Timestamp(custom_start)) &
                (df['date_parsed'] <= pd.Timestamp(custom_end))
            ]

        st.divider()

        if filtered_df.empty:
            st.info("ไม่มีรายการในช่วงเวลาที่เลือกเลยครับ")
        else:
            total_income = filtered_df[filtered_df['type'] == 'income']['amount'].sum()
            total_expense = filtered_df[filtered_df['type'] == 'expense']['amount'].sum()
            net = total_income - total_expense

            # 🆕 เปลี่ยนจาก st.metric() ธรรมดา มาเป็นการ์ดสไตล์เดียวกับ stock-scanner
            c1, c2, c3 = st.columns(3)
            render_metric_card(c1, "รายรับรวม", f"{total_income:,.0f} ฿", icon="🟢")
            render_metric_card(c2, "รายจ่ายรวม", f"{total_expense:,.0f} ฿", icon="🔴")
            render_metric_card(
                c3, "คงเหลือสุทธิ", f"{net:,.0f} ฿", icon="💰",
                delta="เกินดุล" if net >= 0 else "ขาดดุล", delta_positive=(net >= 0)
            )

            st.divider()
            st.markdown("##### 📊 รายจ่ายแยกตามหมวดหมู่")

            # 🆕 ตัวกรองกลุ่ม — แยกดู "รายการหักจากเงินเดือน" ออกจาก "ค่าใช้จ่ายทั่วไป" ได้ เพราะ
            # รายการหักมักมีมูลค่าสูงกว่าค่าใช้จ่ายทั่วไปมาก ถ้าไม่แยกดู จะบดบังค่าใช้จ่ายทั่วไปใน
            # กราฟจนมองแทบไม่เห็นเลย (ตัวกรองนี้มีผลแค่กราฟด้านล่างเท่านั้น ไม่กระทบการ์ดสรุปด้านบน
            # ซึ่งควรยังคงแสดงยอดรวมที่แท้จริงเสมอ)
            _cats_with_group_all = load_categories_with_group('expense', current_user)
            _category_to_group = {c['name']: c['group'] for c in _cats_with_group_all}

            group_filter_choice = st.radio(
                "กรองตามกลุ่ม", ["ทั้งหมด", CATEGORY_GROUP_GENERAL, CATEGORY_GROUP_PAYROLL],
                horizontal=True, key="summary_group_filter"
            )

            expense_df = filtered_df[filtered_df['type'] == 'expense'].copy()
            expense_df['group'] = expense_df['category'].map(_category_to_group).fillna(CATEGORY_GROUP_GENERAL)

            if group_filter_choice != "ทั้งหมด":
                expense_df = expense_df[expense_df['group'] == group_filter_choice]

            expense_by_cat = expense_df.groupby('category')['amount'].sum().sort_values(ascending=False)

            if expense_by_cat.empty:
                st.caption("ยังไม่มีรายการรายจ่ายในช่วงเวลา/กลุ่มนี้เลย")
            else:
                # 🆕 แบ่งครึ่งหน้าจอ — กราฟแท่งด้านซ้าย + กราฟ Donut ด้านขวา (ใช้ข้อมูลเดียวกัน
                # คนละมุมมอง: แท่งช่วยเทียบขนาดตรงๆ ส่วน Donut เห็นสัดส่วนโดยรวมชัดกว่า)
                theme_colors = get_theme_colors()
                chart_col1, chart_col2 = st.columns(2)

                with chart_col1:
                    fig_bar = go.Figure(go.Bar(
                        x=expense_by_cat.values, y=expense_by_cat.index, orientation='h',
                        marker_color=theme_colors['chart_colors'][:len(expense_by_cat)]
                    ))
                    fig_bar.update_layout(
                        title="แยกตามหมวดหมู่ (แท่ง)", height=420,
                        margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(autorange="reversed")
                    )
                    st.plotly_chart(style_plotly(fig_bar), use_container_width=True)

                with chart_col2:
                    fig_donut = go.Figure(go.Pie(
                        labels=expense_by_cat.index, values=expense_by_cat.values, hole=0.45,
                        marker=dict(colors=theme_colors['chart_colors'])
                    ))
                    fig_donut.update_layout(
                        title="สัดส่วนรายจ่าย", height=420, margin=dict(l=10, r=10, t=40, b=10)
                    )
                    st.plotly_chart(style_plotly(fig_donut), use_container_width=True)
