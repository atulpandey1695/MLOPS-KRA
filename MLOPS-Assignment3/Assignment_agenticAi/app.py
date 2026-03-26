"""
FastAPI application exposing five LangGraph-powered AI agents as REST endpoints.
- Agent Bot: Single-turn chatbot (stateless)
- Memory Agent: Multi-turn chat with conversation history (session-based)
- ReAct Agent: Math problem solver with tools (stateless)
- Drafter Agent: Document writing assistant (session-based)
- RAG Agent: PDF-based Q&A using ChromaDB (stateless)
"""

import os
from typing import TypedDict, List, Annotated, Sequence, Union, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from dotenv import load_dotenv

load_dotenv()

# Get API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
if not OPENAI_API_KEY:
    print("WARNING: OPENAI_API_KEY environment variable is not set. API calls will fail.")
    OPENAI_API_KEY = ""

# Lazy initialization of LLM - only when needed
def get_llm():
    key = os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY
    base_url = os.getenv("OPENAI_API_BASE") or OPENAI_API_BASE
    if not key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return ChatOpenAI(
        model=os.getenv("MODEL_NAME", MODEL_NAME),
        openai_api_key=key,
        base_url=base_url
    )

def get_embedding_model():
    key = os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY
    base_url = os.getenv("OPENAI_API_BASE") or OPENAI_API_BASE
    if not key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return OpenAIEmbeddings(
        model=os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL),
        openai_api_key=key,
        openai_api_base=base_url
    )

# Placeholder for lazy initialization
llm = None
embedding_model = None

# Global storage for session-based agents
memory_sessions: Dict[str, List] = {}
drafter_sessions: Dict[str, str] = {}

# =====================
# FastAPI Models
# =====================

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")

class SessionRequest(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    message: str = Field(..., description="User message")

class DrafterRequest(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    message: str = Field(..., description="User message")
    document_content: str = Field(default="", description="Current document content")

class ChatResponse(BaseModel):
    response: str
    session_id: str | None = None


# =====================
# AGENT 1: Agent Bot (Stateless)
# =====================

class AgentBotState(TypedDict):
    messages: List[HumanMessage]

def create_agent_bot():
    """Create a simple stateless chatbot graph"""
    
    def process(state: AgentBotState) -> AgentBotState:
        response = get_llm().invoke(state["messages"])
        state["messages"].append(response)
        return state
    
    graph = StateGraph(AgentBotState)
    graph.add_node("process", process)
    graph.add_edge(START, "process")
    graph.add_edge("process", END)
    return graph.compile()


# =====================
# AGENT 2: Memory Agent (Session-based)
# =====================

class MemoryAgentState(TypedDict):
    messages: List[Union[HumanMessage, AIMessage]]

def create_memory_agent():
    """Create a memory-aware chatbot graph"""
    
    def process(state: MemoryAgentState) -> MemoryAgentState:
        response = get_llm().invoke(state["messages"])
        if hasattr(response, 'content'):
            state["messages"].append(AIMessage(content=response.content))
        return state
    
    graph = StateGraph(MemoryAgentState)
    graph.add_node("process", process)
    graph.add_edge(START, "process")
    graph.add_edge("process", END)
    return graph.compile()


# =====================
# AGENT 3: ReAct Agent (Stateless)
# =====================

@tool
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

@tool
def subtract(a: int, b: int) -> int:
    """Subtract b from a."""
    return a - b

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers together."""
    return a * b

react_tools = [add, subtract, multiply]

class ReActState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

def create_react_agent():
    """Create a ReAct agent with math tools"""
    
    model = get_llm().bind_tools(react_tools)
    
    def model_call(state: ReActState) -> ReActState:
        system_prompt = SystemMessage(
            content="You are my AI assistant. Please answer my query to the best of your ability."
        )
        response = model.invoke([system_prompt] + state["messages"])
        return {"messages": [response]}
    
    def should_continue(state: ReActState) -> str:
        messages = state["messages"]
        last_message = messages[-1]
        if not last_message.tool_calls:
            return "end"
        return "continue"
    
    graph = StateGraph(ReActState)
    graph.add_node("our_agent", model_call)
    graph.add_node("tools", ToolNode(react_tools))
    graph.set_entry_point("our_agent")
    graph.add_conditional_edges(
        "our_agent",
        should_continue,
        {"continue": "tools", "end": END}
    )
    graph.add_edge("tools", "our_agent")
    return graph.compile()


# =====================
# AGENT 4: Drafter Agent (Session-based)
# =====================

@tool
def update_document(content: str) -> str:
    """Updates the document with the provided content."""
    return "Document updated successfully!"

@tool
def save_document(filename: str) -> str:
    """Save the current document to a text file."""
    return f"Document would be saved to {filename}"

drafter_tools = [update_document, save_document]

class DrafterState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

def create_drafter_agent():
    """Create a document drafting agent"""
    
    model = get_llm().bind_tools(drafter_tools)
    
    def our_agent(state: DrafterState) -> DrafterState:
        system_prompt = SystemMessage(content="""
        You are Drafter, a helpful writing assistant. You help users update and modify documents.
        - If the user wants to update or modify content, use the 'update_document' tool.
        - If the user wants to save and finish, use the 'save_document' tool.
        """)
        
        all_messages = [system_prompt] + list(state["messages"])
        response = model.invoke(all_messages)
        return {"messages": list(state["messages"]) + [response]}
    
    def should_continue(state: DrafterState) -> str:
        messages = state["messages"]
        for message in reversed(messages):
            if isinstance(message, ToolMessage) and "saved" in message.content.lower():
                return "end"
        return "continue"
    
    graph = StateGraph(DrafterState)
    graph.add_node("agent", our_agent)
    graph.add_node("tools", ToolNode(drafter_tools))
    graph.set_entry_point("agent")
    graph.add_edge("agent", "tools")
    graph.add_conditional_edges(
        "tools",
        should_continue,
        {"continue": "agent", "end": END}
    )
    return graph.compile()


# =====================
# AGENT 5: RAG Agent (Stateless)
# =====================

# Initialize RAG components lazily
vectorstore = None
retriever_tool = None
rag_agent = None

def init_rag():
    """Initialize RAG components - called on first request"""
    global vectorstore, retriever_tool, rag_agent
    
    if vectorstore is not None:
        return
    
    pdf_path = os.path.join(os.path.dirname(__file__), "Agents", "Stock_Market_Performance_2024.pdf")
    
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    pdf_loader = PyPDFLoader(pdf_path)
    pages = pdf_loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    pages_split = text_splitter.split_documents(pages)
    
    persist_directory = os.path.join(os.path.dirname(__file__), "Agents", "chroma_db")
    
    vectorstore = Chroma.from_documents(
        documents=pages_split,
        embedding=get_embedding_model(),
        persist_directory=persist_directory,
        collection_name="stock_market"
    )
    
    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 5})
    
    @tool
    def retriever_tool_func(query: str) -> str:
        """Search and return information from the Stock Market Performance 2024 document."""
        docs = retriever.invoke(query)
        if not docs:
            return "No relevant information found."
        return "\n\n".join([f"Document {i+1}:\n{doc.page_content}" for i, doc in enumerate(docs)])
    
    retriever_tool = retriever_tool_func
    tools = [retriever_tool]
    
    class RAGState(TypedDict):
        messages: Annotated[Sequence[BaseMessage], add_messages]
    
    def should_continue(state: RAGState):
        result = state['messages'][-1]
        return hasattr(result, 'tool_calls') and len(result.tool_calls) > 0
    
    system_prompt = """
    You are an intelligent AI assistant who answers questions about Stock Market Performance in 2024.
    Use the retriever tool to answer questions about stock market performance data.
    Please cite the specific parts of the documents you use in your answers.
    """
    
    tools_dict = {t.name: t for t in tools}
    rag_llm = get_llm().bind_tools(tools)
    
    def call_llm(state: RAGState) -> RAGState:
        messages = [SystemMessage(content=system_prompt)] + list(state['messages'])
        message = rag_llm.invoke(messages)
        return {'messages': [message]}
    
    def take_action(state: RAGState) -> RAGState:
        tool_calls = state['messages'][-1].tool_calls
        results = []
        for t in tool_calls:
            if t['name'] in tools_dict:
                result = tools_dict[t['name']].invoke(t['args'].get('query', ''))
            else:
                result = "Invalid tool name"
            results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=str(result)))
        return {'messages': results}
    
    graph = StateGraph(RAGState)
    graph.add_node("llm", call_llm)
    graph.add_node("retriever_agent", take_action)
    graph.add_conditional_edges(
        "llm",
        should_continue,
        {True: "retriever_agent", False: END}
    )
    graph.add_edge("retriever_agent", "llm")
    graph.set_entry_point("llm")
    
    rag_agent = graph.compile()


# =====================
# Lazy initialization of agents
# =====================

agent_bot = None
memory_agent = None
react_agent = None
drafter_agent = None

def get_agent_bot():
    global agent_bot
    if agent_bot is None:
        agent_bot = create_agent_bot()
    return agent_bot

def get_memory_agent():
    global memory_agent
    if memory_agent is None:
        memory_agent = create_memory_agent()
    return memory_agent

def get_react_agent():
    global react_agent
    if react_agent is None:
        react_agent = create_react_agent()
    return react_agent

def get_drafter_agent():
    global drafter_agent
    if drafter_agent is None:
        drafter_agent = create_drafter_agent()
    return drafter_agent


# =====================
# FastAPI App
# =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting LangGraph Agents API...")
    yield
    # Shutdown
    print("Shutting down LangGraph Agents API...")

app = FastAPI(title="LangGraph AI Agents", version="1.0.0", lifespan=lifespan)


# =====================
# API Routes
# =====================

@app.get("/")
async def root():
    return {"message": "LangGraph AI Agents API", "agents": [
        "Agent Bot (POST /api/agent-bot/chat)",
        "Memory Agent (POST /api/memory/chat)",
        "ReAct Agent (POST /api/react/solve)",
        "Drafter Agent (POST /api/drafter/chat)",
        "RAG Agent (POST /api/rag/query)"
    ]}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/api/agent-bot/chat", response_model=ChatResponse)
async def agent_bot_chat(request: ChatRequest):
    """Single-turn Gemini chatbot (stateless)"""
    result = get_agent_bot().invoke({"messages": [HumanMessage(content=request.message)]})
    return ChatResponse(response=result["messages"][-1].content)


@app.post("/api/memory/chat", response_model=ChatResponse)
async def memory_chat(request: SessionRequest):
    """Multi-turn chat with conversation history (session-based)"""
    session_id = request.session_id
    
    if session_id not in memory_sessions:
        memory_sessions[session_id] = []
    
    memory_sessions[session_id].append(HumanMessage(content=request.message))
    
    result = get_memory_agent().invoke({"messages": memory_sessions[session_id]})
    memory_sessions[session_id] = result["messages"]
    
    return ChatResponse(
        response=result["messages"][-1].content,
        session_id=session_id
    )


@app.post("/api/react/solve", response_model=ChatResponse)
async def react_solve(request: ChatRequest):
    """Solve math queries using add/subtract/multiply tools (stateless)"""
    result = get_react_agent().invoke(
        {"messages": [("user", request.message)]},
        stream_mode="values"
    )
    
    final_message = result["messages"][-1]
    if hasattr(final_message, "content"):
        response = final_message.content
    else:
        response = str(final_message)
    
    return ChatResponse(response=response)


@app.post("/api/drafter/chat", response_model=ChatResponse)
async def drafter_chat(request: DrafterRequest):
    """Document drafting with update/save tools (session-based)"""
    session_id = request.session_id
    
    if session_id not in drafter_sessions:
        drafter_sessions[session_id] = ""
    
    drafter_sessions[session_id] = request.document_content
    
    # Build messages including system prompt and document context
    system_msg = SystemMessage(content=f"""
    You are Drafter, a helpful writing assistant. You help users create and modify documents.
    Current document content:
    {request.document_content}
    
    - If the user wants to update or create content, use the 'update_document' tool with the new content.
    - If the user wants to save and finish, use the 'save_document' tool.
    """)
    
    state = {"messages": [system_msg, HumanMessage(content=request.message)]}
    
    # Run the agent
    result = await get_drafter_agent().ainvoke(state)
    
    # Get the last message
    if result.get("messages"):
        last_msg = result["messages"][-1]
        if isinstance(last_msg, ToolMessage):
            # Extract the document content from the tool result
            response_text = last_msg.content
            # Try to extract the document from the response
            if "updated document:" in response_text.lower():
                # Extract the actual document content
                lines = response_text.split("\n")
                doc_content = "\n".join(lines[1:]).strip() if len(lines) > 1 else response_text
                drafter_sessions[session_id] = doc_content
            return ChatResponse(
                response=response_text,
                session_id=session_id
            )
        elif hasattr(last_msg, "content"):
            return ChatResponse(
                response=last_msg.content,
                session_id=session_id
            )
    
    return ChatResponse(response="No response generated", session_id=session_id)


@app.post("/api/rag/query", response_model=ChatResponse)
async def rag_query(request: ChatRequest):
    """Answer questions about Stock Market 2024 PDF using RAG (stateless)"""
    global rag_agent
    if rag_agent is None:
        init_rag()
    
    messages = [HumanMessage(content=request.message)]
    result = rag_agent.invoke({"messages": messages})
    
    return ChatResponse(response=result["messages"][-1].content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)
