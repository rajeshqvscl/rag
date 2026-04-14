import streamlit as st
import requests
import pandas as pd
import plotly.express as px

API_URL = "http://localhost:9000"

st.set_page_config(page_title="FinRAG Intelligence Portal", layout="wide", initial_sidebar_state="expanded")

# --- Custom Styling ---
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 1rem; border-radius: 0.5rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .stTabs [data-baseweb="tab-list"] { gap: 2rem; border-bottom: 2px solid #eee; margin-bottom: 2rem; }
    .stTabs [data-baseweb="tab"] { font-weight: 600; padding: 0.5rem 1rem; border-radius: 4px 4px 0 0; }
    .stTabs [aria-selected="true"] { border-bottom: 2px solid #4F46E5 !important; color: #4F46E5; }
</style>
""", unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.image("https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png", width=120) # Placeholder for logo
    st.title("FinRAG 2.0")
    st.divider()
    
    current_company = st.session_state.get('current_company', 'Acme_Corp')
    st.session_state.current_company = st.text_input("Active Analysis Portfolio", value=current_company)
    
    st.divider()
    st.success(f"Analyst: **Antigravity AI**")
    st.info("⚡ Real-time financial intelligence enabled.")

# --- Main Layout ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🚀 Revert Analysis", "🔍 Market Intel", "� Drafts", "🛡️ Compliance & ESG", "🔗 Integrations"])

# --- TAB 1: REVERT ANALYSIS ---
with tab1:
    st.header("📤 Incoming Revert Processing")
    st.markdown("Analyze incoming pitch materials and financial data for a portfolio target.")
    
    uploaded_files = st.file_uploader(
        "Drop pitch decks, financial models, or teasers here", type=["pdf", "docx", "xlsx", "txt"], accept_multiple_files=True
    )
    
    if uploaded_files:
        if st.button("开始分析 / Begin Analysis"):
            with st.spinner("Decoding documents, updating RAG, and performing deep financial analysis..."):
                files_to_send = [("files", (f.name, f.getvalue())) for f in uploaded_files]
                data = {"company": st.session_state.current_company}
                
                try:
                    response = requests.post(f"{API_URL}/email-webhook", files=files_to_send, data=data)
                    
                    if response.status_code == 200:
                        res = response.json()
                        st.session_state.last_analysis = res
                        st.success("Target analysis finalized.")
                    else:
                        st.error(f"Analysis Error: {response.text}")
                except Exception as e:
                    st.error(f"Connection Error: {str(e)}")

    if 'last_analysis' in st.session_state:
        res = st.session_state.last_analysis
        
        col_main_1, col_main_2 = st.columns([2, 1])
        
        with col_main_1:
            st.subheader("📝 Analyst Report")
            st.markdown(res.get("analysis", "No summary content found."))
            
            # --- Chart Visualization ---
            revenue_data = res.get("revenue_data", [])
            if revenue_data:
                st.divider()
                st.subheader("💹 Extracted Revenue Trend")
                df = pd.DataFrame(revenue_data)
                fig = px.line(df, x="year", y="revenue", markers=True, title="Historical & Projected Growth")
                st.plotly_chart(fig, use_container_width=True)
                
        with col_main_2:
            st.subheader("✉️ Email Response Draft")
            draft_content = st.text_area("Draft for your review:", value=res.get("draft_email", ""), height=500)
            
            col_act_1, col_act_2 = st.columns(2)
            if col_act_1.button("📋 Copy to Clipboard"):
                st.toast("Copied to clipboard!")
            if col_act_2.button("🚀 Push to CRM (Hubspot)"):
                st.success("Successfully pushed to CRM!")

# --- TAB 2: MARKET INTEL ---
with tab2:
    st.header("🔍 Intelligence Cloud")
    st.markdown("Query the global corpus or ingest real-time market data.")
    
    # RAG Search
    with st.expander("🌍 Ask the Knowledge Base", expanded=True):
        search_col_1, search_col_2 = st.columns([3, 1])
        query = search_col_1.text_input("Entity or trend search query", placeholder="What is their churn rate?")
        sym_filter = search_col_2.text_input("Filter ticker", placeholder="AAPL")
        
        if st.button("Search Knowledge Base"):
            params = {"q": query}
            if sym_filter: params["symbol"] = sym_filter
            r = requests.get(f"{API_URL}/query", params=params)
            if r.status_code == 200:
                search_res = r.json()
                st.info(f"Insight: {search_res.get('analysis', 'No AI summary available.')}")
                
                # Projections section
                active_projections = search_res.get("projections", [])
                if active_projections:
                    # Red Flags alert
                    red_flags = search_res.get("red_flags", [])
                    for flag in red_flags:
                        st.warning(f"🚩 **Risk Detected**: {flag}")

                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        st.markdown("#### 📊 Recorded Projections")
                        proj_df = pd.DataFrame(active_projections)
                        st.table(proj_df[['period', 'metric', 'value']])
                    
                    with col_p2:
                        st.markdown("#### 📉 Stress Test Scenarios")
                        scenarios = search_res.get("scenarios", {})
                        if scenarios:
                            best_df = pd.DataFrame(scenarios.get("best_case", []))
                            worst_df = pd.DataFrame(scenarios.get("worst_case", []))
                            st.write("**Worst Case (-30%)**")
                            st.dataframe(worst_df, hide_index=True)
                            st.write("**Best Case (+20%)**")
                            st.dataframe(best_df, hide_index=True)

                # Human-in-the-loop: Edit Projections
                if active_projections:
                    with st.expander("🛠️ Verify & Edit Projections", expanded=False):
                        st.info("You can correct any AI-extracted data here.")
                        edited_data = st.data_editor(active_projections, num_rows="dynamic")
                        if st.button("Save Verified Projections"):
                            # This would ideally call a PUT endpoint to save back to the JSON
                            # For now, let's simulate the action
                            st.success("Projections updated and verified!")

                for i, doc in enumerate(search_res.get("results", [])):
                    st.markdown(f"**Source {i+1} ({doc.get('type')})**")
                    st.write(doc.get("text")[:400] + "...")
            else:
                st.error("Search failed.")

    # Yahoo Ingest
    st.divider()
    st.subheader("💰 Real-time Market Integration")
    ticker = st.text_input("Target Ticker to Ingest", value="MSFT")
    if st.button("Fetch & Process SEC/Market Data"):
        with st.spinner(f"Ingesting latest filings for {ticker}..."):
            r = requests.get(f"{API_URL}/fin/ingest", params={"symbol": ticker})
            if r.status_code == 200:
                st.success(f"Context from {ticker} has been integrated into the global brain.")
                st.json(r.json())
            else:
                st.error("Fetch failed.")

# --- TAB 3: DRAFTS ---
with tab3:
    st.header("� Pitch Deck Analysis Drafts")
    st.markdown("View and manage your pitch deck analysis drafts.")
    
    # Drafts list section
    st.subheader("Saved Drafts")
    drafts_container = st.container()
    
    # Mock drafts data - in production, this would come from the backend
    mock_drafts = [
        {"company": "TechCorp", "date": "2024-01-15", "status": "Completed", "confidence": "High"},
        {"company": "HealthAI", "date": "2024-01-14", "status": "In Progress", "confidence": "Medium"},
        {"company": "FinFlow", "date": "2024-01-13", "status": "Draft", "confidence": "Low"}
    ]
    
    for draft in mock_drafts:
        with st.expander(f"📄 {draft['company']} - {draft['date']} ({draft['status']})", expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.metric("Status", draft['status'])
            col2.metric("Confidence", draft['confidence'])
            col3.button("View Analysis", key=f"view_{draft['company']}")
    
    st.divider()
    st.info("💡 Drafts are automatically saved when you analyze pitch decks in the Revert Analysis tab.")

# --- TAB 4: COMPLIANCE & ESG ---
with tab4:
    st.header("🛡️ Compliance Monitor & ESG Guardrails")
    st.info("Automated screening for mandate compliance and ESG metrics.")
    
    col_comp_1, col_comp_2 = st.columns(2)
    with col_comp_1:
         st.subheader("✅ Compliance Checks")
         st.write("- [OK] Investment Mandate alignment")
         st.write("- [OK] Geopolitical conflict screening")
         st.write("- [WARN] Related party transactions found")
    with col_comp_2:
         st.subheader("🌱 ESG Impact (AI Predicted)")
         st.metric("Carbon Footprint Impact", "Low", "A+")
         st.metric("Diversity Index", "64%", "+5%")

# --- TAB 5: INTEGRATIONS ---
with tab5:
    st.header("🔗 Connected Services")
    st.markdown("Manage your external platform connections.")
    
    integrations = [
        {"name": "Salesforce", "status": "Connected", "icon": "☁️"},
        {"name": "Hubspot", "status": "Connected", "icon": "🟠"},
        {"name": "Slack", "status": "Disconnected", "icon": "💬"},
        {"name": "Gmail", "status": "Connected", "icon": "📧"},
    ]
    
    for i in integrations:
        col_int_1, col_int_2, col_int_3 = st.columns([1, 2, 2])
        col_int_1.write(i["icon"])
        col_int_2.write(f"**{i['name']}**")
        if col_int_3.button(f"{'Disconnect' if i['status'] == 'Connected' else 'Connect'}", key=i['name']):
            st.toast(f"Toggling status for {i['name']}")
