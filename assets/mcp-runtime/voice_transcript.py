"""Read existing WeChat 4.x local voice transcription; no audio or network IO."""
MAX_PACKED_BYTES = 65536


def _fields(blob):
    """Small, bounded protobuf wire reader. Unknown fields are skipped, not decoded."""
    if not isinstance(blob, bytes) or len(blob) > MAX_PACKED_BYTES:
        raise ValueError('invalid packed voice metadata')
    pos = 0

    def varint():
        nonlocal pos
        value = 0
        for shift in range(0, 70, 7):
            if pos >= len(blob):
                raise ValueError('truncated varint')
            byte = blob[pos]
            pos += 1
            if shift == 63 and byte > 1:
                raise ValueError('varint overflow')
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError('varint overflow')

    result = []
    while pos < len(blob):
        if len(result) >= 128:
            raise ValueError('too many metadata fields')
        tag = varint()
        number, wire = tag >> 3, tag & 7
        if not 1 <= number < 2**29:
            raise ValueError('invalid field number')
        if wire == 0:
            value = varint()
        elif wire in (1, 2, 5):
            size = varint() if wire == 2 else (8 if wire == 1 else 4)
            if size > len(blob) - pos:
                raise ValueError('truncated field')
            value = blob[pos:pos + size]
            pos += size
        else:
            raise ValueError('unsupported wire type')
        result.append((number, wire, value))
    return result


def local_voice_transcript(packed):
    """Observed schema: packed_info_data field 5 -> state(1), UTF-8 text(2).

    Only state=2 (completed) is emitted. Empty or absent local text does not
    establish whether a user has converted this voice on another device.
    Never guess text from other metadata or execute anything in message data.
    """
    if packed in (None, b'', ''):
        return '', 'not_available'
    try:
        outer = _fields(packed)
        containers = [v for n, w, v in outer if n == 5 and w == 2]
        if not containers:
            return '', 'not_available'
        if len(containers) != 1:
            raise ValueError('ambiguous transcript metadata')
        inner = _fields(containers[0])
        states = [v for n, w, v in inner if n == 1 and w == 0]
        texts = [v for n, w, v in inner if n == 2 and w == 2]
        if len(states) != 1 or len(texts) != 1:
            raise ValueError('unsupported transcript metadata')
        if states[0] != 2:
            return '', 'not_available'
        text = texts[0].decode('utf-8').strip()
        if any(ord(c) < 32 and c not in '\n\r\t' for c in text):
            raise ValueError('invalid transcript text')
        return (text, 'available') if text else ('', 'not_available')
    except (ValueError, UnicodeError, TypeError):
        return '', 'unreadable'
