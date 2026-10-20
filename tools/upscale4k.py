"""Upscale an AI photoshoot image (Flow 1K, 768x1376) to 4K 2160x3840 with EDSR x4, in tiles.
Usage: python3 tools/upscale4k.py in.jpg out.jpg  (needs opencv-contrib-python-headless; ~11 min on CPU)
"""
import cv2, numpy as np, sys, os, urllib.request
MODEL=os.path.expanduser('~/.cache/EDSR_x4.pb')
if not os.path.exists(MODEL) or os.path.getsize(MODEL)<1000000:
    os.makedirs(os.path.dirname(MODEL),exist_ok=True)
    urllib.request.urlretrieve('https://raw.githubusercontent.com/Saafke/EDSR_Tensorflow/master/models/EDSR_x4.pb',MODEL)
src, dst = sys.argv[1], sys.argv[2]
sr=cv2.dnn_superres.DnnSuperResImpl_create(); sr.readModel(MODEL); sr.setModel('edsr',4)
im=cv2.imread(src); H,W=im.shape[:2]; T=160; P=12
out=np.zeros((H*4,W*4,3),np.uint8)
for y in range(0,H,T):
    for x in range(0,W,T):
        y0,x0=max(0,y-P),max(0,x-P); y1,x1=min(H,y+T+P),min(W,x+T+P)
        u=sr.upsample(im[y0:y1,x0:x1])
        oy,ox=(y-y0)*4,(x-x0)*4; th,tw=min(T,H-y)*4,min(T,W-x)*4
        out[y*4:y*4+th,x*4:x*4+tw]=u[oy:oy+th,ox:ox+tw]
h,w=out.shape[:2]
out=cv2.resize(out,(2160,int(h*2160/w)),interpolation=cv2.INTER_AREA)
h=out.shape[0]; y=max(0,(h-3840)//2); out=out[y:y+3840]
cv2.imwrite(dst,out,[cv2.IMWRITE_JPEG_QUALITY,95]); print(out.shape)
