r"""Repaints the helmet opening of the PACKHUNT astronaut (astro_c_100_hires.png) as a real black mirrored visor with
FLUX.1-schnell inpainting (4-bit, two phases like astronaut_gen.py), so the glass gets the photo's own light instead
of a drawn one. The mask is the inner edge of the helmet ring, traced on a gridded zoom.

    C:\Users\erlen\krea_local\venv\Scripts\python.exe fomoindex/render/visor_inpaint.py [n_seeds]

Writes C:\Users\erlen\krea_local\output_fomoindex\visor_<seed>.png (full image) and a contact sheet of the helmets.
"""
import gc
import os
import sys
import time

import numpy as np
import torch
from diffusers import BitsAndBytesConfig as DiffBnb
from diffusers import FluxInpaintPipeline, FluxTransformer2DModel
from PIL import Image, ImageDraw, ImageFilter
from transformers import BitsAndBytesConfig as TfBnb
from transformers import CLIPTextModel, CLIPTokenizer, T5EncoderModel, T5TokenizerFast

SRC = r"C:\Users\erlen\krea_local\output_packhunt\astro_c_100_hires.png"
OUT = r"C:\Users\erlen\krea_local\output_fomoindex"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
PROMPT = ("close-up photograph of a complete round white NASA spacesuit helmet seen three quarters from the front, the white "
          "helmet shell and the silver visor ring go all the way around a closed jet black mirrored visor, polished black glass "
          "with a soft studio light reflection, the face completely hidden, the helmet sits on the white suit's neck ring, black space background, photoreal, 8k, sharp")
RING = [(1135, 790), (1158, 752), (1186, 724), (1218, 700), (1256, 684), (1300, 674), (1340, 672), (1378, 680), (1410, 694),
        (1428, 716), (1430, 770), (1430, 820), (1424, 870), (1412, 912), (1396, 945), (1374, 970), (1350, 989), (1326, 1003),
        (1288, 1008), (1250, 1007), (1214, 1003), (1182, 992), (1156, 970), (1137, 945), (1124, 910), (1119, 872), (1122, 834)]
CX, CY, BOX = 1290, 900, 704          # the crop handed to FLUX, centred on the opening
repo = "black-forest-labs/FLUX.1-schnell"
t0 = time.time()

tbnb = TfBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
t5 = T5EncoderModel.from_pretrained(repo, subfolder="text_encoder_2", quantization_config=tbnb, torch_dtype=torch.bfloat16)
t5tok = T5TokenizerFast.from_pretrained(repo, subfolder="tokenizer_2")
clip = CLIPTextModel.from_pretrained(repo, subfolder="text_encoder", torch_dtype=torch.bfloat16).to("cuda")
cliptok = CLIPTokenizer.from_pretrained(repo, subfolder="tokenizer")
with torch.no_grad():
    ti = t5tok(PROMPT, padding="max_length", max_length=256, truncation=True, return_tensors="pt").input_ids.to("cuda")
    pe = t5(ti, output_hidden_states=False)[0].to(torch.bfloat16)
    ci = cliptok(PROMPT, padding="max_length", max_length=77, truncation=True, return_tensors="pt").input_ids.to("cuda")
    pooled = clip(ci, output_hidden_states=False).pooler_output.to(torch.bfloat16)
del t5, clip
gc.collect()
torch.cuda.empty_cache()

dbnb = DiffBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
transformer = FluxTransformer2DModel.from_pretrained(repo, subfolder="transformer", quantization_config=dbnb, torch_dtype=torch.bfloat16)
pipe = FluxInpaintPipeline.from_pretrained(repo, transformer=transformer, text_encoder=None, text_encoder_2=None, tokenizer=None,
                                           tokenizer_2=None, torch_dtype=torch.bfloat16)
pipe.vae.to("cuda")
print(f"model ready in {time.time() - t0:.0f}s", flush=True)

src = Image.open(SRC).convert("RGB")
x0, y0 = CX - BOX // 2, CY - BOX // 2
crop = src.crop((x0, y0, x0 + BOX, y0 + BOX))
mask = Image.new("L", src.size, 0)
dr = ImageDraw.Draw(mask)
dr.polygon(RING, fill=255)
# The photo has no helmet shell right of the opening, only black, so a visor painted there hangs out in space. The mask
# therefore also covers the right part of where the round shell must be, and FLUX draws shell and ring around the glass.
HX, HY, HR = 1268, 842, 262
shell = Image.new("L", src.size, 0)
ImageDraw.Draw(shell).ellipse((HX - HR, HY - HR, HX + HR, HY + HR), fill=255)
ImageDraw.Draw(shell).rectangle((1290, HY, HX + HR, 1150), fill=255)
right = Image.new("L", src.size, 0)
ImageDraw.Draw(right).rectangle((1372, 600, HX + HR + 20, 1110), fill=255)
# and the empty gap under the helmet down to the suit, so the shell ends on a neck ring instead of a cut line
ImageDraw.Draw(right).polygon([(1290, 1000), (1470, 1000), (1500, 1060), (1470, 1150), (1330, 1150), (1290, 1080)], fill=255)
mask = Image.fromarray(np.maximum(np.asarray(mask), np.minimum(np.asarray(shell), np.asarray(right))))
mask = mask.filter(ImageFilter.GaussianBlur(5)).point(lambda v: 255 if v > 60 else 0)   # round, not stair-stepped
mcrop = mask.crop((x0, y0, x0 + BOX, y0 + BOX))
big, bigm = crop.resize((1024, 1024), Image.LANCZOS), mcrop.resize((1024, 1024), Image.LANCZOS)

thumbs = []
for i in range(N):
    seed = 700 + i
    out = pipe(prompt_embeds=pe, pooled_prompt_embeds=pooled, image=big, mask_image=bigm, strength=1.0, guidance_scale=0.0,
               num_inference_steps=4, width=1024, height=1024, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    patch = out.resize((BOX, BOX), Image.LANCZOS)
    soft = mcrop.filter(ImageFilter.GaussianBlur(4))
    full = src.copy()
    full.paste(Image.composite(patch, crop, soft), (x0, y0))
    f = os.path.join(OUT, f"visor_{seed}.png")
    full.save(f)
    thumbs.append(full.crop((x0, y0, x0 + BOX, y0 + BOX)).resize((320, 320)))
    print(os.path.basename(f), flush=True)

sheet = Image.new("RGB", (320 * len(thumbs), 320))
for i, t in enumerate(thumbs):
    sheet.paste(t, (i * 320, 0))
sheet.save(os.path.join(OUT, "sheet_visor.jpg"), quality=90)
print("sheet done", flush=True)
