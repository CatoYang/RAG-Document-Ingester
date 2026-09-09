import sys
import json
import re

def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"decision": "allow"}))
        return

    tool_call = input_data.get("toolCall", {})
    args = tool_call.get("args", {})
    
    content = ""
    if tool_call.get("name") == "write_to_file":
        content = args.get("CodeContent", "")
    elif tool_call.get("name") == "replace_file_content":
        content = args.get("ReplacementContent", "")
        
    if not content:
        print(json.dumps({"decision": "allow"}))
        return

    # Check for synchronous open() usage inside async functions
    if "async def" in content and re.search(r'\bopen\(', content) and "aiofiles" not in content:
        print(json.dumps({
            "decision": "deny",
            "reason": "Synchronous file reads (e.g., open()) are not allowed. Please use asynchronous I/O like aiofiles."
        }))
        return

    print(json.dumps({"decision": "allow"}))

if __name__ == "__main__":
    main()
