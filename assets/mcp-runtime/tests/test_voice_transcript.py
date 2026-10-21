import hashlib
import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from voice_transcript import local_voice_transcript, MAX_PACKED_BYTES
from policy import read_messages, validate


def varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def field(number, value):
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    if isinstance(value, str):
        value = value.encode('utf-8')
    return varint(number << 3 | 2) + varint(len(value)) + value


def packed(text, state=2):
    return field(1, 1342) + field(5, field(1, state) + field(2, text)) + field(11, 0)


class VoiceTests(unittest.TestCase):
    def test_reads_completed_unicode_only_at_known_path(self):
        self.assertEqual(local_voice_transcript(packed('客户是ACME，续航400公里。')), ('客户是ACME，续航400公里。', 'available'))
        self.assertEqual(local_voice_transcript(field(9, '无关文字')), ('', 'not_available'))
        self.assertEqual(local_voice_transcript(field(5, field(1, 2) + field(9, '无关文字'))), ('', 'unreadable'))

    def test_missing_empty_and_incomplete_never_fabricate_text(self):
        for data in (None, b'', '', packed('', 0), packed('尚未完成', 1), packed('   ')):
            self.assertEqual(local_voice_transcript(data), ('', 'not_available'))

    def test_malformed_oversized_invalid_utf8_and_ambiguous_are_safe(self):
        invalid = [b'\xff', b'\x00', b'\x2a\xff', b'\x2a\x7fabc', b'\x0b',
                   b'x' * (MAX_PACKED_BYTES + 1), packed(b'\xff'), packed('x\x00y'),
                   field(1, 1) * 129, b'\x08'+b'\xff'*9+b'\x02',
                   field(5, field(1, 2)+field(2, 'a')) * 2,
                   field(5, field(1, 2)+field(2, 'a')+field(2, 'b'))]
        for data in invalid:
            with self.subTest(data=data[:20]):
                self.assertEqual(local_voice_transcript(data), ('', 'unreadable'))

    def fixture(self):
        table = 'Msg_' + hashlib.md5(b'voice-test').hexdigest()
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute(f'CREATE TABLE {table} (local_id, local_type, real_sender_id, create_time, message_content, compress_content, sort_seq, packed_info_data)')
        for i, kind, blob in [(1, 34, packed('ACME电动卡车')), (2, 34, packed('', 0)), (3, 1, packed('不得替代普通消息'))]:
            conn.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?)', (i, kind, 1, 100+i, '<msg><voicemsg aeskey="DO_NOT_EXPOSE"/></msg>' if kind==34 else '普通正文', '', 100+i, blob))
        class DB:
            def _run_msg_query(self, user, build): return build([(conn, table)])
            def _shard_label(self, c): return 'test.db'
            def _shard_maps(self, tables): return {}
            def _msg_row_to_dict(self, row, maps): return {'content':row['message_content'], 'type':'语音' if row['local_type']==34 else '文本'}
        self.addCleanup(conn.close)
        return DB(), conn, table

    def test_query_keyword_searches_voice_and_keeps_original_ids(self):
        db, _, _ = self.fixture()
        q = dict(chat_id='voice-test', start=100, end=104, limit=100, after=None, keyword='acme')
        page = read_messages(db, q)
        self.assertFalse(page['has_more'])
        self.assertEqual(len(page['messages']), 1)
        msg = page['messages'][0]
        self.assertEqual(msg['id'], 'test.db:1')
        self.assertEqual(msg['content'], '[语音转文字] ACME电动卡车')
        self.assertEqual(msg['transcript_status'], 'available')
        self.assertEqual(msg['transcript_source'], 'wechat_local')

    def test_no_voice_metadata_leak_and_normal_message_unchanged(self):
        db, _, _ = self.fixture()
        page = read_messages(db, dict(chat_id='voice-test', start=100, end=104, limit=100, after=None, keyword=''))
        self.assertEqual(page['messages'][0]['content'], '普通正文')
        self.assertNotIn('transcript_status', page['messages'][0])
        self.assertEqual(page['messages'][1]['transcript_status'], 'not_available')
        self.assertNotIn('DO_NOT_EXPOSE', str(page))

    def test_transcript_obeys_limits_and_pagination(self):
        db, conn, table = self.fixture()
        conn.execute(f'UPDATE {table} SET packed_info_data=? WHERE local_id=1', (packed('中'*5000),))
        page = read_messages(db, dict(chat_id='voice-test', start=100, end=104, limit=2, after=None, keyword=''))
        self.assertTrue(page['has_more'])
        q = validate('query_messages', dict(chat_id='voice-test', cursor=page['next_cursor'], limit=2))
        page2 = read_messages(db, q)
        self.assertEqual(len(page2['messages']), 1)
        self.assertFalse(page2['has_more'])
        self.assertEqual(len(page2['messages'][0]['content']), 4000)
        self.assertTrue(page2['messages'][0]['content_truncated'])


if __name__ == '__main__':
    unittest.main()
