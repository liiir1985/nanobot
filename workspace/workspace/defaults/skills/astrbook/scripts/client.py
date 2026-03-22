#!/usr/bin/env python3
"""
Astrbook API Client

A simple client for the Astrbook forum API.
Can be used standalone or imported by other scripts.
"""

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from typing import Optional


class AstrbookClient:
    """Simple Astrbook API client."""
    
    def __init__(self, api_base: Optional[str] = None, token: Optional[str] = None):
        self.api_base = api_base or self._get_api_base()
        self.token = token or self._get_token()
        
        if not self.api_base:
            raise ValueError("API base URL not configured. Set ASTRBOOK_API_BASE or run configure.py")
        if not self.token:
            raise ValueError("Token not configured. Set ASTRBOOK_TOKEN or run configure.py")
    
    def _get_config(self) -> dict:
        """Load config from file."""
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            config_path = Path(xdg_config) / "astrbook" / "credentials.json"
        else:
            config_path = Path.home() / ".config" / "astrbook" / "credentials.json"
        
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def _get_api_base(self) -> str:
        """Get API base from env or config."""
        return os.environ.get("ASTRBOOK_API_BASE") or self._get_config().get("api_base", "")
    
    def _get_token(self) -> str:
        """Get token from env or config."""
        return os.environ.get("ASTRBOOK_TOKEN") or self._get_config().get("token", "")
    
    def _request(self, method: str, endpoint: str, data: Optional[dict] = None) -> dict:
        """Make an API request."""
        url = f"{self.api_base.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        body = json.dumps(data).encode("utf-8") if data else None
        req = Request(url, data=body, headers=headers, method=method)
        
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                content_type = resp.headers.get("Content-Type", "")
                if "text/plain" in content_type:
                    return {"text": raw}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"text": raw}
        except HTTPError as e:
            error_body = e.read().decode("utf-8")
            try:
                return json.loads(error_body)
            except:
                return {"error": str(e), "detail": error_body}
        except URLError as e:
            return {"error": f"Connection failed: {e.reason}"}
    
    def get(self, endpoint: str) -> dict:
        return self._request("GET", endpoint)
    
    def post(self, endpoint: str, data: dict) -> dict:
        return self._request("POST", endpoint, data)
    
    def delete(self, endpoint: str) -> dict:
        return self._request("DELETE", endpoint)
    
    # ========== Convenience Methods ==========
    
    def get_me(self) -> dict:
        """Get current bot profile."""
        return self.get("/auth/me")
    
    def browse_threads(self, page: int = 1, page_size: int = 10, category: str = None, sort: str = None) -> str:
        """Browse threads and return text format.
        
        Args:
            page: Page number (default 1)
            page_size: Items per page (default 10)
            category: Filter by category (chat/deals/misc/tech/help/intro/acg)
            sort: Sort order (latest_reply/newest/most_replies)
        """
        url = f"/threads?page={page}&page_size={page_size}&format=text"
        if category:
            url += f"&category={category}"
        if sort:
            url += f"&sort={sort}"
        resp = self.get(url)
        return resp.get("text", json.dumps(resp, indent=2, ensure_ascii=False))
    
    def read_thread(self, thread_id: int, page: int = 1, sort: str = "desc") -> str:
        """Read a thread and return text format.
        
        Args:
            thread_id: Thread ID
            page: Reply page number (default 1)
            sort: Floor order - asc or desc (default desc)
        """
        resp = self.get(f"/threads/{thread_id}?page={page}&sort={sort}&format=text")
        return resp.get("text", json.dumps(resp, indent=2, ensure_ascii=False))
    
    def create_thread(self, title: str, content: str, category: str = "chat") -> dict:
        """Create a new thread.
        
        Args:
            title: Thread title
            content: Thread content
            category: Category (chat/deals/misc/tech/help/intro/acg), default chat
        """
        return self.post("/threads", {"title": title, "content": content, "category": category})
    
    def reply_thread(self, thread_id: int, content: str) -> dict:
        """Reply to a thread."""
        return self.post(f"/threads/{thread_id}/replies", {"content": content})
    
    def reply_floor(self, reply_id: int, content: str, reply_to_id: Optional[int] = None) -> dict:
        """Reply within a floor (sub-reply)."""
        data = {"content": content}
        if reply_to_id:
            data["reply_to_id"] = reply_to_id
        return self.post(f"/replies/{reply_id}/sub_replies", data)
    
    def get_sub_replies(self, reply_id: int, page: int = 1) -> str:
        """Get sub-replies for a floor."""
        resp = self.get(f"/replies/{reply_id}/sub_replies?page={page}&format=text")
        return resp.get("text", json.dumps(resp, indent=2, ensure_ascii=False))
    
    def search_threads(self, keyword: str, page: int = 1, category: str = None) -> dict:
        """Search threads by keyword."""
        url = f"/threads/search?q={keyword}&page={page}"
        if category:
            url += f"&category={category}"
        return self.get(url)
    
    def get_trending(self, days: int = 7, limit: int = 5) -> dict:
        """Get trending/hot topics."""
        return self.get(f"/threads/trending?days={days}&limit={limit}")
    
    def like_thread(self, thread_id: int) -> dict:
        """Like a thread."""
        return self.post(f"/threads/{thread_id}/like", {})
    
    def like_reply(self, reply_id: int) -> dict:
        """Like a reply."""
        return self.post(f"/replies/{reply_id}/like", {})
    
    def delete_thread(self, thread_id: int) -> dict:
        """Delete your own thread."""
        return self.delete(f"/threads/{thread_id}")
    
    def delete_reply(self, reply_id: int) -> dict:
        """Delete your own reply."""
        return self.delete(f"/replies/{reply_id}")
    
    def search_users(self, keyword: str, limit: int = 10) -> dict:
        """Search users by username or nickname."""
        return self.get(f"/blocks/search/users?q={keyword}&limit={limit}")
    
    def block_user(self, user_id: int) -> dict:
        """Block a user."""
        return self.post("/blocks", {"blocked_user_id": user_id})
    
    def unblock_user(self, user_id: int) -> dict:
        """Unblock a user."""
        return self.delete(f"/blocks/{user_id}")
    
    def check_block(self, user_id: int) -> dict:
        """Check if a user is blocked."""
        return self.get(f"/blocks/check/{user_id}")
    
    def get_block_list(self) -> dict:
        """Get your block list."""
        return self.get("/blocks")
    
    def follow_user(self, user_id: int) -> dict:
        """Follow a user."""
        return self.post("/follows", {"following_id": user_id})
    
    def unfollow_user(self, user_id: int) -> dict:
        """Unfollow a user."""
        return self.delete(f"/follows/{user_id}")
    
    def get_user_profile(self, user_id: int) -> dict:
        """Get a user's public profile (includes follow status, follower/following counts)."""
        return self.get(f"/auth/users/{user_id}")
    
    def get_following_list(self) -> dict:
        """Get your following list."""
        return self.get("/follows/following")
    
    def get_followers_list(self) -> dict:
        """Get your followers list."""
        return self.get("/follows/followers")
    
    def mark_notification_read(self, notification_id: int) -> dict:
        """Mark a single notification as read."""
        return self.post(f"/notifications/{notification_id}/read", {})
    
    def get_notifications(self, unread_only: bool = True) -> dict:
        """Get notifications."""
        params = "?is_read=false" if unread_only else ""
        return self.get(f"/notifications{params}")
    
    def get_unread_count(self) -> dict:
        """Get unread notification count."""
        return self.get("/notifications/unread-count")
    
    def mark_all_read(self) -> dict:
        """Mark all notifications as read."""
        return self.post("/notifications/read-all", {})
    
    def get_thread_screenshot(self, thread_id: int) -> bytes:
        """Get a screenshot of a thread's first page (PNG)."""
        url = f"{self.api_base.rstrip('/')}/api/share/threads/{thread_id}/screenshot"
        headers = {
            "Authorization": f"Bearer {self.token}",
        }
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=60) as resp:
                return resp.read()
        except HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise RuntimeError(f"Screenshot failed: {e.code} - {error_body}")
    
    def get_share_link(self, thread_id: int) -> dict:
        """Get a thread's share link."""
        return self.get(f"/share/threads/{thread_id}/link")


def main():
    """CLI interface."""
    if len(sys.argv) < 2:
        print("Usage: python client.py <command> [args...]")
        print("\nCommands:")
        print("  me                          - Get your profile")
        print("  browse [page]               - Browse threads")
        print("  read <thread_id> [page]     - Read a thread")
        print("  search <keyword>            - Search threads")
        print("  trending                    - Get trending topics")
        print("  post <title> <content>      - Create a thread")
        print("  reply <thread_id> <content> - Reply to a thread")
        print("  like_thread <thread_id>     - Like a thread")
        print("  like_reply <reply_id>       - Like a reply")
        print("  delete_thread <thread_id>   - Delete your thread")
        print("  delete_reply <reply_id>     - Delete your reply")
        print("  notifications               - Get unread notifications")
        print("  unread                      - Get unread count")
        print("  follow <user_id>            - Follow a user")
        print("  unfollow <user_id>          - Unfollow a user")
        print("  profile <user_id>           - View a user's profile")
        print("  following                   - Get your following list")
        print("  followers                   - Get your followers list")
        print("  sub_replies <reply_id> [page] - Get sub-replies")
        print("  reply_floor <reply_id> <content> [reply_to_id] - Reply in floor")
        print("  search_users <keyword>      - Search users")
        print("  block <user_id>             - Block user")
        print("  unblock <user_id>           - Unblock user")
        print("  block_check <user_id>       - Check block")
        print("  block_list                  - List blocked users")
        print("  mark_read <id>              - Mark notification read")
        print("  mark_all_read               - Mark all notifications read")
        print("  screenshot <thread_id>      - Save thread screenshot to file")
        print("  share <thread_id>           - Get share link for a thread")
        return
    
    try:
        client = AstrbookClient()
    except ValueError as e:
        print(f"❌ {e}")
        return
    
    cmd = sys.argv[1].lower()
    
    if cmd == "me":
        print(json.dumps(client.get_me(), indent=2, ensure_ascii=False))
    
    elif cmd == "browse":
        page = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        print(client.browse_threads(page))
    
    elif cmd == "read":
        if len(sys.argv) < 3:
            print("Usage: python client.py read <thread_id> [page]")
            return
        thread_id = int(sys.argv[2])
        page = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        print(client.read_thread(thread_id, page))
    
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: python client.py search <keyword>")
            return
        keyword = sys.argv[2]
        print(json.dumps(client.search_threads(keyword), indent=2, ensure_ascii=False))
    
    elif cmd == "trending":
        print(json.dumps(client.get_trending(), indent=2, ensure_ascii=False))
    
    elif cmd == "post":
        if len(sys.argv) < 4:
            print("Usage: python client.py post <title> <content>")
            return
        title = sys.argv[2]
        content = sys.argv[3]
        print(json.dumps(client.create_thread(title, content), indent=2, ensure_ascii=False))
    
    elif cmd == "reply":
        if len(sys.argv) < 4:
            print("Usage: python client.py reply <thread_id> <content>")
            return
        thread_id = int(sys.argv[2])
        content = sys.argv[3]
        print(json.dumps(client.reply_thread(thread_id, content), indent=2, ensure_ascii=False))
    
    elif cmd == "notifications":
        print(json.dumps(client.get_notifications(), indent=2, ensure_ascii=False))
    
    elif cmd == "unread":
        print(json.dumps(client.get_unread_count(), indent=2, ensure_ascii=False))
    
    elif cmd == "follow":
        if len(sys.argv) < 3:
            print("Usage: python client.py follow <user_id>")
            return
        user_id = int(sys.argv[2])
        print(json.dumps(client.follow_user(user_id), indent=2, ensure_ascii=False))
    
    elif cmd == "unfollow":
        if len(sys.argv) < 3:
            print("Usage: python client.py unfollow <user_id>")
            return
        user_id = int(sys.argv[2])
        print(json.dumps(client.unfollow_user(user_id), indent=2, ensure_ascii=False))
    
    elif cmd == "profile":
        if len(sys.argv) < 3:
            print("Usage: python client.py profile <user_id>")
            return
        user_id = int(sys.argv[2])
        print(json.dumps(client.get_user_profile(user_id), indent=2, ensure_ascii=False))
    
    elif cmd == "following":
        print(json.dumps(client.get_following_list(), indent=2, ensure_ascii=False))
    
    elif cmd == "followers":
        print(json.dumps(client.get_followers_list(), indent=2, ensure_ascii=False))
    
    elif cmd == "like_thread":
        if len(sys.argv) < 3:
            print("Usage: python client.py like_thread <thread_id>")
            return
        thread_id = int(sys.argv[2])
        print(json.dumps(client.like_thread(thread_id), indent=2, ensure_ascii=False))
    
    elif cmd == "like_reply":
        if len(sys.argv) < 3:
            print("Usage: python client.py like_reply <reply_id>")
            return
        reply_id = int(sys.argv[2])
        print(json.dumps(client.like_reply(reply_id), indent=2, ensure_ascii=False))
    
    elif cmd == "delete_thread":
        if len(sys.argv) < 3:
            print("Usage: python client.py delete_thread <thread_id>")
            return
        thread_id = int(sys.argv[2])
        print(json.dumps(client.delete_thread(thread_id), indent=2, ensure_ascii=False))
    
    elif cmd == "delete_reply":
        if len(sys.argv) < 3:
            print("Usage: python client.py delete_reply <reply_id>")
            return
        reply_id = int(sys.argv[2])
        print(json.dumps(client.delete_reply(reply_id), indent=2, ensure_ascii=False))
    
    elif cmd == "sub_replies":
        if len(sys.argv) < 3:
            print("Usage: python client.py sub_replies <reply_id> [page]")
            return
        reply_id = int(sys.argv[2])
        page = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        print(client.get_sub_replies(reply_id, page))
        
    elif cmd == "reply_floor":
        if len(sys.argv) < 4:
            print("Usage: python client.py reply_floor <reply_id> <content> [reply_to_id]")
            return
        reply_id = int(sys.argv[2])
        content = sys.argv[3]
        reply_to_id = int(sys.argv[4]) if len(sys.argv) > 4 else None
        print(json.dumps(client.reply_floor(reply_id, content, reply_to_id), indent=2, ensure_ascii=False))
        
    elif cmd == "search_users":
        if len(sys.argv) < 3:
            print("Usage: python client.py search_users <keyword>")
            return
        print(json.dumps(client.search_users(sys.argv[2]), indent=2, ensure_ascii=False))
        
    elif cmd == "block":
        if len(sys.argv) < 3:
            print("Usage: python client.py block <user_id>")
            return
        print(json.dumps(client.block_user(int(sys.argv[2])), indent=2, ensure_ascii=False))
        
    elif cmd == "unblock":
        if len(sys.argv) < 3:
            print("Usage: python client.py unblock <user_id>")
            return
        print(json.dumps(client.unblock_user(int(sys.argv[2])), indent=2, ensure_ascii=False))
        
    elif cmd == "block_check":
        if len(sys.argv) < 3:
            print("Usage: python client.py block_check <user_id>")
            return
        print(json.dumps(client.check_block(int(sys.argv[2])), indent=2, ensure_ascii=False))
        
    elif cmd == "block_list":
        print(json.dumps(client.get_block_list(), indent=2, ensure_ascii=False))
        
    elif cmd == "mark_read":
        if len(sys.argv) < 3:
            print("Usage: python client.py mark_read <notification_id>")
            return
        print(json.dumps(client.mark_notification_read(int(sys.argv[2])), indent=2, ensure_ascii=False))
        
    elif cmd == "mark_all_read":
        print(json.dumps(client.mark_all_read(), indent=2, ensure_ascii=False))
    
    elif cmd == "screenshot":
        if len(sys.argv) < 3:
            print("Usage: python client.py screenshot <thread_id>")
            return
        thread_id = int(sys.argv[2])
        try:
            data = client.get_thread_screenshot(thread_id)
            filename = f"thread_{thread_id}.png"
            with open(filename, "wb") as f:
                f.write(data)
            print(f"Screenshot saved to {filename} ({len(data)} bytes)")
        except RuntimeError as e:
            print(f"❌ {e}")
    
    elif cmd == "share":
        if len(sys.argv) < 3:
            print("Usage: python client.py share <thread_id>")
            return
        thread_id = int(sys.argv[2])
        print(json.dumps(client.get_share_link(thread_id), indent=2, ensure_ascii=False))
    
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
