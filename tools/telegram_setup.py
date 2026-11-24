#!/usr/bin/env python3
"""One-time Telegram setup:  python tools/telegram_setup.py <BOT_TOKEN>
1) create a bot with @BotFather, 2) send any message to your bot, 3) run this.
Finds your chat_id and stores token + chat_id in config.local.json (git-ignored)."""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from seccam import config as C  # noqa: E402


def main():
    token = sys.argv[1] if len(sys.argv) > 1 else C.load()["telegram"]["token"]
    if not token:
        sys.exit("usage: python tools/telegram_setup.py <BOT_TOKEN>")
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
    if r.status_code == 401:
        sys.exit("토큰이 올바르지 않습니다 (401). BotFather가 준 토큰을 다시 확인하세요.")
    r.raise_for_status()
    chats = {}
    for u in r.json().get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat")
        if chat:
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or ""
    if not chats:
        sys.exit("봇에게 온 메시지가 없습니다. 텔레그램에서 봇 대화방에 아무 메시지나 보낸 뒤 다시 실행하세요.")
    chat_id, who = list(chats.items())[-1]
    path = C.save_local({"telegram": {"token": token, "chat_id": str(chat_id)}})
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  data={"chat_id": chat_id, "text": "✅ Pi 보안카메라 알림이 연결되었습니다."}, timeout=20)
    print(f"chat_id={chat_id} ({who}) 저장 -> {path}\n텔레그램에 테스트 메시지를 보냈습니다.")


if __name__ == "__main__":
    main()
