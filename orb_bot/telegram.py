"""
Minimal Telegram interface (Bot API over HTTPS, long polling).

Only messages coming from TELEGRAM_CHAT_ID are executed: anybody else who finds
the bot gets no answer, so nobody can pause or stop it.
"""
import logging
import threading
import time

import requests

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{}/{}"


class Telegram:
    def __init__(self, token, chat_id):
        self.token, self.chat_id = token, str(chat_id)
        self.enabled = bool(token and chat_id)
        self.offset = 0
        self.handlers = {}

    def _call(self, method, **params):
        r = requests.post(API.format(self.token, method), data=params, timeout=35)
        r.raise_for_status()
        return r.json()

    def send(self, text):
        if not self.enabled:
            log.info("[telegram disabled] %s", text.replace("\n", " | "))
            return
        try:
            self._call("sendMessage", chat_id=self.chat_id, text=text)
        except requests.RequestException as exc:
            log.warning("Telegram send failed: %s", exc)

    def command(self, name):
        def register(fn):
            self.handlers["/" + name] = fn
            return fn
        return register

    def _poll_once(self):
        updates = self._call("getUpdates", offset=self.offset + 1, timeout=30).get("result", [])
        for u in updates:
            self.offset = u["update_id"]
            msg = u.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != self.chat_id:
                log.warning("Ignored command from unauthorized chat %s", msg.get("chat", {}).get("id"))
                continue
            cmd = (msg.get("text") or "").strip().split()[0:1]
            handler = self.handlers.get(cmd[0].lower().split("@")[0]) if cmd else None
            reply = handler() if handler else "Commands: " + " ".join(sorted(self.handlers))
            if reply:
                self.send(reply)

    def start(self):
        if not self.enabled:
            return
        try:  # skip messages sent while the bot was offline
            pending = self._call("getUpdates", offset=-1, timeout=0).get("result", [])
            if pending:
                self.offset = pending[-1]["update_id"]
        except requests.RequestException as exc:
            log.warning("Telegram init failed: %s", exc)

        def loop():
            while True:
                try:
                    self._poll_once()
                except Exception as exc:  # keep the listener alive, but log the reason
                    log.warning("Telegram polling error: %s", exc)
                    time.sleep(5)
        threading.Thread(target=loop, daemon=True).start()
