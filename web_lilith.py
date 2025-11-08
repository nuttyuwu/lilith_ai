import os
import threading
import configparser
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

import lilith_ai

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
config = configparser.ConfigParser()
config.read(CONFIG_PATH)

DEFAULT_USER_NAME = ""
# Create shared AI/memory layer (display not needed for web)
Lilith_AI = lilith_ai.LilithAI(None, config, BASE_DIR, DEFAULT_USER_NAME)
MEMORY = Lilith_AI.Lilith_mem
PERSONA_TEXT = Lilith_AI.persona
MEMORY_DATA = Lilith_AI.memory

app = Flask(__name__, static_folder='static')
allowed_origins = os.getenv("CORS_ORIGINS", "*")
CORS(app, resources={
    r"/chat": {"origins": allowed_origins},
    r"/nickname": {"origins": allowed_origins},
})

memory_lock = threading.Lock()

@app.route('/')
def home():
    debug = {
        "cwd": os.getcwd(),
        "base_dir": BASE_DIR,
        "persona_file": config['ai_config']['persona'],
        "memory_file": config['ai_config']['memory'],
        "persona_length": len(PERSONA_TEXT),
        "memory_count": len(MEMORY_DATA.get("conversation", [])),
    }
    recent_memory = MEMORY_DATA.get("conversation", [])[-20:]
    user_name = MEMORY.get_user_name(MEMORY_DATA)
    name_set = MEMORY_DATA.get("meta", {}).get("user_name_set", False)
    return render_template(
        'index.html',
        persona=PERSONA_TEXT,
        memory=recent_memory,
        debug=debug,
        user_name=user_name,
        user_name_set=name_set,
    )

@app.route('/nickname', methods=['GET', 'POST'])
def nickname():
    with memory_lock:
        if request.method == 'GET':
            return jsonify({'user_name': Lilith_AI.get_user_name()})
        payload = request.json or {}
        new_name = (payload.get('user_name') or '').strip()
        if not new_name:
            return jsonify({'error': 'nickname required'}), 400
        Lilith_AI.set_user_name(new_name)
        return jsonify({'user_name': Lilith_AI.get_user_name()})

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').strip()
    if not user_msg:
        return jsonify({'reply': '', 'emotion': 'idle'}), 400

    with memory_lock:
        reply = Lilith_AI.lilith_reply(user_msg)
        emotion = Lilith_AI.get_current_emotion()

    return jsonify({'reply': reply, 'emotion': emotion})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
