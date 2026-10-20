r"""Redraws the PACKHUNT astronaut (astro_c_100.png, the approved pose with the arm reaching out) with FLUX.1-schnell
img2img so the helmet gets a closed black visor as part of the picture, instead of a visor patched in afterwards.
Two phases like astronaut_gen.py so it fits next to Ollama.

    C:\Users\erlen\krea_local\venv\Scripts\python.exe fomoindex/render/astronaut_redraw.py [n_seeds] [strength]

Writes C:\Users\erlen\krea_local\output_fomoindex\redraw_<seed>.png and sheet_redraw.jpg.
"""
import gc
import os
import sys
import time

import torch
from diffusers import BitsAndBytesConfig as DiffBnb
from diffusers import FluxImg2ImgPipeline, FluxTransformer2DModel
from PIL import Image
from transformers import BitsAndBytesConfig as TfBnb
from transformers import CLIPTextModel, CLIPTokenizer, T5EncoderModel, T5TokenizerFast

SRC = r"C:\Users\erlen\krea_local\output_packhunt\astro_c_100.png"
OUT = r"C:\Users\erlen\krea_local\output_fomoindex"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
STRENGTH = float(sys.argv[2]) if len(sys.argv) > 2 else 0.6
PROMPT = ("hyperrealistic photograph of an astronaut in a white NASA EMU spacesuit floating weightless in deep space, one gloved "
          "hand reaching out, the helmet visor is closed and completely jet black and mirrored, polished black glass with a soft "
          "studio reflection, no face visible, no text on the visor, full body, crisp detailed suit fabric and seams, strong key "
          "light from the upper left, pure black background, 8k")
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
pipe = FluxImg2ImgPipeline.from_pretrained(repo, transformer=transformer, text_encoder=None, text_encoder_2=None, tokenizer=None,
                                           tokenizer_2=None, torch_dtype=torch.bfloat16)
pipe.vae.to("cuda")
print(f"model ready in {time.time() - t0:.0f}s", flush=True)

src = Image.open(SRC).convert("RGB")
thumbs = []
for i in range(N):
    seed = 800 + i
    img = pipe(prompt_embeds=pe, pooled_prompt_embeds=pooled, image=src, strength=STRENGTH, guidance_scale=0.0, num_inference_steps=4,
               width=src.width, height=src.height, generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    f = os.path.join(OUT, f"redraw_{seed}.png")
    img.save(f)
    thumbs.append(img.resize((320, int(320 * img.height / img.width))))
    print(os.path.basename(f), flush=True)
sheet = Image.new("RGB", (320 * len(thumbs), thumbs[0].height))
for i, t in enumerate(thumbs):
    sheet.paste(t, (i * 320, 0))
sheet.save(os.path.join(OUT, "sheet_redraw.jpg"), quality=90)
print("sheet done", flush=True)
