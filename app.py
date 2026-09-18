# =============================================================
# App.py
# แอปบันทึกรายรับ-รายจ่ายส่วนตัว — รองรับพิมพ์เอง + พูดบันทึก + อ่านจากรูปภาพ (AI แปลงเสียง/รูปภาพ
# + จัดหมวดหมู่อัตโนมัติ) มีระบบ Login แยกผู้ใช้ (คนละบัญชี เห็นแค่ข้อมูลตัวเอง)
# 🆕 ปรับโครงสร้างเมนูจากแท็บแนวนอนด้านบน มาเป็นเมนู Sidebar แนวตั้งด้านซ้ายแทน (เหมือนที่ปรับให้
# stock-scanner ไปแล้วก่อนหน้านี้) และแยก "บันทึกรายการ" เป็น 2 แท็บย่อยแนวนอน (รายรับ/รายจ่าย)
# =============================================================
import streamlit as st
import pandas as pd
from datetime import date
from auth import check_login, show_user_bar
from backend_functions import (
    load_categories, add_category_if_new, save_transaction,
    load_transactions, delete_transaction, update_transaction,
    transcribe_audio, categorize_with_ai, extract_transactions_from_image,
)

st.set_page_config(page_title="บันทึกรายรับ-รายจ่าย", page_icon="💰", layout="wide")

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

        edit_df = pd.DataFrame(st.session_state['extracted_items'])[['description', 'amount', 'type', 'category']]
        edited_df = st.data_editor(
            edit_df, use_container_width=True, hide_index=True, key="image_edit_table",
            column_config={
                "description": st.column_config.TextColumn("รายละเอียด"),
                "amount": st.column_config.NumberColumn("จำนวนเงิน", format="%.2f", min_value=0.0),
                "type": st.column_config.SelectboxColumn("ประเภท", options=["income", "expense"]),
                "category": st.column_config.TextColumn("หมวดหมู่"),
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
                        add_category_if_new(row['category'], row['type'], current_user)
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
    with st.expander("➕ เพิ่มหมวดหมู่เอง"):
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

    tab_income, tab_expense = st.tabs(["🟢 รายรับ", "🔴 รายจ่าย"])

    with tab_income:
        income_method = st.radio(
            "เลือกวิธีบันทึก", ["✍️ พิมพ์เอง", "🎤 พูดบันทึก", "📷 อ่านจากรูปภาพ"],
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
            "เลือกวิธีบันทึก", ["✍️ พิมพ์เอง", "🎤 พูดบันทึก"],
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
        df['type_label'] = df['type'].map({'income': '🟢 รายรับ', 'expense': '🔴 รายจ่าย'})
        # 🆕 เพิ่ม 'image': '📷 รูปภาพ' เข้า mapping ที่มา (source) เพราะตอนนี้มีช่องทางบันทึกใหม่แล้ว
        df['source_label'] = df['source'].map({'manual': '✍️ พิมพ์', 'voice': '🎤 พูด', 'image': '📷 รูปภาพ'})

        display_df = df[['date', 'type_label', 'amount', 'category', 'description', 'source_label']].rename(columns={
            'date': 'วันที่', 'type_label': 'ประเภท', 'amount': 'จำนวนเงิน',
            'category': 'หมวดหมู่', 'description': 'รายละเอียด', 'source_label': 'ที่มา'
        })

        st.caption("💡 คลิกที่แถวในตารางเพื่อเลือกรายการที่ต้องการแก้ไขหรือลบ (คลิกหัวคอลัมน์เพื่อเรียงลำดับได้ด้วย)")
        event = st.dataframe(
            display_df, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row", key="history_table"
        )

        selected_rows = event.selection.rows if event and event.selection else []

        if selected_rows:
            selected_idx = selected_rows[0]
            selected_transaction = transactions[selected_idx]

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
                    st.success("✅ แก้ไขสำเร็จ!")
                    st.rerun()

            if delete_edit:
                delete_transaction(selected_transaction['id'])
                st.success("ลบสำเร็จ")
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
        total_income = df[df['type'] == 'income']['amount'].sum()
        total_expense = df[df['type'] == 'expense']['amount'].sum()
        net = total_income - total_expense

        c1, c2, c3 = st.columns(3)
        c1.metric("รายรับรวม", f"{total_income:,.0f} ฿")
        c2.metric("รายจ่ายรวม", f"{total_expense:,.0f} ฿")
        c3.metric("คงเหลือสุทธิ", f"{net:,.0f} ฿", delta=f"{net:,.0f}")

        st.divider()
        st.markdown("##### 📊 รายจ่ายแยกตามหมวดหมู่")
        expense_by_cat = df[df['type'] == 'expense'].groupby('category')['amount'].sum().sort_values(ascending=False)
        if not expense_by_cat.empty:
            st.bar_chart(expense_by_cat)
        else:
            st.caption("ยังไม่มีรายการรายจ่ายเลย")
