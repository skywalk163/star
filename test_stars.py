import urllib.request, json

r = urllib.request.urlopen('http://localhost:8767/api/stars/')
d = json.loads(r.read())
stars = d if isinstance(d, list) else d.get('stars', [])
print(f'发现 {len(stars)} 个星体')
for s in stars:
    print(f'  {s}')
