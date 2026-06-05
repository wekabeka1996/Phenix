import subprocess
import os
from pathlib import Path

def generate_dump(output_file="project_content_dump.md"):
    # Дозволені розширення файлів
    allowed_exts = {".py", ".yaml", ".yml", ".json"}
    
    try:
        # Використовуємо git для отримання списку файлів. 
        # Це автоматично ігнорує всі файли та папки, що вказані в .gitignore
        result = subprocess.run(
            ["git", "ls-files"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        files = result.stdout.splitlines()
    except subprocess.CalledProcessError:
        print("Помилка: Цей скрипт потрібно запускати в середовищі git-репозиторію.")
        return
    except FileNotFoundError:
        print("Помилка: Git не встановлено або не додано до PATH.")
        return

    # Фільтруємо лише потрібні формати
    filtered_files = [f for f in files if Path(f).suffix.lower() in allowed_exts]

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("# Повний вміст проекту\n\n")
        
        for file_path in sorted(filtered_files):
            path_obj = Path(file_path)
            
            # Перевіряємо чи файл дійсно існує
            if not path_obj.is_file():
                continue
                
            out.write(f"## Файл: `{file_path}`\n\n")
            
            # Визначаємо мову для підсвітки синтаксису в Markdown
            ext = path_obj.suffix.lower()[1:]
            if ext == "yml":
                ext = "yaml"
                
            out.write(f"```{ext}\n")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    out.write(content)
            except Exception as e:
                out.write(f"# Не вдалося прочитати файл: {e}\n")
            
            out.write("\n```\n\n")
            
    print(f"Дамп проекту успішно згенеровано у файл: {output_file}")

if __name__ == "__main__":
    generate_dump()
