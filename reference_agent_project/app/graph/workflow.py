from typing import TypedDict
from langgraph.graph import StateGraph, END
from app.agents.reference_agent import ReferenceAgent
from app.models.schemas import SearchRequest

class RefState(TypedDict, total=False):
    request: SearchRequest
    rewritten_query: str
    result: dict

agent = ReferenceAgent()

def rewrite_node(state: RefState):
    return {'rewritten_query': agent.rewrite_query(state['request'].query)}

def retrieve_node(state: RefState):
    res = agent.retrieval.search(state['request'], rewritten_query=state['rewritten_query'])
    return {'result': res.model_dump()}

def build_graph():
    g = StateGraph(RefState)
    g.add_node('rewrite', rewrite_node)
    g.add_node('retrieve', retrieve_node)
    g.set_entry_point('rewrite')
    g.add_edge('rewrite', 'retrieve')
    g.add_edge('retrieve', END)
    return g.compile()
