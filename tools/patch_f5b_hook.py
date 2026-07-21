#!/usr/bin/env python3
"""Fix event_trigger.py INSERT statement - remove nonexistent columns."""
from pathlib import Path
p = Path("game/app/mainline/event_trigger.py")
src = p.read_text(encoding="utf-8")

old = '_INSERT = _sqltext("INSERT INTO units (player_id,unit_type,name,level,hp,max_hp,mp,mov,atk,def_,matk,mdef,x,y,attack_range,min_attack_range,skills,color,has_acted,has_moved) VALUES (:p,:t,:n,:lv,20,20,3,3,10,5,0,0,:x,:y,1,1,\'[]\',:c,0,0)")'
new = '_INSERT = _sqltext("INSERT INTO units (player_id,unit_type,name,level,hp,max_hp,mp,mov,atk,def_,matk,mdef,x,y,skills,has_acted,has_moved) VALUES (:p,:t,:n,:lv,20,20,3,3,10,5,0,0,:x,:y,\'[]\',0,0)")'

if old not in src:
    print("old not found, trying to find _INSERT")
    import re
    for m in re.finditer(r'_INSERT.*?\)', src, re.DOTALL):
        print(m.group()[:200])
    raise SystemExit(1)

src = src.replace(old, new, 1)
# Remove the color param usage
old2 = '"c": str(spec.get("color", "blue")),\n                '
src = src.replace(old2, '')
p.write_text(src, encoding="utf-8")
print("patched")
