Output docs/assets/demo-prewrite-guard-vhs.gif
Set Shell "bash"
Set FontSize 15
Set Width 1200
Set Height 640
Set Padding 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms

Type "# 1. Attempt reading protected .env credential via Claude Code hook"
Enter
Sleep 400ms
Type "echo '{\"tool_name\":\"read_file\",\"tool_input\":{\"path\":\".env\"}}' | netark-mcp hook --hook-mode claude --cwd ."
Enter
Sleep 1800ms

Type "# 2. Self-healed check via environment variable"
Enter
Sleep 400ms
Type "echo '{\"tool_name\":\"write_file\",\"tool_input\":{\"path\":\"src/app.py\",\"content\":\"import os\\nkey = os.environ.get(\\\"API_KEY\\\")\\n\"}}' | netark-mcp hook --hook-mode claude --cwd ."
Enter
Sleep 2500ms
