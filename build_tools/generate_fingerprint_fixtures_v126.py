#!/usr/bin/env python3
"""Original PCM and server Chromaprint reference for actual Android JNI tests."""
import array
import ctypes
import ctypes.util
import math
import os
from pathlib import Path
import struct
import subprocess

root = Path(os.environ['PROJECT_ROOT'])
assets = root / 'ffmpeg-audio/src/androidTest/assets'
assets.mkdir(parents=True, exist_ok=True)
pcm = array.array('h')
for n in range(45 * 11025):
    t=n/11025
    freq=[196,262,330,392,440,294,220,349][int(t*4)%8]
    value=(math.sin(t*freq*math.tau)+.27*math.sin(t*freq*2.01*math.tau)+.18*math.sin(t*91*math.tau))
    pcm.append(round(value*11000*(.6+.4*math.cos(t*.9)**2)))
original=pcm.tobytes()
lib=ctypes.CDLL(ctypes.util.find_library('chromaprint'))
lib.chromaprint_new.argtypes=[ctypes.c_int];lib.chromaprint_new.restype=ctypes.c_void_p
for name in ['chromaprint_free','chromaprint_finish']:getattr(lib,name).argtypes=[ctypes.c_void_p]
lib.chromaprint_start.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
lib.chromaprint_feed.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_int16),ctypes.c_int]
lib.chromaprint_get_raw_fingerprint.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32)),ctypes.POINTER(ctypes.c_int)]
lib.chromaprint_dealloc.argtypes=[ctypes.c_void_p]
for name,rate,channels,fmt in [('mono',11025,1,'s16le'),('stereo',48000,2,'s16le'),('float',48000,2,'f32le')]:
    source=subprocess.check_output(['ffmpeg','-v','error','-f','s16le','-ar','11025','-ac','1','-i','pipe:0',
        '-ar',str(rate),'-ac',str(channels),'-f',fmt,'pipe:1'],input=original)
    reference=subprocess.check_output(['ffmpeg','-v','error','-f',fmt,'-ar',str(rate),'-ac',str(channels),'-i','pipe:0',
        '-ar','11025','-ac','1','-f','s16le','pipe:1'],input=source)
    context=lib.chromaprint_new(1)
    pointer=ctypes.POINTER(ctypes.c_uint32)();count=ctypes.c_int()
    try:
        assert lib.chromaprint_start(context,11025,1)
        samples=(ctypes.c_int16*(len(reference)//2)).from_buffer_copy(reference)
        assert lib.chromaprint_feed(context,samples,len(samples))
        assert lib.chromaprint_finish(context)
        assert lib.chromaprint_get_raw_fingerprint(context,ctypes.byref(pointer),ctypes.byref(count))
        expected=struct.pack('<' + str(count.value) + 'I',*[pointer[i] for i in range(count.value)])
        (assets/f'capture-{name}.pcm').write_bytes(source)
        (assets/f'capture-{name}.fp').write_bytes(expected)
    finally:
        if pointer:lib.chromaprint_dealloc(pointer)
        lib.chromaprint_free(context)
print('Original mono/stereo/float PCM and server algorithm-1 reference generated')
