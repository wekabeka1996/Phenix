import subprocess
from pathlib import Path

def get_git_files(allowed_exts):
    try:
        # Отримуємо всі файли, які бачить git (ігнорує ті, що в .gitignore)
        result = subprocess.run(
            ["git", "ls-files"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        files = result.stdout.splitlines()
        
        filtered_files = []
        for f in files:
            path = Path(f)
            if path.suffix.lower() not in allowed_exts:
                continue
            
            # Ігноруємо папку tests та приховані файли/папки (з крапкою на початку)
            if "tests" in path.parts or any(p.startswith(".") for p in path.parts):
                continue
                
            filtered_files.append(f)
            
        return filtered_files
    except Exception as e:
        print(f"Помилка виконання git ls-files: {e}")
        return []

def build_tree(paths):
    """Будує вкладений словник з плоского списку шляхів."""
    tree = {}
    for path in paths:
        parts = Path(path).parts
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree

def render_tree(tree, prefix=""):
    """Рендерить дерево у вигляді красивого тексту."""
    lines = []
    # Сортуємо: спочатку папки (в яких є вкладеності), потім файли
    entries = sorted(tree.keys(), key=lambda k: (len(tree[k]) == 0, k.lower()))
    
    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry}")
        
        extension_prefix = "    " if is_last else "│   "
        if tree[entry]:
            lines.extend(render_tree(tree[entry], prefix + extension_prefix))
            
    return lines

def generate_skeleton(output_file="project_skeleton.md"):
    allowed_exts = {".py", ".yaml", ".yml", ".json"}
    files = get_git_files(allowed_exts)
    
    if not files:
        print("Файлів із заданими розширеннями не знайдено.")
        return

    tree = build_tree(files)
    rendered_lines = render_tree(tree)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Структура проекту\n\n")
        f.write("```text\n")
        f.write(f"Phenix/\n")
        f.write("\n".join(rendered_lines))
        f.write("\n```\n")
        
    print(f"Скелет проекту успішно згенеровано у файл: {output_file}")

if __name__ == "__main__":
    generate_skeleton()
