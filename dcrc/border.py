"""Convert an optional user-supplied image into two PSP side fields. MIT.
No image is bundled: these bytes belong only in the user's local PSP folder.
"""
import struct
import warnings
from .errors import ConverterError

def encode_border(path):
    try:
        from PIL import Image,ImageOps
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.width<1 or image.height<1 or image.width>4096 or image.height>4096:
                    raise ValueError('Image dimensions must be1..4096.')
                oriented=ImageOps.exif_transpose(image).convert('RGBA')
                flat=Image.new('RGB',oriented.size,(0,0,0))
                flat.paste(oriented,mask=oriented.getchannel('A'))
                image=flat.resize((480,272),Image.Resampling.BILINEAR)
        pixels=[]
        for y in range(512):
            for x in range(128):
                sx=min(x,59) if x<64 else 420+min(x-64,59)
                r,g,b=image.getpixel((sx,min(y,271)))
                pixels.append((r>>3)|((g>>2)<<5)|((b>>3)<<11))
        return struct.pack('<4I',0x31524244,128,512,131072)+struct.pack('<65536H',*pixels)
    except Exception as error:
        raise ConverterError('border_image','The optional border image could not be converted.',str(error)) from error
