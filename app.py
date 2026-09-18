# =============================================================
# App.py
# แอปบันทึกรายรับ-รายจ่ายส่วนตัว — รองรับพิมพ์เอง + พูดบันทึก (AI แปลงเสียง+จัดหมวดหมู่อัตโนมัติ)
# =============================================================
import streamlit as st
import pandas as pd
from datetime import date
from backend_functions import (
    load_categories, add_category_if_new, save_transaction,
    load_transactions, delete_transaction, transcribe_audio, categorize_with_ai,
)

st.set_page_config(page_title="บันทึกรายรับ-รายจ่าย", page_icon="💰", layout="wide")

st.title("💰 บันทึกรายรับ-รายจ่ายส่วนตัว")

# โหลดหมวดหมู่ทั้งหมดไว้ล่วงหน้า (ใช้ทั้งฝั่งพิมพ์เองและฝั่ง AI)
expense_categories = load_categories('expense')
income_categories = load_categories('income')

tab_record, tab_history, tab_summary = st.tabs(["📝 บันทึกรายการ", "📜 ประวัติรายการ", "📊 สรุปภาพรวม"])

# =============================================================
# แท็บ 1: บันทึกรายการ (พิมพ์เอง + พูดบันทึก)
# =============================================================
with tab_record:
    method = st.radio("เลือกวิธีบันทึก", ["✍️ พิมพ์เอง", "🎤 พูดบันทึก"], horizontal=True)

    st.divider()

    # --- วิธีที่ 1: พิมพ์เอง ---
    if method == "✍️ พิมพ์เอง":
        with st.form("manual_entry_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                trans_type = st.radio("ประเภท", ["รายจ่าย", "รายรับ"], horizontal=True)
                trans_date = st.date_input("วันที่", value=date.today())
                amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=10.0, format="%.2f")
            with c2:
                # เลือกหมวดหมู่ตามประเภทที่เลือกไว้ — มีตัวเลือก "ให้ AI เลือกให้" ด้วย
                category_list = expense_categories if trans_type == "รายจ่าย" else income_categories
                category_choice = st.selectbox("หมวดหมู่", ["🤖 ให้ AI เลือกให้อัตโนมัติ"] + category_list)
                description = st.text_area("รายละเอียด", placeholder="เช่น ค่าข้าวเที่ยงกับเพื่อน")

            submitted = st.form_submit_button("💾 บันทึกรายการ", type="primary", use_container_width=True)

        if submitted:
            if amount <= 0:
                st.warning("กรุณาระบุจำนวนเงินมากกว่า 0 ครับ")
            else:
                type_code = "expense" if trans_type == "รายจ่าย" else "income"

                if category_choice == "🤖 ให้ AI เลือกให้อัตโนมัติ":
                    with st.spinner("AI กำลังเลือกหมวดหมู่ให้..."):
                        try:
                            ai_result = categorize_with_ai(
                                description or f"{trans_type} {amount} บาท",
                                expense_categories, income_categories
                            )
                            final_category = ai_result.get('category', 'อื่นๆ')
                            if ai_result.get('is_new_category'):
                                st.info(f"🆕 AI สร้างหมวดหมู่ใหม่ให้: **{final_category}**")
                                add_category_if_new(final_category, type_code)
                        except Exception as e:
                            st.warning(f"AI จัดหมวดหมู่ไม่สำเร็จ ใช้หมวด 'อื่นๆ' แทน: {e}")
                            final_category = "อื่นๆ"
                else:
                    final_category = category_choice

                save_transaction(trans_date, type_code, amount, final_category, description, "manual")
                st.cache_data.clear()
                st.success(f"✅ บันทึกสำเร็จ! {trans_type} {amount:,.2f} บาท ({final_category})")
                st.rerun()

    # --- วิธีที่ 2: พูดบันทึก ---
    else:
        st.caption("กดปุ่มแล้วพูดบรรยายรายการ เช่น \"จ่ายค่าข้าวเที่ยง 80 บาท\" หรือ \"ได้เงินขายภาพสต็อก 3000 บาท\"")

        from streamlit_mic_recorder import mic_recorder
        # 🔧 ระบุ format="wav" ชัดเจนเสมอ (ไม่พึ่งค่า default ของไลบรารี เพราะบางเวอร์ชัน default
        # เป็น "webm" แทน ซึ่งอาจทำให้ส่งไฟล์ผิดประเภทไปให้ Groq วิเคราะห์)
        audio = mic_recorder(start_prompt="🎤 เริ่มพูด", stop_prompt="⏹️ หยุดพูด", format="wav", key="voice_recorder")

        if audio:
            with st.spinner("กำลังแปลงเสียงเป็นข้อความ..."):
                try:
                    transcribed_text = transcribe_audio(audio['bytes'])
                except Exception as e:
                    st.error(f"❌ แปลงเสียงไม่สำเร็จ: {e}")
                    transcribed_text = None

            if transcribed_text:
                st.info(f"🗣️ ข้อความที่แปลงได้: \"{transcribed_text}\"")

                with st.spinner("AI กำลังวิเคราะห์และจัดหมวดหมู่..."):
                    try:
                        ai_result = categorize_with_ai(transcribed_text, expense_categories, income_categories)
                    except Exception as e:
                        st.error(f"❌ AI วิเคราะห์ไม่สำเร็จ: {e}")
                        ai_result = None

                if ai_result:
                    # 🆕 แสดงผลที่ AI วิเคราะห์ได้ ให้ผู้ใช้ตรวจสอบ/แก้ไขก่อนบันทึกจริงเสมอ (ไม่บันทึก
                    # ทันทีอัตโนมัติ) กันกรณีแปลงเสียง/วิเคราะห์ผิดพลาดแล้วข้อมูลเพี้ยนเข้าระบบ
                    st.markdown("##### ✅ ตรวจสอบก่อนบันทึก")
                    with st.form("voice_confirm_form"):
                        vc1, vc2 = st.columns(2)
                        with vc1:
                            confirm_type = st.radio(
                                "ประเภท", ["รายจ่าย", "รายรับ"], horizontal=True,
                                index=0 if ai_result.get('type') == 'expense' else 1
                            )
                            confirm_date = st.date_input("วันที่", value=date.today())
                            confirm_amount = st.number_input(
                                "จำนวนเงิน (บาท)", min_value=0.0, step=10.0,
                                value=float(ai_result.get('amount', 0)), format="%.2f"
                            )
                        with vc2:
                            confirm_category_list = expense_categories if confirm_type == "รายจ่าย" else income_categories
                            _suggested = ai_result.get('category', 'อื่นๆ')
                            _options = confirm_category_list + ([_suggested] if _suggested not in confirm_category_list else [])
                            confirm_category = st.selectbox(
                                "หมวดหมู่ (AI แนะนำไว้แล้ว แก้ไขได้)", _options,
                                index=_options.index(_suggested) if _suggested in _options else 0
                            )
                            confirm_description = st.text_area("รายละเอียด", value=ai_result.get('description', transcribed_text))

                        voice_submitted = st.form_submit_button("💾 ยืนยันบันทึก", type="primary", use_container_width=True)

                    if voice_submitted:
                        if confirm_amount <= 0:
                            st.warning("กรุณาระบุจำนวนเงินมากกว่า 0 ครับ")
                        else:
                            type_code = "expense" if confirm_type == "รายจ่าย" else "income"
                            add_category_if_new(confirm_category, type_code)
                            save_transaction(confirm_date, type_code, confirm_amount, confirm_category, confirm_description, "voice")
                            st.cache_data.clear()
                            st.success(f"✅ บันทึกสำเร็จ! {confirm_type} {confirm_amount:,.2f} บาท ({confirm_category})")
                            st.rerun()

# =============================================================
# แท็บ 2: ประวัติรายการ
# =============================================================
with tab_history:
    transactions = load_transactions()

    if not transactions:
        st.info("ยังไม่มีรายการบันทึกไว้เลยครับ")
    else:
        df = pd.DataFrame(transactions)
        df['type_label'] = df['type'].map({'income': '🟢 รายรับ', 'expense': '🔴 รายจ่าย'})
        df['source_label'] = df['source'].map({'manual': '✍️ พิมพ์', 'voice': '🎤 พูด'})

        st.dataframe(
            df[['date', 'type_label', 'amount', 'category', 'description', 'source_label']].rename(columns={
                'date': 'วันที่', 'type_label': 'ประเภท', 'amount': 'จำนวนเงิน',
                'category': 'หมวดหมู่', 'description': 'รายละเอียด', 'source_label': 'ที่มา'
            }),
            use_container_width=True, hide_index=True
        )

        st.divider()
        st.markdown("##### 🗑️ ลบรายการ")
        del_options = {f"{t['date']} | {t['category']} | {t['amount']:,.0f} บาท | {t['description'][:30]}": t['id'] for t in transactions}
        to_delete = st.selectbox("เลือกรายการที่ต้องการลบ", list(del_options.keys()))
        if st.button("🗑️ ลบรายการนี้"):
            delete_transaction(del_options[to_delete])
            st.success("ลบสำเร็จ")
            st.rerun()

# =============================================================
# แท็บ 3: สรุปภาพรวม
# =============================================================
with tab_summary:
    transactions = load_transactions()

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
