def two_sum(a,t):
 d={}
 for i,x in enumerate(a):
  if t-x in d: return [d[t-x],i]
  d[x]=i
 return []
