import json, numpy as np, sounddevice as sd, vosk
from audio_utils import negotiate_input, block_to_vosk_bytes

DEVICE = 18

m = vosk.Model("models/vosk-model-small-pt-0.3")
r = vosk.KaldiRecognizer(m, 16000)

rate, ch, bs = negotiate_input(DEVICE, 250)
print("Mic aberto:", rate, "Hz,", ch, "canal(is), bloco", bs)
print("FALE QUALQUER COISA. Feche a janela para sair.")

with sd.InputStream(device=DEVICE, samplerate=rate, channels=ch, dtype="float32", blocksize=bs) as st:
    while True:
        data, _ = st.read(bs)
        b = block_to_vosk_bytes(data, rate)
        if r.AcceptWaveform(b):
            txt = json.loads(r.Result()).get("text", "")
            if txt:
                print("OUVI:", txt)