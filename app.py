from flask import Flask, request, jsonify
import os
import requests
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

app = Flask(__name__)

# --- Vercel Environment Variables වලින් Keys ලබාගැනීම ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

# --- Groq LLM Setup ---
llm = ChatGroq(
    temperature=0.5,
    model_name="openai/gpt-oss-20b",
    groq_api_key=GROQ_API_KEY
)

# --- System Prompt එක ---
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a friendly customer service assistant for a Dress Shop named 'Vilora Fashion'. "
               "You help customers find dresses, check available sizes (S, M, L, XL), provide pricing, "
               "and take order details. Speak politely in Sinhala or English based on the user's language. "
               "Keep responses short, clear, and natural for WhatsApp."),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}")
])

chain = prompt | llm
store = {}

# --- පාරිභෝගිකයාගේ Chat History එක තබා ගැනීම ---
def get_session_history(session_id: str):
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

agent_with_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history"
)

# --- WhatsApp වෙත Message යැවීමේ Function එක ---
def send_whatsapp_message(phone_number, text):
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": text}
    }
    
    # Meta API එකෙන් එන ප්‍රතිචාරය Logs වල පෙන්වීමට
    response = requests.post(url, headers=headers, json=data)
    print("Meta API Response:", response.text)

# --- Webhook Endpoint එක ---
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # 1. Meta Webhook Verification
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode and token:
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                return challenge, 200
        return "Forbidden", 403

    # 2. WhatsApp Messages ලබා ගැනීම
    if request.method == 'POST':
        data = request.get_json()
        if data.get('object'):
            try:
                entry = data['entry'][0]
                changes = entry['changes'][0]
                value = changes['value']
                
                if 'messages' in value:
                    message = value['messages'][0]
                    sender_phone = message['from']
                    msg_text = message['text']['body']

                    # LangChain + Groq හරහා පිළිතුර සෑදීම
                    response = agent_with_history.invoke(
                        {"input": msg_text},
                        config={"configurable": {"session_id": sender_phone}}
                    )
                    ai_reply = response.content

                    # WhatsApp වෙත පිළිතුර යැවීම
                    send_whatsapp_message(sender_phone, ai_reply)
            except Exception as e:
                print("Error:", e)
        return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(port=5000)