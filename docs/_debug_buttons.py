import re

with open(r'D:/Python/BattleBlitz/battleblitz/godot-client/scenes/main.tscn', encoding='utf-8') as f:
    tscn = f.read()
with open(r'D:/Python/BattleBlitz/battleblitz/godot-client/scripts/main.gd', encoding='utf-8') as f:
    src = f.read()

def to_snake(name):
    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
    snake = re.sub(r'(?<=[a-z])_l_', 'l_', snake)
    return snake

# 抓 button: groups 1=name, 2=parent, 3=body
btn_pat = r'\[node name="([^"]+)" type="Button" parent="([^"]+)"\]\s*\n((?:[^\n]*\n){0,10})'
buttons = [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(btn_pat, tscn)]

# handler map
handler_map = {}
pat = r'([a-zA-Z_][a-zA-Z0-9_]*)\.(pressed|toggled)\.connect\(([a-zA-Z_][a-zA-Z0-9_]*)(?:\.bind\(([^)]*)\))?\)'
for m in re.finditer(pat, src):
    handler_map.setdefault(m.group(1).lower(), []).append(m.group(3))

onready_vars = re.findall(r'onready var ([a-zA-Z_][a-zA-Z0-9_]*):', src)

print("--- DEAD 按钮 ---")
for name, parent, body in buttons:
    key = to_snake(name)
    if key not in handler_map:
        var_exists = key in onready_vars
        print(f'  {parent}/{name}  key={key}  has_var={var_exists}')

print()
print(f'total buttons={len(buttons)}  live={len(buttons) - sum(1 for n,p,b in buttons if to_snake(n) not in handler_map)}')
