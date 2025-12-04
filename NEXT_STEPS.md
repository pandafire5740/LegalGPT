# Current

# Future

# Complete
* ~~We probably don't need both FAISS and ChromaDB for vector searches. Let's use Chroma everywhere~~ ✅
* ~~Getting the error NameError: name 'user_query' is not defined when using /chat/query/stream~~ ✅
* ~~Let's look at injecting our VectorStore instead of constructing a new wrapper each time we need it~~ ✅
* ~~contextassembler._gather_inventory should probably live in the vectorstore itself (and is potentially just a metadata search)~~ ✅
* ~~Let's look at assemble_context from the perspective of context window pollution/management~~ ✅
* ~~Let's change the detect_intent function to be a multi-round tool-calling flow instead~~ ✅
* ~~Let's DRY up chat_query_stream and chat_query~~ ✅
* ~~Let's remove ai_service.py and remaining usages~~ ✅
* ~~Let's implement an overall sentiment score in the Extract tab that indicates whether this contract is good to sign as is~~ ✅
* ~~Let's implement some better formatting and newlining for the LLM's responses in the Chat feature. Current results are in one-block, paragraph form and difficult to read~~ ✅
* ~~Change the "Quick Action" tab on the left menu panel to "Document Management", with the option to upload local documents (existing) and manage any local files (new)~~ ✅
* ~~Center the chat, search, and extract tab selection menu~~ ✅