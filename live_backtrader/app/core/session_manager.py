from typing import Optional
import os

class SessionManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SessionManager, cls).__new__(cls)
            cls._instance.ssid = ""
            cls._instance.load_ssid()
        return cls._instance

    def load_ssid(self):
        # Allow loading from a file or env
        if os.path.exists("ssid.txt"):
            try:
                with open("ssid.txt", "r") as f:
                    self.ssid = f.read().strip()
            except:
                pass
        
        if not self.ssid:
             self.ssid = os.getenv("POCKET_OPTION_SSID", "")

    def set_ssid(self, ssid: str):
        self.ssid = ssid.strip()
        # Save to file persistence
        try:
            with open("ssid.txt", "w") as f:
                f.write(self.ssid)
        except:
            pass

    def get_ssid(self) -> str:
        return self.ssid

session_manager = SessionManager()
