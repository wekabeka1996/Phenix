from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch

model_path = "./DeepSeek-R1-Distill-Qwen-14B"

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

print("Preparing quantization config...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)

print("Loading model...")
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    quantization_config=bnb_config,
    device_map="auto",                     # автоматичний мапінг
    llm_int8_enable_fp32_cpu_offload=True, # оффлоад якщо потрібно
    trust_remote_code=True,
)

prompt = "<think>\n2+2=?\n</think>\n\n"

inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

print("Generating...")
output = model.generate(
    **inputs,
    max_new_tokens=200,
    temperature=0.6,
)

print(tokenizer.decode(output[0], skip_special_tokens=False))
