# Third-party notices

`assets/mcp-runtime/vendor/db.py` is an unmodified copy of the database reader from [fanyuantaier/wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica), commit `62503d76a0db069171cb4e42e87090ad285db489`.

SHA256: `9d4eba69e868dea8000d8acdbaed723149cf8732c52e097f23fb3b07fa5ddc55`.

The upstream reader is licensed under Apache License 2.0; the license is preserved at `assets/mcp-runtime/vendor/LICENSE`. Its original source comments are retained. This project loads it through an isolated wrapper, disables key persistence and account fallback, and does not import upstream GUI/media/send modules. Wrapper, voice parser, offline-ASR integration, tests and skill instructions are additions in this project.

Runtime dependencies and models are downloaded separately. Their own licenses apply. This repository does not redistribute Python wheels or model weights. Offline recognition uses faster-whisper, CTranslate2, pysilk-mod and the [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small) model at revision `536b0662742c02347bc0e980a01041f333bce120`, converted from OpenAI Whisper. Consult the model and dependency repositories for their licensing terms.
