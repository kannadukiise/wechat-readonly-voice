import pathlib
import sqlite3
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from local_asr import read_local_voice, MAX_AUDIO_BYTES, AutoVoiceTranscriber
from policy import read_messages, validate
import test_voice_transcript as voice_tests


class LocalAudioTests(unittest.TestCase):
    def fixture(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.execute('CREATE TABLE Name2Id (user_name TEXT)')
        conn.executemany('INSERT INTO Name2Id VALUES (?)',[('wanted',),('other',)])
        conn.execute('CREATE TABLE VoiceInfo (chat_name_id, svr_id, voice_data, create_time)')
        conn.executemany('INSERT INTO VoiceInfo VALUES (?,?,?,?)',[(2,123,b'wrong-chat',200),(1,123,b'right-chat',100)])
        class NonClosing:
            def execute(self,*args):return conn.execute(*args)
            def close(self):pass
        class DB:
            _db_files=[('media','media_0.db',None)]
            def _open(self,rel):return NonClosing()
        self.addCleanup(conn.close)
        return DB(),conn

    def test_chat_and_server_must_both_match(self):
        db,_=self.fixture()
        self.assertEqual(read_local_voice(db,'wanted',123),(b'right-chat','available'))
        self.assertEqual(read_local_voice(db,'absent',123),(None,'audio_not_local'))
        self.assertEqual(read_local_voice(db,'wanted',None),(None,'audio_not_local'))

    def test_large_audio_not_returned(self):
        db,conn=self.fixture()
        conn.execute('UPDATE VoiceInfo SET voice_data=zeroblob(?) WHERE chat_name_id=1',(MAX_AUDIO_BYTES+1,))
        self.assertEqual(read_local_voice(db,'wanted',123),(None,'audio_too_large'))

    def test_missing_audio_never_initializes_model(self):
        db,_=self.fixture()
        asr=AutoVoiceTranscriber(db,'absent',pathlib.Path(__file__).parent)
        result=asr({'server_id':123})
        self.assertEqual(result[0],'')
        self.assertEqual(result[1]['transcript_status'],'audio_not_local')
        self.assertIsNone(asr.model)


class BudgetTests(unittest.TestCase):
    def test_budget_cursor_preserves_unprocessed_voices_in_filtered_pages(self):
        fixture=voice_tests.VoiceTests();db,conn,table=fixture.fixture()
        self.addCleanup(fixture.doCleanups)
        conn.execute(f'UPDATE {table} SET local_type=34,packed_info_data=?',(voice_tests.packed('',0),))
        class ASR:
            def __init__(self):self.count=0
            @property
            def exhausted(self):return self.count>=1
            def __call__(self,row):
                self.count+=1
                return '自动文字',{'transcript_source':'local_whisper','transcript_status':'available'}
        q=dict(chat_id='voice-test',start=100,end=104,limit=100,after=None,keyword='不存在')
        scanned=0;pages=0
        while True:
            page=read_messages(db,q,transcribe=ASR())
            self.assertEqual(page['messages'],[])
            self.assertEqual(page['scanned'],1)
            scanned+=page['scanned'];pages+=1
            if not page['has_more']:break
            q=validate('query_messages',dict(chat_id='voice-test',keyword='不存在',cursor=page['next_cursor'],limit=100))
            self.assertLess(pages,4)
        self.assertEqual((scanned,pages),(3,3))


if __name__=='__main__':unittest.main()
