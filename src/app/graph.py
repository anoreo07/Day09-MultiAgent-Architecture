from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.config import Settings
from app.data_access import ShoppingDataStore, build_data_tools
from app.prompts import (
    DATA_WORKER_PROMPT,
    POLICY_WORKER_PROMPT,
    RESPONSE_WORKER_PROMPT,
    SUPERVISOR_PROMPT,
)
from app.state import ShoppingState
from provider import get_chat_model
from rag.embeddings import SentenceTransformerEmbeddings
from rag.vector_store import ChromaPolicyStore


class ShoppingAssistant:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        
        # Load chat model
        self.llm = get_chat_model(self.settings)
        
        # Load embedding model
        self.embeddings = SentenceTransformerEmbeddings(self.settings.embedding_model_name)
        
        # Load data store
        self.data_store = ShoppingDataStore(self.settings.orders_path)
        
        # Load vector store
        self.policy_store = ChromaPolicyStore(
            persist_directory=self.settings.chroma_dir,
            embedding_model=self.embeddings
        )
        
        # Build tools
        self.data_tools = build_data_tools(self.data_store)
        
        # Build graph
        self.graph = build_graph(self.llm, self.policy_store, self.data_tools)

    def ask(
        self,
        question: str,
        trace_file: Path | None = None,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if rebuild_index:
            self.policy_store.rebuild(self.settings.policy_path)
        else:
            self.policy_store.ensure_index(self.settings.policy_path)
            
        initial_state: ShoppingState = {
            "question": question,
            "trace": [],
            "route": {},
            "policy_result": {},
            "data_result": {},
            "final_answer": ""
        }
        
        result = self.graph.invoke(initial_state)
        
        if trace_file:
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            with open(trace_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                
        return result

    def run_batch(
        self,
        test_file: Path,
        output_dir: Path,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        if not test_file.exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")
            
        with open(test_file, "r", encoding="utf-8") as f:
            test_data = json.load(f)
            
        if isinstance(test_data, list):
            questions = test_data
        else:
            questions = test_data.get("questions", [])
            
        results = []
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for i, item in enumerate(questions):
            q = item.get("question", "")
            print(f"Running test {i+1}/{len(questions)}: {q}")
            
            trace_name = f"test_{i:03d}.json"
            res = self.ask(q, trace_file=output_dir / trace_name, rebuild_index=(i==0 and rebuild_index))
            results.append({
                "id": i,
                "question": q,
                "expected": item.get("expected_route"),
                "actual_route": res.get("route"),
                "final_answer": res.get("final_answer")
            })
            
        summary = {
            "total": len(questions),
            "results": results
        }
        
        with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            
        return summary


def build_graph(llm: Any, policy_store: ChromaPolicyStore, data_tools: list) -> Any:
    workflow = StateGraph(ShoppingState)
    
    # Curry nodes with necessary dependencies
    def supervisor(state: ShoppingState):
        return supervisor_node(state, llm)
        
    def policy_worker(state: ShoppingState):
        return worker_1_policy_node(state, llm, policy_store)
        
    def data_worker(state: ShoppingState):
        return worker_2_data_node(state, llm, data_tools)
        
    def response_worker(state: ShoppingState):
        return worker_3_response_node(state, llm)
    
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("worker_1_policy", policy_worker)
    workflow.add_node("worker_2_data", data_worker)
    workflow.add_node("worker_3_response", response_worker)
    
    workflow.set_entry_point("supervisor")
    
    def router(state: ShoppingState) -> list[str]:
        route = state.get("route", {})
        if route.get("status") == "clarification_needed":
            return ["worker_3_response"]
            
        next_nodes = []
        if route.get("needs_policy"):
            next_nodes.append("worker_1_policy")
        if route.get("needs_data"):
            next_nodes.append("worker_2_data")
            
        if not next_nodes:
            return ["worker_3_response"]
            
        return next_nodes

    workflow.add_conditional_edges(
        "supervisor",
        router,
        {
            "worker_1_policy": "worker_1_policy",
            "worker_2_data": "worker_2_data",
            "worker_3_response": "worker_3_response"
        }
    )
    
    workflow.add_edge("worker_1_policy", "worker_3_response")
    workflow.add_edge("worker_2_data", "worker_3_response")
    workflow.add_edge("worker_3_response", END)
    
    return workflow.compile()


def supervisor_node(state: ShoppingState, llm: Any) -> ShoppingState:
    messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=state["question"])
    ]
    response = llm.invoke(messages)
    
    # Simple JSON parsing from response
    content = response.content
    try:
        # Try to find JSON in the response
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            route = json.loads(json_match.group())
        else:
            route = json.loads(content)
    except Exception:
        # Fallback if parsing fails
        route = {
            "status": "ok",
            "needs_policy": True,
            "needs_data": True,
            "clarification_question": None
        }
        
    return {
        "route": route,
        "trace": [{"node": "supervisor", "output": route}]
    }


def worker_1_policy_node(state: ShoppingState, llm: Any, policy_store: ChromaPolicyStore) -> ShoppingState:
    # 1. Search Policy
    query = state["question"]
    hits = policy_store.search(query)
    
    # 2. Ask LLM to summarize
    context = "\n\n".join([f"Source: {h['citation']}\nContent: {h['content']}" for h in hits])
    
    messages = [
        SystemMessage(content=POLICY_WORKER_PROMPT),
        HumanMessage(content=f"Question: {state['question']}\n\nRetrieved Context:\n{context}")
    ]
    response = llm.invoke(messages)
    
    try:
        json_match = re.search(r"\{.*\}", response.content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(response.content)
    except Exception:
        result = {"status": "ok", "summary": response.content, "facts": [], "citations": []}
        
    return {
        "policy_result": result,
        "trace": [{"node": "worker_1_policy", "hits": hits, "output": result}]
    }


def worker_2_data_node(state: ShoppingState, llm: Any, data_tools: list) -> ShoppingState:
    # Data worker uses tool calling
    llm_with_tools = llm.bind_tools(data_tools)
    
    messages = [
        SystemMessage(content=DATA_WORKER_PROMPT),
        HumanMessage(content=state["question"])
    ]
    
    # Keep calling tools until LLM provides a final JSON
    curr_messages = messages
    tool_outputs = []
    
    for _ in range(5): # Limit tool iterations
        response = llm_with_tools.invoke(curr_messages)
        curr_messages.append(response)
        
        if not response.tool_calls:
            break
            
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            # Find the tool
            target_tool = next((t for t in data_tools if t.name == tool_name), None)
            if target_tool:
                output = target_tool.invoke(tool_args)
                tool_outputs.append({"tool": tool_name, "args": tool_args, "output": output})
                curr_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": tool_name,
                    "content": output
                })
    
    # Final cleanup to get JSON
    final_prompt = "Dựa trên các thông tin đã tra cứu được, hãy trả về kết quả dưới dạng JSON như đã quy định trong DATA_WORKER_PROMPT."
    curr_messages.append(HumanMessage(content=final_prompt))
    final_response = llm.invoke(curr_messages)
    
    try:
        json_match = re.search(r"\{.*\}", final_response.content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(final_response.content)
    except Exception:
        result = {"status": "ok", "summary": final_response.content, "facts": [], "missing_fields": []}

    return {
        "data_result": result,
        "trace": [{"node": "worker_2_data", "tool_calls": tool_outputs, "output": result}]
    }


def worker_3_response_node(state: ShoppingState, llm: Any) -> ShoppingState:
    combined_context = f"""
Supervisor Route: {json.dumps(state['route'], ensure_ascii=False)}
Policy Worker Result: {json.dumps(state.get('policy_result', {}), ensure_ascii=False)}
Data Worker Result: {json.dumps(state.get('data_result', {}), ensure_ascii=False)}
"""
    
    messages = [
        SystemMessage(content=RESPONSE_WORKER_PROMPT),
        HumanMessage(content=f"Question: {state['question']}\n\nContext:\n{combined_context}")
    ]
    response = llm.invoke(messages)
    
    return {
        "final_answer": response.content,
        "trace": [{"node": "worker_3_response", "output": response.content}]
    }

import re # Needed for re.search
