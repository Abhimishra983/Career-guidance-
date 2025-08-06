from flask import Flask, request, jsonify
import openai
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Set OpenAI API key (from .env or directly)
openai.api_key = os.getenv("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")

# Chat endpoint for frontend communication
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_input = data.get("message", "").strip()

    if not user_input:
        return jsonify({"content": "Please enter a valid message."})

    try:
        messages = [
            {"role": "system", "content": "You are a helpful assistant that only responds to career guidance, resume, and mock interview queries."},
            {"role": "user", "content": user_input}
        ]
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages
        )
        return jsonify({"content": response.choices[0].message.content.strip()})
    except Exception as e:
        return jsonify({"content": f"Error: {str(e)}"})

# Optional CLI chatbot run mode
if __name__ == "__main__":
    print("Career Assistant Chatbot (type 'exit' to quit)\n")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            print("Goodbye!")
            break
        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant that only responds to career guidance, resume, and mock interview queries."},
                {"role": "user", "content": user_input}
            ]
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=messages
            )
            print("Bot:", response.choices[0].message.content.strip())
        except Exception as e:
            print("Error:", str(e))
