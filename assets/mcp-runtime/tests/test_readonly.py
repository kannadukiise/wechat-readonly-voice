import sys, pathlib, unittest, sqlite3, tempfile, hashlib, asyncio
from datetime import datetime, timezone, timedelta
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
tempfile.tempdir = str(pathlib.Path(__file__).resolve().parents[1])
from policy import validate, read_messages
from guard import Guard

class PolicyTests(unittest.TestCase):
    def test_rejects_unknown_or_write_tool(self):
        for tool in ('send_message', 'export', 'sql'):
            with self.assertRaises(ValueError): validate(tool, {})

    def test_rejects_bad_arguments(self):
        for args in ({'chat_id':'x', 'limit':101}, {'chat_id':'x','offset':-1},
                     {'chat_id':'x','start':'bad'}, {'chat_id':'x','start':'2026-10-17','end':'2026-10-16'},
                     {'chat_id':'x','path':'C:/secret'}, {'chat_id':'x','limit':True}):
            with self.assertRaises(ValueError): validate('query_messages', args)

    def test_local_date_and_exclusive_end(self):
        q=validate('query_messages', {'chat_id':'x','start':'2026-10-16','end':'2026-10-17'})
        self.assertEqual(q['end']-q['start'],86400)
        self.assertEqual(datetime.fromtimestamp(q['start'],timezone.utc).hour,16)

    def fixture(self):
        table='Msg_'+hashlib.md5(b"x' OR 1=1--").hexdigest()
        conns=[]
        for shard in range(2):
            c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
            c.execute(f'CREATE TABLE {table} (local_id, local_type, real_sender_id, create_time, message_content, compress_content, sort_seq)')
            for i in range(3):
                c.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?,?,?)',(i,1,1,100+i,'needle' if i==1 else 'other',None,100+i))
            conns.append((c,table))
        class DB:
            def _run_msg_query(self,user,build): return build(conns)
            def _shard_label(self,c): return str(conns.index(next(t for t in conns if t[0] is c)))
            def _shard_maps(self,t): return {}
            def _msg_row_to_dict(self,r,m): return dict(r, content=r['message_content'], type='text', sender_username='sender')
        self.addCleanup(lambda:[c.close() for c,t in conns])
        return DB()

    def test_shard_pagination_and_literal_chat_id(self):
        db=self.fixture()
        q={'chat_id':"x' OR 1=1--",'start':100,'end':103,'limit':2,'after':None,'keyword':''}
        page=read_messages(db,q)
        self.assertEqual(len(page['messages']),2)
        self.assertEqual({m['create_time'] for m in page['messages']},{102})
        import json,base64
        q['after']=json.loads(base64.urlsafe_b64decode(page['next_cursor']))['after']
        page2=read_messages(db,q)
        self.assertEqual({m['create_time'] for m in page2['messages']},{101})
        q['keyword']='needle'; q['after']=None
        found=read_messages(db,q)
        self.assertEqual(len(found['messages']),2)
        self.assertEqual({m['create_time'] for m in found['messages']},{101})

    def test_half_open_date_range(self):
        q={'chat_id':"x' OR 1=1--",'start':101,'end':102,'limit':100,'after':None,'keyword':''}
        self.assertEqual(len(read_messages(self.fixture(),q)['messages']),2)

    def test_cursor_pins_range_and_rejects_different_chat(self):
        page=read_messages(self.fixture(),dict(chat_id="x' OR 1=1--",start=100,end=103,limit=1,after=None,keyword=''))
        q=validate('query_messages',dict(chat_id="x' OR 1=1--",cursor=page['next_cursor']))
        self.assertEqual((q['start'],q['end']),(100,103))
        with self.assertRaises(ValueError):validate('query_messages',dict(chat_id='other',cursor=page['next_cursor']))

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import server
        self.server=server
        self.tmp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.tmp.name).resolve()
        self.old=(server.ROOT,server.SCRATCH,server.TIMEOUT,server.LOCK)
        server.ROOT=self.root;server.SCRATCH=self.root/'scratch';server.TIMEOUT=.3;server.LOCK=asyncio.Lock()
        (self.root/'worker.py').write_text('import sys,pathlib,time\np=pathlib.Path(sys.argv[1]);(p/"copy.db").write_text("synthetic")\ntime.sleep(30)\n')
    async def asyncTearDown(self):
        s=self.server;s.ROOT,s.SCRATCH,s.TIMEOUT,s.LOCK=self.old
        self.tmp.cleanup()
    async def test_timeout_cleans_scratch(self):
        result=await self.server.run_worker('wechat_status',{})
        self.assertEqual(result['error'],'query_timeout')
        self.assertFalse(list(self.server.SCRATCH.glob('query-*')))
    async def test_failed_worker_cleans_scratch(self):
        (self.root/'worker.py').write_text('import sys,pathlib,time\np=pathlib.Path(sys.argv[1]);(p/"copy.db").write_text("synthetic")\ntime.sleep(.05)\nsys.exit(1)\n')
        result=await self.server.run_worker('wechat_status',{})
        self.assertEqual(result['error'],'worker_failed')
        self.assertFalse(list(self.server.SCRATCH.glob('query-*')))
    async def test_sweep_preserves_active_server(self):
        import os
        s=self.server;s.SCRATCH.mkdir()
        active=s.SCRATCH/f'query-{os.getpid()}-active';active.mkdir()
        dead=s.SCRATCH/'query-4294967294-dead';dead.mkdir()
        s.sweep_stale()
        self.assertTrue(active.exists());self.assertFalse(dead.exists())
    async def test_cancel_cleans_and_queued_cancel_never_launches(self):
        first=asyncio.create_task(self.server.run_worker('wechat_status',{}))
        await asyncio.sleep(.05)
        queued=asyncio.create_task(self.server.run_worker('wechat_status',{}))
        await asyncio.sleep(.01);queued.cancel()
        with self.assertRaises(asyncio.CancelledError):await queued
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):await first
        self.assertFalse(list(self.server.SCRATCH.glob('query-*')))

class GuardTests(unittest.TestCase):
    def test_no_network_or_process_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=Guard(pathlib.Path(tmp))
            for event,args in [('socket.connect',(None,('example.com',443))),('ctypes.dlsym',(None,'WriteProcessMemory')),('subprocess.Popen',('cmd','cmd /c echo bad',None,None))]:
                with self.assertRaises(PermissionError):g.audit(event,args)

    def test_only_scratch_writes_and_readonly_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=Guard(pathlib.Path(tmp))
            g.audit('open',(str(pathlib.Path(tmp)/'copy.db'),'wb',0))
            with self.assertRaises(PermissionError):g.audit('open',(str(pathlib.Path(tmp).parent/'original.db'),'wb',0))
            with self.assertRaises(PermissionError):g.audit('sqlite3.connect',(str(pathlib.Path(tmp)/'copy.db'),))
            g.audit('sqlite3.connect',('file:'+str(pathlib.Path(tmp)/'copy.db')+'?mode=ro',))

if __name__=='__main__': unittest.main()
