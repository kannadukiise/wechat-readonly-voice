"""Single guarded database operation. Never imports upstream __init__/GUI."""
import sys, pathlib, os, types, logging, hashlib, importlib.util, json, contextlib, tempfile, shutil
ROOT=pathlib.Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'lib'))
from policy import validate, read_messages
from guard import Guard

DIGEST='9d4eba69e868dea8000d8acdbaed723149cf8732c52e097f23fb3b07fa5ddc55'

def load_reader():
    src=ROOT/'vendor'/'db.py'
    if hashlib.sha256(src.read_bytes()).hexdigest()!=DIGEST:raise RuntimeError('source digest mismatch')
    pkg=types.ModuleType('wechatauto');pkg.__path__=[]
    sys.modules['wechatauto']=pkg
    logger=types.ModuleType('wechatauto.logger')
    logger.wxlog=logging.getLogger('wechat-readonly')
    logger.wxlog.handlers=[logging.NullHandler()];logger.wxlog.propagate=False
    sys.modules['wechatauto.logger']=logger
    spec=importlib.util.spec_from_file_location('reviewed_db',src)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.WeChatDB._save_keys=lambda self:None
    module.WeChatDB._stable_key_dirs=lambda self:[]
    module.WeChatDB._load_key_cache=lambda self,path:{}
    module.WeChatDB._try_other_accounts=lambda self:False
    module.WeChatDB._select_account_by_keys=lambda self,cands:False
    return module

def execute(tool,args,scratch,config):
    q=validate(tool,args)
    module=load_reader()
    account_root=pathlib.Path(config['db_dir']).resolve()
    account=config['account']
    if pathlib.Path(account).name!=account or '/' in account or '\\' in account:
        raise ValueError('invalid pinned account')
    if not (account_root/account/'db_storage').is_dir():raise RuntimeError('account unavailable')
    pids=object.__new__(module.WeChatDB)._find_weixin_pids()
    if not pids:raise RuntimeError('wechat not running or inaccessible')
    if tool=='wechat_status':
        return {'ready':True,'read_only':True,'network_disabled':True,'keys_persisted':False,
                'account_pinned':True,'timezone':'Asia/Ulaanbaatar (+08:00)',
                'note':'Checks files/process only; run a query to verify database access.'}
    db=module.WeChatDB(db_dir=str(account_root),account=account,workdir=str(scratch))
    # Prevent implicit future account/workdir changes from being silently accepted.
    if db.account!=account or pathlib.Path(db.workdir).resolve()!=scratch:raise RuntimeError('scope changed')
    if tool=='query_messages':
        from local_asr import AutoVoiceTranscriber
        result=read_messages(db,q,transcribe=AutoVoiceTranscriber(db,q['chat_id'],ROOT))
    elif tool=='find_chats':
        matches=db.search_contact(q['keyword'])[:q['limit']]
        result={'chats':[{'chat_id':r['username'],'name':(r['remark'] or r['nick_name'] or r['username'])[:200],
                          'is_group':r['username'].endswith('@chatroom')} for r in matches],
                'note':'Upstream contact search examines at most 50 matches; use a specific keyword.'}
    else:
        sessions=db.get_sessions(limit=q['limit'])
        result={'chats':[{'chat_id':r['username'],'name':db.get_nickname(r['username'])[:200],
                          'last_time':r['last_time'],'is_group':r['username'].endswith('@chatroom')} for r in sessions]}
    if any('GUI' in k or k.startswith('wechatauto.') and k!='wechatauto.logger' for k in sys.modules):
        raise RuntimeError('unexpected GUI import')
    # Detect upstream fallback to older main-DB snapshots when WAL merging failed.
    stale=any(p.read_text().strip().split(',')[-1]=='-1' for p in scratch.glob('*.stamp'))
    result['snapshot_may_lag']=stale
    return result

def main():
    scratch=pathlib.Path(sys.argv[1]).resolve()
    expected=ROOT/'scratch'
    if scratch.parent!=expected or not scratch.name.startswith('query-') or not scratch.is_dir():
        raise SystemExit(2)
    sys.addaudithook(Guard(scratch).audit)
    tempfile.tempdir=str(scratch)
    class Sink:
        def write(self,t):return len(t)
        def flush(self):pass
    try:
        request=json.loads(sys.stdin.buffer.readline(16385))
        config=json.loads((ROOT/'private_config.json').read_text(encoding='utf-8'))
        with contextlib.redirect_stdout(Sink()),contextlib.redirect_stderr(Sink()):
            result=execute(request['tool'],request['arguments'],scratch,config)
        reply={'ok':True,'result':result}
    except Exception as exc:
        reply={'ok':False,'error':type(exc).__name__,
               'message':'Read failed; keep WeChat logged in, check permissions and pinned account. No data returned.'}
    try:
        shutil.rmtree(scratch)
    except Exception:
        reply={'ok':False,'error':'cleanup_failed','message':'Temporary copy cleanup failed; no records returned.'}
    sys.stdout.buffer.write(json.dumps(reply,ensure_ascii=False).encode('utf-8'));sys.stdout.buffer.flush()

if __name__=='__main__':main()
