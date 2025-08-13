import os,yaml
_cfg=None
def get_config():
  global _cfg
  if _cfg is not None: return _cfg
  path=os.path.join(os.path.dirname(__file__),'..','config.yaml')
  try:
    _cfg=yaml.safe_load(open(path,'r',encoding='utf-8')) or {}
  except Exception:
    _cfg={}
  return _cfg
