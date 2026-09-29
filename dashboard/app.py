"""
Streamlit Dashboard (Phase 9).

Connects to Postgres and visualizes the loan onboarding pipeline.
Shows Straight-Through Processing (STP) rate, decision breakdown, and manual review queue.
"""
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

# Database Connection
# The dashboard runs in its own container and connects to 'postgres'
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_USER = os.getenv("POSTGRES_USER", "appuser")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "changeme")
DB_NAME = os.getenv("POSTGRES_DB", "creditunion")

DB_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

@st.cache_resource
def get_engine():
    return create_engine(DB_URL)

def load_data(query: str):
    engine = get_engine()
    return pd.read_sql(query, engine)

st.set_page_config(page_title="Credit Union Analytics", page_icon="🏦", layout="wide")
st.title("🏦 Credit Union Loan Onboarding — Analytics Dashboard")

try:
    # 1. Load Data
    apps_df = load_data("SELECT * FROM applications")
    
    if apps_df.empty:
        st.warning("No applications found in the database. Have you run the pipeline yet?")
        st.stop()
        
    # 2. Key Metrics
    st.header("KPIs")
    col1, col2, col3 = st.columns(3)
    
    total_apps = len(apps_df)
    auto_approved = len(apps_df[apps_df['status'] == 'AUTO_APPROVED'])
    stp_rate = (auto_approved / total_apps) * 100 if total_apps > 0 else 0
    human_review = len(apps_df[apps_df['status'] == 'HUMAN_REVIEW'])
    
    col1.metric("Total Applications Processed", f"{total_apps}")
    col2.metric("Straight-Through Processing (STP) Rate", f"{stp_rate:.1f}%")
    col3.metric("Applications Pending Human Review", f"{human_review}")
    
    st.markdown("---")
    
    # 3. Visualizations
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("Decision Breakdown")
        status_counts = apps_df['status'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Count']
        fig1 = px.pie(status_counts, values='Count', names='Status', hole=0.4, 
                      color='Status',
                      color_discrete_map={
                          'AUTO_APPROVED': '#2e7d32', 
                          'AUTO_REJECTED': '#c62828',
                          'HUMAN_REVIEW': '#f9a825',
                          'APPROVED': '#4caf50',
                          'REJECTED': '#e53935'
                      })
        st.plotly_chart(fig1, use_container_width=True)
        
    with col_chart2:
        st.subheader("Auto-Rejection Reasons")
        rejected_df = apps_df[apps_df['status'] == 'AUTO_REJECTED'].copy()
        if not rejected_df.empty:
            reason_counts = rejected_df['decision_reason'].value_counts().reset_index()
            reason_counts.columns = ['Reason', 'Count']
            fig2 = px.bar(reason_counts, x='Reason', y='Count', color='Reason')
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No auto-rejected applications yet.")
            
    # 4. Human Review Queue
    st.markdown("---")
    st.subheader("Human Review Queue")
    # Extract flags from rules_result JSON
    apps_df['flags'] = apps_df['rules_result'].apply(lambda x: x.get('flags', []) if isinstance(x, dict) else [])

    review_queue = apps_df[apps_df['status'] == 'HUMAN_REVIEW'][
        ['id', 'applicant_name', 'requested_loan_amount', 'flags', 'created_at']
    ]
    if not review_queue.empty:
        st.dataframe(review_queue, use_container_width=True)
    else:
        st.success("The human review queue is empty!")

except Exception as e:
    st.error(f"Failed to connect to the database or fetch data: {e}")
    st.info("Make sure the Postgres container is running and migrations have been applied.")
