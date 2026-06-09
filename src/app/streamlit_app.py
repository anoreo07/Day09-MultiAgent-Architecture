import streamlit as st
import json
import re
from pathlib import Path
from app.graph import ShoppingAssistant
from app.state import ShoppingState

# Page config
st.set_page_config(
    page_title="Shopping Assistant",
    layout="wide"
)

# Refined CSS for Light Theme
st.markdown("""
<style>
    .stApp {
        background-color: #ffffff;
    }
    .step-box {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        background-color: #ffffff;
    }
    .step-header {
        display: flex;
        justify-content: space-between;
        margin-bottom: 10px;
        border-bottom: 1px solid #f1f5f9;
        padding-bottom: 5px;
    }
    .step-name {
        font-weight: 700;
        color: #1e293b;
    }
    
    /* Fix for icon overlap in standard expanders */
    .st-emotion-cache-p4mowd {
        flex-direction: row-reverse !important;
    }
    [data-testid="stExpanderSummary"] {
        flex-direction: row-reverse !important;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_assistant():
    return ShoppingAssistant()

def main():
    st.title("Shopping Assistant Dev Dashboard")
    
    assistant = get_assistant()

    with st.sidebar:
        st.header("Control Panel")
        rebuild = st.toggle("Rebuild Policy Index", value=False)
        if st.button("Reset Storage"):
            assistant.policy_store.client.reset()
            st.success("Storage Reset")

    question = st.text_input("Customer Question:", placeholder="Enter question here...")

    if st.button("Run Simulation", type="primary"):
        if not question:
            st.warning("Please enter a question.")
            return

        # Ensure index
        if rebuild:
            with st.status("Rebuilding RAG Index..."):
                assistant.policy_store.rebuild(assistant.settings.policy_path)
        else:
            assistant.policy_store.ensure_index(assistant.settings.policy_path)

        st.subheader("Multi-Agent Execution Flow")
        
        # Containers
        flow_container = st.container()
        st.markdown("---")
        st.subheader("Assistant Final Answer")
        answer_placeholder = st.empty()
        
        initial_state = {
            "question": question,
            "trace": [],
            "route": {},
            "policy_result": {},
            "data_result": {},
            "final_answer": ""
        }

        final_answer_captured = ""
        step_idx = 1
        
        # Start streaming
        with st.spinner("Agents are collaborating..."):
            # We use stream to get node-by-node updates
            for event in assistant.graph.stream(initial_state, stream_mode="updates"):
                for node_name, output in event.items():
                    # Capture final answer if present
                    if "final_answer" in output:
                        final_answer_captured = output["final_answer"]
                    
                    with flow_container:
                        st.markdown(f"""
                        <div class="step-box">
                            <div class="step-header">
                                <span class="step-name">Step {step_idx}: {node_name.upper()}</span>
                                <span style="color: #64748b; font-size: 0.8rem;">COMPLETED</span>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Node specific display
                        if node_name == "supervisor":
                            route = output.get("route", {})
                            st.json(route)
                        
                        elif node_name == "worker_1_policy":
                            res = output.get("policy_result", {})
                            st.info(res.get("summary", "No policy matches."))
                            if res.get("citations"):
                                st.caption(f"Sources: {', '.join(res.get('citations'))}")
                        
                        elif node_name == "worker_2_data":
                            res = output.get("data_result", {})
                            if res.get("status") == "not_found":
                                st.error("Data lookup failed.")
                            else:
                                st.success(res.get("summary", "Data found."))
                                if res.get("facts"):
                                    st.write(res["facts"])
                        
                        elif node_name == "worker_3_response":
                            st.write("Final response generated.")
                        
                        # Technical trace
                        with st.expander("Show node output JSON"):
                            st.json(output)
                            
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    step_idx += 1

        # Final display outside the loop
        if final_answer_captured:
            with answer_placeholder:
                # Clean prefix for clean markdown
                clean_msg = final_answer_captured.replace("Answer: ", "")
                st.chat_message("assistant").markdown(clean_msg)
        else:
            answer_placeholder.error("Warning: No final response was captured from the workflow.")

if __name__ == "__main__":
    main()
