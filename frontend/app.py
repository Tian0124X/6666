"""Streamlit 前端主入口 — 企业智能办公助手"""

import streamlit as st

st.set_page_config(
    page_title="企业智能办公助手",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===== 侧边栏导航 =====
with st.sidebar:
    st.title("🤖 企业智能办公助手")
    st.markdown("---")

    page = st.radio(
        "导航",
        ["💬 智能对话", "🔧 工具测试", "📚 知识库管理", "⚙️ 偏好设置"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption(f"Powered by 通义千问 | v1.0.0")
    st.caption(f"后端: http://localhost:8000")
    st.caption(f"API 文档: http://localhost:8000/docs")

# ===== 页面路由 =====
if page == "💬 智能对话":
    st.title("💬 智能对话")
    st.info("对话功能将在 Phase 6 实现。当前为骨架界面。")

    # 占位聊天界面
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("请输入您的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            st.markdown(f"_[骨架响应]_ 收到您的消息: {prompt[:80]}...")
        st.session_state.messages.append(
            {"role": "assistant", "content": f"[骨架响应] 收到您的消息: {prompt[:80]}..."}
        )

elif page == "🔧 工具测试":
    st.title("🔧 工具测试")
    st.info("工具测试功能将在 Phase 6 实现。")

    tab1, tab2, tab3 = st.tabs(["📊 数据分析", "📋 OA 查询", "👤 CRM 查询"])

    with tab1:
        st.text("上传 Excel/CSV 文件进行自动化分析")
        st.file_uploader("选择文件", type=["xlsx", "csv"], key="analyze_file")
        if st.button("开始分析", disabled=True):
            st.write("待实现...")

    with tab2:
        st.text("查询 OA 审批状态")
        st.text_input("审批编号", key="oa_id")
        if st.button("查询", disabled=True):
            st.write("待实现...")

    with tab3:
        st.text("查询 CRM 客户信息")
        st.text_input("客户名称", key="crm_name")
        if st.button("搜索", disabled=True):
            st.write("待实现...")

elif page == "📚 知识库管理":
    st.title("📚 知识库管理")

    tab1, tab2 = st.tabs(["📤 上传文档", "🔍 知识问答"])

    with tab1:
        st.subheader("上传企业文档")
        st.caption("支持格式: PDF, Word (.docx), Excel (.xlsx), TXT")
        uploaded_file = st.file_uploader(
            "选择文件",
            type=["pdf", "docx", "xlsx", "xls", "txt", "csv"],
            key="knowledge_upload",
        )
        if uploaded_file and st.button("上传到知识库", disabled=True):
            st.write("待实现...")

    with tab2:
        st.subheader("知识问答测试")
        st.text_input("输入问题", placeholder="例如：公司年假政策是什么？", key="qa_question")
        if st.button("查询", disabled=True):
            st.write("待实现...")

elif page == "⚙️ 偏好设置":
    st.title("⚙️ 偏好设置")
    st.info("设置功能将在 Phase 6 实现。")

    with st.form("settings_form"):
        st.subheader("模型设置")
        st.selectbox("模型", ["qwen-turbo", "qwen-plus", "qwen-max"], index=1)
        st.slider("Temperature", 0.0, 1.0, 0.5, 0.1)

        st.subheader("工具开关")
        st.checkbox("数据分析工具", value=True)
        st.checkbox("OA/CRM 工具", value=True)
        st.checkbox("知识库检索", value=True)

        st.form_submit_button("保存设置", disabled=True)
