"""Offline, in-memory SILK -> PCM -> Whisper for requested voice rows only."""
import os
import pathlib
import sys
import time

MAX_AUDIO_BYTES = 2_000_000
MAX_AUDIO_SECONDS = 65
MAX_VOICES_PER_PAGE = 3


def read_local_voice(db, chat_id, server_id):
    """Resolve by both chat and server ID, never by shard-local message ID alone."""
    if not server_id:
        return None, 'audio_not_local'
    for rel, path, _ in db._db_files:
        if not pathlib.Path(path).name.startswith('media_'):
            continue
        conn = db._open(rel)
        try:
            row = conn.execute(
                'SELECT length(v.voice_data) AS bytes, '
                'CASE WHEN length(v.voice_data)<=? THEN v.voice_data ELSE NULL END AS audio '
                'FROM VoiceInfo v JOIN Name2Id n ON v.chat_name_id=n.rowid '
                'WHERE n.user_name=? AND v.svr_id=? ORDER BY v.create_time DESC LIMIT 1',
                (MAX_AUDIO_BYTES, chat_id, server_id)).fetchone()
            if row and row['bytes']:
                if row['bytes'] > MAX_AUDIO_BYTES:
                    return None, 'audio_too_large'
                return bytes(row['audio']), 'available'
        finally:
            conn.close()
    return None, 'audio_not_local'


class AutoVoiceTranscriber:
    def __init__(self, db, chat_id, root):
        self.db = db
        self.chat_id = chat_id
        self.root = pathlib.Path(root).resolve()
        self.attempts = 0
        self.model = None
        self.started = time.monotonic()

    @property
    def exhausted(self):
        # Let the page cursor resume BEFORE the next voice; do not skip it.
        return self.attempts >= MAX_VOICES_PER_PAGE or (self.attempts > 0 and time.monotonic()-self.started > 70)

    def __call__(self, row):
        self.attempts += 1
        meta = {'transcript_source': 'local_whisper', 'transcript_model': 'whisper-small-int8',
                'transcript_review_required': True}
        try:
            audio, status = read_local_voice(self.db, self.chat_id, row['server_id'])
            if audio is None:
                return '', dict(meta, transcript_status=status)
            if not (self.root/'asr_model'/'model.bin').is_file():
                return '', dict(meta, transcript_status='asr_unavailable')
            # Set before importing inference dependencies. Model loading is local-only.
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            os.environ['TOKENIZERS_PARALLELISM'] = 'false'
            library = str(self.root/'asr_lib')
            if library not in sys.path:
                sys.path.insert(0, library)
            import numpy as np
            import pysilk
            import onnxruntime as ort
            ort.disable_telemetry_events()
            from faster_whisper import WhisperModel
            pcm = pysilk.decode(audio, sample_rate=16000)
            samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
            if len(samples) > 16000*MAX_AUDIO_SECONDS:
                return '', dict(meta, transcript_status='audio_too_long')
            if not len(samples):
                return '', dict(meta, transcript_status='no_speech_detected')
            if self.model is None:
                self.model = WhisperModel(str(self.root/'asr_model'), device='cpu',
                    compute_type='int8', cpu_threads=8, num_workers=1, local_files_only=True)
            segments, info = self.model.transcribe(samples, beam_size=5, temperature=0,
                condition_on_previous_text=False, vad_filter=True,
                vad_parameters={'min_silence_duration_ms':300}, language=None)
            kept = []
            for segment in segments:
                if segment.no_speech_prob >= .6 and segment.avg_logprob < -1:
                    continue
                kept.append(segment.text.strip())
                if len(kept) >= 50:
                    break
            text = ' '.join(kept).strip()
            return text, dict(meta, transcript_status='available' if text else 'no_speech_detected',
                              transcript_language=info.language)
        except Exception:
            # No raw audio, exception messages, identifiers or transcripts in logs.
            return '', dict(meta, transcript_status='asr_failed')
