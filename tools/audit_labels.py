"""Check disk vs JSONL state — show what's labeled, what's deleted, what's new."""
import os
import json
from glob import glob

ON_DISK = set()
for ext in ("*.png", "*.webp", "*.jpg", "*.jpeg"):
    for p in glob("docs/路线/参考调研/battle-map-references/images/**/" + ext, recursive=True):
        ON_DISK.add(p.replace("\\", "/"))

IN_JSONL = set()
JSONL_PATH = "docs/路线/参考调研/battle-map-references/map_region_labels.jsonl"
if os.path.exists(JSONL_PATH):
    with open(JSONL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            IN_JSONL.add(rec["path"])

DELETED = IN_JSONL - ON_DISK
ALREADY = IN_JSONL & ON_DISK
NEW = ON_DISK - IN_JSONL

print(f"当前 disk 上: {len(ON_DISK)} 张")
print(f"JSONL 已标:   {len(IN_JSONL)} 张")
print(f"  仍存在:     {len(ALREADY)} 张")
print(f"  已删:       {len(DELETED)} 张")
print(f"未标:         {len(NEW)} 张")
print()
if DELETED:
    print("--- 已删的图(JSONL 里还留着记录):")
    for p in sorted(DELETED):
        print(f"  {p.split('/')[-1]}")
print()
if NEW:
    print("--- 还没标的新图:")
    for p in sorted(NEW)[:15]:
        print(f"  {p.split('/')[-1]}")
    if len(NEW) > 15:
        print(f"  ...还有 {len(NEW) - 15} 张")
