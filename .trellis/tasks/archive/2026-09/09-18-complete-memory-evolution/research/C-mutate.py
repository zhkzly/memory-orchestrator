"""One exact mutation, invoked only by the official mutation-license tool."""
import json
from pathlib import Path
import sys

rows=json.loads(Path(__file__).with_name('C-mutations.json').read_text())
row=next(item for item in rows if item['name']==sys.argv[1])
path=Path(row['target']);before=path.read_text()
assert before.count(row['old'])==1, (row['name'],before.count(row['old']))
path.write_text(before.replace(row['old'],row['replacement'],1))
