
<p align="center">
  <h1 align="center">🔥 TELEGRAM FIGHT VOICE CHAT BOT 🔥</h1>
</p>

<p align="center">
  <a href="https://github.com/ITZ-HAKEEB/VAMPIRE-FIGHT">
    <img src="https://img.shields.io/badge/GitHub-Repository-blue?style=for-the-badge&logo=github" alt="GitHub Repo">
  </a>
  <a href="https://python.org">
    <img src="https://img.shields.io/badge/Python-3.10%2B-green?style=for-the-badge&logo=python" alt="Python">
  </a>
  <a href="https://heroku.com">
    <img src="https://img.shields.io/badge/Heroku-Ready-purple?style=for-the-badge&logo=heroku" alt="Heroku">
  </a>
</p>

---

### 🚀 About The Project
**VAMPIRE-FIGHT** is a powerful Telegram Userbot and Voice Chat bridge designed specifically for Telegram group fights. It allows a userbot to automatically connect to a Logger Voice Chat and stream/bridge audio to a Target Voice Chat with customizable volume boost control (1% to 500%).

---

### 👑 Features
* **VC Bridging:** Automatically connects your userbot to Logger and Target group voice chats.
* **Volume Boost:** Extensible volume control ranging from `1%` up to `500%` for loud and clear fight audio.
* **Sudo System:** Add or remove authorized sudo users using simple commands (`.addsudo` / `.rmsudo`).
* **Multi-User Access:** Commands can be executed by the Owner, Sudo users, and the Userbot account itself.
* **Heroku Ready:** Supports 24/7 deployment using Docker and Heroku workflow.

---

### ⚙️ Available Commands (Prefix: `.`)
* `.help` - Show the interactive help menu.
* `.joinvc <logger_id> <target_id>` - Connect the userbot to Logger VC & Target VC.
* `.leavevc` - Disconnect from active voice chats.
* `.volume <1-500>` - Adjust audio boost volume level.
* `.addsudo <user_id>` - Add a new user to the sudo list (Owner only).
* `.rmsudo <user_id>` - Remove a user from the sudo list (Owner only).
* `.sudolist` - View all current authorized sudo users.

---

### ☁️ Heroku Deployment
Deploy this bot directly to Heroku with a single click using the big deploy button below:

<p align="center">
  <a href="https://heroku.com/deploy?template=https://github.com/ITZ-HAKEEB/VAMPIRE-FIGHT">
    <img src="https://www.herokucdn.com/deploy/button.svg" alt="Deploy to Heroku" width="250px">
  </a>
</p>

---

### 🛠️ Required Environment Variables
When deploying to Heroku, make sure to set the following Config Vars:
1. `API_ID` - Get from my.telegram.org
2. `API_HASH` - Get from my.telegram.org
3. `SESSION_STRING` - Your Pyrogram v2 String Session
4. `OWNER_ID` - Your Telegram User ID

---

### 💻 Connect With Me
* **GitHub:** [ITZ-HAKEEB](https://github.com/ITZ-HAKEEB)
* 
