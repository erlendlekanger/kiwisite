r"""Hires pass for a chosen astronaut candidate: FLUX img2img at 2x resolution with low strength adds real detail.
Two phases (prompt encoded first, text encoders freed, then the transformer) so it fits next to Ollama's models.

    C:\\Users\\erlen\\krea_local\\venv\\Scripts\\python.exe fomoindex/render/astronaut_hires.py astro_p_102.png [strength]
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

SRC_DIR = r"C:\Users\erlen\krea_local\output_fomoindex"
name = sys.argv[1]
strength = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3
prompt = os.environ.get("PH_PROMPT") or ("hyperrealistic photograph of an astronaut in a white spacesuit with a dark mirrored helmet visor floating weightless in deep space, holding out a black smartphone, "
          "crisp detailed suit fabric, seams and gloves, strong key light, pure black background, 8k, sharp")
repo = "black-forest-labs/FLUX.1-schnell"
t0 = time.time()

tbnb = TfBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
t5 = T5EncoderModel.from_pretrained(repo, subfolder="text_encoder_2", quantization_config=tbnb, torch_dtype=torch.bfloat16)
t5tok = T5TokenizerFast.from_pretrained(repo, subfolder="tokenizer_2")
clip = CLIPTextModel.from_pretrained(repo, subfolder="text_encoder", torch_dtype=torch.bfloat16).to("cuda")
cliptok = CLIPTokenizer.from_pretrained(repo, subfolder="tokenizer")
with torch.no_grad():
    ti = t5tok(prompt, padding="max_length", max_length=256, truncation=True, return_tensors="pt").input_ids.to("cuda")
    pe = t5(ti, output_hidden_states=False)[0].to(torch.bfloat16)
    ci = cliptok(prompt, padding="max_length", max_length=77, truncation=True, return_tensors="pt").input_ids.to("cuda")
    pooled = clip(ci, output_hidden_states=False).pooler_output.to(torch.bfloat16)
del t5, clip
gc.collect()
torch.cuda.empty_cache()
print(f"prompt encoded, encoders freed, {time.time() - t0:.0f}s", flush=True)

dbnb = DiffBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
transformer = FluxTransformer2DModel.from_pretrained(repo, subfolder="transformer", quantization_config=dbnb, torch_dtype=torch.bfloat16)
pipe = FluxImg2ImgPipeline.from_pretrained(repo, transformer=transformer, text_encoder=None, text_encoder_2=None, tokenizer=None, tokenizer_2=None, torch_dtype=torch.bfloat16)
pipe.vae.to("cuda")
pipe.vae.enable_tiling()
print(f"model ready in {time.time() - t0:.0f}s, vram {torch.cuda.memory_allocated() / 1e9:.1f} GB", flush=True)

src = Image.open(os.path.join(SRC_DIR, name)).convert("RGB")
big = src.resize((src.width * 2, src.height * 2), Image.LANCZOS)
t = time.time()
out = pipe(prompt_embeds=pe, pooled_prompt_embeds=pooled, image=big, strength=strength, guidance_scale=0.0, num_inference_steps=4,
           width=big.width, height=big.height, generator=torch.Generator("cpu").manual_seed(7)).images[0]
dst = os.path.join(SRC_DIR, name.replace(".png", "_hires.png"))
out.save(dst)
print(f"hires {out.size} in {time.time() - t:.0f}s -> {dst}", flush=True)
