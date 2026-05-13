import streamlit as st
from snapshot_page import render_snapshot_tab

st.set_page_config(
    page_title="SCB FX Snapshot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_snapshot_tab()
