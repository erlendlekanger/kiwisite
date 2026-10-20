r"""Astronaut-kandidater til FOMOINDEX-forsiden med lokal FLUX.1-schnell (4-bit, RTX 4090), samme oppskrift som
PACKHUNT (packhunt/tools/astronaut_gen.py): promptene kodes foerst og tekstkoderne frigjoeres, saa lastes transformeren.
Astronauten holder en telefon med skjermen mot oss; skjermen fylles med den ekte logoen etterpaa (astronaut_compose.py).

    C:\Users\erlen\krea_local\venv\Scripts\python.exe fomoindex/render/astronaut_gen.py [n_per_prompt]

Skriver C:\Users\erlen\krea_local\output_fomoindex\astro_<prompt>_<seed>.png og et kontaktark.
"""
import gc
import os
import sys
import time

import torch
from diffusers import BitsAndBytesConfig as DiffBnb
from diffusers import FluxPipeline, FluxTransformer2DModel
from PIL import Image
from transformers import BitsAndBytesConfig as TfBnb
from transformers import CLIPTextModel, CLIPTokenizer, T5EncoderModel, T5TokenizerFast

OUT = r"C:\Users\erlen\krea_local\output_fomoindex"
os.makedirs(OUT, exist_ok=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
W, H = int(os.environ.get("PH_W", 1024)), int(os.environ.get("PH_H", 1280))
PREFIX = os.environ.get("PH_PREFIX", "astro")
PROMPTS = {
    "p": "hyperrealistic photograph of an astronaut in a white NASA EMU spacesuit with a dark black mirrored helmet visor, floating weightless in deep space, "
         "body turned three quarters toward the camera, one arm stretched out toward the viewer holding a modern black smartphone in the gloved hand, "
         "the phone screen faces the camera and is completely black, legs trailing behind, full body in frame, crisp detailed suit fabric and seams, "
         "strong key light from the upper left, soft blue earth light from below, pure black background, 8k",
    "q": "hyperrealistic photo of an astronaut in a white spacesuit with a black mirrored visor floating diagonally in space, reaching forward with one arm, "
         "gripping a large modern iphone with the blank black screen turned toward the viewer, whole body visible with margin, "
         "studio quality lighting, pure black background, 8k, photoreal",
}
repo = "black-forest-labs/FLUX.1-schnell"
t0 = time.time()

# ---- phase 1: text embeddings
tbnb = TfBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
t5 = T5EncoderModel.from_pretrained(repo, subfolder="text_encoder_2", quantization_config=tbnb, torch_dtype=torch.bfloat16)
t5tok = T5TokenizerFast.from_pretrained(repo, subfolder="tokenizer_2")
clip = CLIPTextModel.from_pretrained(repo, subfolder="text_encoder", torch_dtype=torch.bfloat16).to("cuda")
cliptok = CLIPTokenizer.from_pretrained(repo, subfolder="tokenizer")
embeds = {}
with torch.no_grad():
    for key, prompt in PROMPTS.items():
        ti = t5tok(prompt, padding="max_length", max_length=256, truncation=True, return_tensors="pt").input_ids.to("cuda")
        pe = t5(ti, output_hidden_states=False)[0].to(torch.bfloat16)
        ci = cliptok(prompt, padding="max_length", max_length=77, truncation=True, return_tensors="pt").input_ids.to("cuda")
        pooled = clip(ci, output_hidden_states=False).pooler_output.to(torch.bfloat16)
        embeds[key] = (pe, pooled)
del t5, clip
gc.collect()
torch.cuda.empty_cache()
print(f"prompts encoded, text encoders freed, {time.time() - t0:.0f}s", flush=True)

# ---- phase 2: the transformer
dbnb = DiffBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
transformer = FluxTransformer2DModel.from_pretrained(repo, subfolder="transformer", quantization_config=dbnb, torch_dtype=torch.bfloat16)
pipe = FluxPipeline.from_pretrained(repo, transformer=transformer, text_encoder=None, text_encoder_2=None, tokenizer=None, tokenizer_2=None, torch_dtype=torch.bfloat16)
pipe.vae.to("cuda")
print(f"model ready in {time.time() - t0:.0f}s, vram {torch.cuda.memory_allocated() / 1e9:.1f} GB", flush=True)

files = []
for key, (pe, pooled) in embeds.items():
    for i in range(N):
        seed = 100 + i
        t = time.time()
        img = pipe(prompt_embeds=pe, pooled_prompt_embeds=pooled, guidance_scale=0.0, num_inference_steps=4, width=W, height=H,
                   generator=torch.Generator("cpu").manual_seed(seed)).images[0]
        f = os.path.join(OUT, f"{PREFIX}_{key}_{seed}.png")
        img.save(f)
        files.append(f)
        print(f"{os.path.basename(f)} {time.time() - t:.1f}s", flush=True)

tw, th_ = 320, int(320 * H / W)
thumbs = [Image.open(f).resize((tw, th_)) for f in files]
cols = N
rows = (len(thumbs) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw, rows * th_), (0, 0, 0))
for i, th in enumerate(thumbs):
    sheet.paste(th, ((i % cols) * tw, (i // cols) * th_))
sheet.save(os.path.join(OUT, f"sheet_{PREFIX}.jpg"), quality=88)
print("sheet", os.path.join(OUT, f"sheet_{PREFIX}.jpg"), flush=True)
