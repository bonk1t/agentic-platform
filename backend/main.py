import json
import os
import time

import openai
from flask import Flask, jsonify, request

import functions


def create_app():
    app = Flask(__name__)

    openai_api_key = os.getenv("OPENAI_API_KEY")
    client = openai.OpenAI(api_key=openai_api_key)

    assistant_id = functions.create_software_assistant(client)

    @app.route("/start", methods=["GET"])
    def start_conversation():
        thread = client.beta.threads.create()
        return jsonify({"thread_id": thread.id})

    @app.route("/chat", methods=["POST"])
    def chat():
        data = request.json
        thread_id = data.get("thread_id")
        user_input = data.get("message", "")

        if not thread_id:
            return jsonify({"error": "Missing thread_id"}), 400

        client.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=user_input
        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id, assistant_id=assistant_id
        )

        while True:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run.id
            )
            if run_status.status == "completed":
                break
            elif run_status.status == "requires_action":
                for (
                    tool_call
                ) in run_status.required_action.submit_tool_outputs.tool_calls:
                    output = functions.handle_action(tool_call, thread_id, run.id)
                    client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread_id,
                        run_id=run.id,
                        tool_outputs=[
                            {"tool_call_id": tool_call.id, "output": json.dumps(output)}
                        ],
                    )
                time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        response = messages.data[0].content[0].text.value
        return jsonify({"response": response})

    return app
