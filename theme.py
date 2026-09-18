# =============================================================
# theme.py
# ธีมสีและสไตล์การ์ด — โทนสีเดียวกับ stock-scanner (ครีม + เขียวเซจ)
# =============================================================
import streamlit as st

BG_COLOR = "#FAF7F0"        # พื้นหลังครีม
PRIMARY_COLOR = "#7C9885"   # เขียวเซจ (สีหลัก)
TEXT_DARK = "#2C3E32"
TEXT_MUTED = "#6B7C6F"
BORDER_COLOR = "#EDE8DD"

# ชุดสีไล่โทนเขียวเซจ สำหรับกราฟหลายสี (เรียงจากเข้มไปอ่อน)
CHART_COLORS = [
    "#4A6858", "#597865", "#5C7A6A", "#6B8975", "#7C9885",
    "#8FA894", "#9FB3A6", "#A3B8A8", "#B5C9BA"
]


def apply_theme():
    """ฉีด CSS ปรับพื้นหลังทั้งแอปให้เข้าธีมเดียวกับ stock-scanner (ครีม + เขียวเซจ)"""
    st.markdown(f"""
        <style>
        .stApp {{
            background-color: {BG_COLOR};
        }}
        section[data-testid="stSidebar"] {{
            background-color: #F3EFE4;
        }}
        </style>
    """, unsafe_allow_html=True)


def render_metric_card(col, label, value, icon="", delta=None, delta_positive=None):
    """
    การ์ดตัวเลขสไตล์เดียวกับ stock-scanner (กรอบมน/เงา/ฟอนต์) ใช้แทน st.metric() ธรรมดา
    เพื่อให้หน้าตาไปในทิศทางเดียวกันทั้งแอป
    """
    delta_html = ""
    if delta is not None:
        color = "#2E7D32" if delta_positive else "#C62828"
        arrow = "▲" if delta_positive else "▼"
        delta_html = f'<div style="color:{color};font-size:13px;margin-top:4px;">{arrow} {delta}</div>'

    col.markdown(f"""
        <div style="
            background-color: white;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            border: 1px solid {BORDER_COLOR};
        ">
            <div style="font-size:14px;color:{TEXT_MUTED};margin-bottom:6px;">{icon} {label}</div>
            <div style="font-size:28px;font-weight:700;color:{TEXT_DARK};">{value}</div>
            {delta_html}
        </div>
    """, unsafe_allow_html=True)


def get_theme_colors():
    """คืนค่าชุดสีธีม สำหรับใช้กับกราฟ Plotly หรือส่วนอื่นๆ ที่ต้องการสีตรงกับธีม"""
    return {
        "bg": BG_COLOR,
        "primary": PRIMARY_COLOR,
        "text": TEXT_DARK,
        "chart_colors": CHART_COLORS,
    }


def style_plotly(fig):
    """ปรับสไตล์กราฟ Plotly ให้เข้าธีม (พื้นหลังโปร่งใส ให้เห็นพื้นครีมทะลุ + สีตัวอักษรเข้าธีม)"""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT_DARK),
        colorway=CHART_COLORS,
    )
    return fig
