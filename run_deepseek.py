from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

model_path = "./DeepSeek-R1-Distill-Qwen-14B"

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

print("Loading model...")
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    device_map="auto",
    torch_dtype=torch.bfloat16,
    load_in_4bit=True,     # 4-bit quantization for RTX 4070
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
