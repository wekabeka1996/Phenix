from huggingface_hub import snapshot_download

path = snapshot_download(
    repo_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
    local_dir="./DeepSeek-R1-Distill-Qwen-14B",
    local_dir_use_symlinks=False,
)

print("Downloaded to:", path)
