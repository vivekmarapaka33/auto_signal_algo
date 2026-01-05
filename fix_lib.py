import os
import re

def fix_file(path):
    print(f"Fixing {path}")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace | with , inside type hints (simplified)
        # This is a bit risky but we're targeting a specific library's style
        # Original: ssid: str, url: str | None = None, config: Config | dict | str = None
        # Target: ssid: str, url: Union[str, None] = None...
        
        # A safer way for this specific library is to just replace ' | ' with ', ' 
        # and then wrap the whole thing in Union[...] if we find a comma? 
        # Actually, let's just use from __future__ import annotations AND replace | with ,
        # because Python 3.9 still doesn't like | in type evaluation.
        
        if ' | ' in content:
            content = content.replace(' | ', ', ')
            # We need to wrap it in Union[...] for it to be valid if we replace | with ,
            # But that's hard with regex. 
            # Alternative: replace ' | ' with ' or '? No.
            # Best: replace ' | ' with '' (just take the first type) or use strings.
            
            # Let's try to replace 'Type1 | Type2' with 'Union[Type1, Type2]'
            content = re.sub(r'([a-zA-Z0-9_\[\]]+) \| ([a-zA-Z0-9_\[\]]+) \| ([a-zA-Z0-9_\[\]]+)', r'Union[\1, \2, \3]', content)
            content = re.sub(r'([a-zA-Z0-9_\[\]]+) \| ([a-zA-Z0-9_\[\]]+)', r'Union[\1, \2]', content)
            
            if 'from typing import' in content:
                if 'Union' not in content:
                    content = content.replace('from typing import ', 'from typing import Union, ')
            else:
                content = 'from typing import Union, Optional, Any\n' + content
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Error fixing {path}: {e}")

base_dir = r'C:\Users\surya_prakash\AppData\Roaming\Python\Python39\site-packages\BinaryOptionsToolsV2'
if os.path.exists(base_dir):
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.endswith('.py'):
                fix_file(os.path.join(root, f))
else:
    print(f"Directory not found: {base_dir}")
