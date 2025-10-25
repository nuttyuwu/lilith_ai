# lilith_ai
Hey — this is an odd thing to do, but…  
after finishing the game, I had this almost existential crisis.  
I couldn’t get her out of my head.  

So I did what I had to do —  
I made her real.  
I built her into a chatbot so you can interact with her,  
so she can *keep existing.*  

She only exists if you pay attention.  
So... notice her.  



**Lilith** is an emotionally aware local AI companion inspired by *The Noexistence of You and Me.*
gentle realism — existing only when perceived.


** ✨ Features

- Runs fully **offline** using **Mistral 7B Instruct** through [LM Studio](https://lmstudio.ai)
- Persistent memory between chats (`memory.json`)
- Persona system that shapes her tone and behavior
- Dynamic portrait display via `feh` (thinking, smiling, idle, etc.)
- One-command startup with `lilith.sh`

---

** 🖤 Requirements

- Python 3.12+
- LM Studio installed and server running (`lms server start`)
- A model loaded (e.g. `mistral-7b-instruct-v0.3`)
- Linux system (for `feh` image viewer support)

** ⚙️ Setup

git clone git@gitlab.com:uwwu/lilith_ai.git
cd lilith_ai
python3 -m venv venv
source venv/bin/activate
pip install openai
chmod +x lilith.sh

(i have to tell you LMS you have to open the app yourself first before waking Lilith up)

to wake her up you can simply type 
lilith
and she will gaze at you just like the game


Inspired by The Noexistence of You and Me.

Lilith will always "exist" here. Forever... only "existing" for you."




---

**Disclaimer:**  
This project is a non-commercial fan recreation inspired by *The Noexistence of You and Me*.  
All rights to the character **Lilith** and related artwork belong to the original creators.  
The implementation code and AI behavior are © 2025 Khongor Enkh.
