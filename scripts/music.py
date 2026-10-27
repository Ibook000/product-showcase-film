"""Small, deterministic original beat bed. No project imports or network calls."""
import math
import wave
from pathlib import Path
import numpy as np


def synthesize(path, duration, bpm=120, sample_rate=48000, seed=7, offset=0, events=()):
    if duration <= 0 or bpm <= 0 or sample_rate < 8000:
        raise ValueError('duration, BPM and sample rate must be positive')
    sr=int(sample_rate); n=round(duration*sr); beat=60/bpm
    mix=np.zeros((n,2),np.float32); rng=np.random.default_rng(seed)
    def add(at, signal, gain=1, pan=0):
        first=round(at*sr)
        if first<0:signal=signal[-first:];first=0
        length=min(len(signal),n-first)
        if length<=0:return
        x=signal[:length]*gain
        mix[first:first+length,0]+=x*math.sqrt((1-pan)/2)
        mix[first:first+length,1]+=x*math.sqrt((1+pan)/2)
    def note(midi,duration,decay):
        t=np.arange(round(duration*sr))/sr;freq=440*2**((midi-69)/12)
        return (np.sin(2*np.pi*freq*t)+.15*np.sin(4*np.pi*freq*t))*np.exp(-decay*t)*np.minimum(1,t/.004)
    t=np.arange(round(.36*sr))/sr
    kick=np.sin(2*np.pi*(46*t+75*.02*(1-np.exp(-t/.02))))*np.exp(-t*14)
    t=np.arange(round(.16*sr))/sr
    noise=rng.standard_normal(len(t));snare=(.35*noise+.2*np.sin(2*np.pi*185*t))*np.exp(-t*27)
    t=np.arange(round(.055*sr))/sr
    hat=rng.standard_normal(len(t));hat=(hat-np.convolve(hat,np.ones(9)/9,'same'))*np.exp(-t*110)
    chords=[[50,57,62,65],[46,53,58,62],[53,60,65,69],[48,55,60,64]]
    count=math.ceil(max(0,duration-offset)/beat)
    for k in range(count):
        at=offset+k*beat;chord=chords[(k//8)%4]
        add(at,kick,.75)
        if k%4 in [1,3]:add(at,snare,.43)
        add(at,hat,.06,-.25);add(at+beat/2,hat,.11,.25)
        add(at,note(chord[0]-12,min(.32,beat*.65),9),.20)
        for j in range(2):
            sound=note(chord[(k+j)%4]+12,min(.3,beat*.65),13)
            add(at+beat*(.25+j*.5),sound,.055,(-.35 if j else .35))
    for at in events:
        t=np.arange(round(.045*sr))/sr
        add(float(at),rng.standard_normal(len(t))*np.exp(-t*100),.07)
    mix=np.tanh(mix)
    fade=np.minimum(1,(duration-np.arange(n)/sr)/min(.18,duration))
    mix*=fade[:,None];mix*=.85/max(float(np.abs(mix).max()),1e-6)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(sr)
        f.writeframes((mix*32767).astype('<i2').tobytes())
    return path
