f = open("app/routes/packing_slips.py", "r")
ln = f.readlines()
f.close()
v = ln[140].strip()[:-4]
print("VALUES:", v)
print("count:", v.count("?"))
