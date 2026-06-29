import psutil

names = ['Trae.exe', 'trae.exe', 'TRAE SOLO CN.exe', 'TRAE SOLO CN', 'Trae CN', 'trae']
names_lower = [n.lower() for n in names]
count = 0
for proc in psutil.process_iter(['pid', 'name']):
    try:
        if proc.info['name'].lower() in names_lower:
            count += 1
            print(f"Found: {proc.info['name']} (PID {proc.info['pid']})")
    except:
        pass
print(f"Total: {count}")
