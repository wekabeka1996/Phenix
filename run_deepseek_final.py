from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import torch

model_path = "./DeepSeek-R1-Distill-Qwen-14B"

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

print("Preparing quantization config...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    llm_int8_enable_fp32_cpu_offload=True,
)

print("Loading model (with CPU/GPU split)...")
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    quantization_config=bnb_config,
    trust_remote_code=True,
    device_map={
        "model.embed_tokens": 0,
        "model.layers": 0,       # основні layer-и на GPU
        "lm_head": "cpu",        # великі матриці offload на CPU
        "model.norm": "cpu",     # нормалізації теж на CPU
    },
    offload_folder="./offload",  # куди скидати CPU tensors
)

prompt = "<think>\n2+2=?\n</think>\n\n"
inputs = tokenizer(prompt, return_tensors="pt").to(0)

print("Generating...")
output = model.generate(
    **inputs,
    max_new_tokens=200,
    temperature=0.6,
)

print(tokenizer.decode(output[0], skip_special_tokens=False))
