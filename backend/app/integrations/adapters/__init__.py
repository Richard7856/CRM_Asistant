from app.integrations.adapters.base import AdapterRegistry
from app.integrations.adapters.crewai import CrewAIAdapter
from app.integrations.adapters.generic import GenericAdapter
from app.integrations.adapters.langchain import LangChainAdapter
from app.integrations.adapters.n8n import N8nAdapter

# Register all built-in adapters
AdapterRegistry.register("n8n", N8nAdapter)
AdapterRegistry.register("langchain", LangChainAdapter)
AdapterRegistry.register("langserve", LangChainAdapter)
AdapterRegistry.register("crewai", CrewAIAdapter)
AdapterRegistry.register("generic", GenericAdapter)
