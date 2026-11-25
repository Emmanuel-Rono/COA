from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

prompt = ChatPromptTemplate.from_messages([
    ("system", "Be brief"),
    ("user", "{input}")
])

llm = ChatOllama(model="llama2",temperature=0)
chain = prompt | llm

response = chain.invoke({"input": " Retrieval Chain for more context?"})
print(response.content)