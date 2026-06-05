#!/usr/bin/env python3
"""
Запуск pytest, поиск тестов со статусом FAILED или ERROR и перемещение файлов с этими тестами
в папку резервной копии. По умолчанию выполняется dry-run — только показ кандидатов.

Использование:
  python3 scripts/remove_failed_tests.py        # dry-run, показывает что удалится
  python3 scripts/remove_failed_tests.py --execute   # реально переместит файлы в .trash

Автор: GitHub Copilot (автоматически сгенерировано)
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime


def run_pytest_and_write_junit(junit_path):
    cmd = ["pytest", "-q", "--maxfail=0", f"--junitxml={junit_path}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print("Ошибка: pytest не найден в PATH.")
        sys.exit(2)
    output = proc.stdout + "\n" + proc.stderr
    return output, proc.returncode


def parse_junit_for_failed_tests(junit_path: str):
    import xml.etree.ElementTree as ET

    if not os.path.exists(junit_path):
        return []
    tree = ET.parse(junit_path)
    root = tree.getroot()
    tests = []
    # pytest junit has <testcase> elements; failure/error are child tags
    for tc in root.findall('.//testcase'):
        has_problem = any(child.tag in ('failure', 'error') for child in tc)
        if not has_problem:
            continue
        name = tc.attrib.get('name')
        fileattr = tc.attrib.get('file') or tc.attrib.get('classname')
        tests.append({'name': name, 'file': fileattr})
    return tests


def tests_to_files(tests):
    files = []
    for t in tests:
        f = t.get('file')
        name = t.get('name')
        if f and os.path.exists(f):
            files.append(os.path.normpath(f))
            continue
        # if file attribute looks like a module/class, try to map to path
        if f and '.' in f:
            candidate = os.path.join(*f.split('.')) + '.py'
            if os.path.exists(candidate):
                files.append(os.path.normpath(candidate))
                continue
        # fallback: search for function definition in repo (tests folders)
        if name:
            grep_cmd = ['grep', '-R', '-n', f'def {name}(', '--include=test_*.py', '.']
            try:
                proc = subprocess.run(grep_cmd, capture_output=True, text=True)
                if proc.returncode == 0 and proc.stdout:
                    first = proc.stdout.splitlines()[0]
                    path = first.split(':', 1)[0]
                    if os.path.exists(path):
                        files.append(os.path.normpath(path))
                        continue
            except Exception:
                pass
        # if all fails, keep the raw file token (may be relative path)
        if f:
            files.append(f)
    return sorted(set(files))


def make_backup_and_move(files, backup_root):
    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    dest = os.path.join(backup_root, 'failed_tests_backup_' + ts)
    os.makedirs(dest, exist_ok=True)
    moved = []
    for f in files:
        if not os.path.exists(f):
            print(f"Пропускаю (не найден): {f}")
            continue
        # keep relative path inside backup
        try:
            rel = os.path.relpath(f, start=os.getcwd())
        except Exception:
            rel = os.path.basename(f)
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(f, target)
        moved.append((f, target))
    return dest, moved


def main():
    parser = argparse.ArgumentParser(description='Remove files containing tests that FAILED or ERROR')
    parser.add_argument('--execute', action='store_true', help='Actually move files to .trash (default: dry-run)')
    parser.add_argument('--backup-dir', default='.trash', help='Where to store moved files (default: .trash)')
    args = parser.parse_args()

    print('Запускаю pytest и собираю список FAILED/ERROR тестів (junit xml) ...')
    junit_path = '.pytest_junit.xml'
    output, rc = run_pytest_and_write_junit(junit_path)
    tests = parse_junit_for_failed_tests(junit_path)
    files = tests_to_files(tests)

    if not files:
        print('Не найдено файлов с тестами, дающими FAILED или ERROR.')
        sys.exit(0)

    print('\nНайденные тесты:')
    for t in tests:
        print('  -', t)

    print('\nФайлы, предлагаемые к перемещению:')
    for f in files:
        print('  -', f)

    if not args.execute:
        print('\nDRY-RUN: ничего не будет перемещено. Запустите с --execute для выполнения.')
        sys.exit(0)

    backup_root = args.backup_dir
    dest, moved = make_backup_and_move(files, backup_root)
    print(f'Файлы перемещены в: {dest}')
    for src, dst in moved:
        print(f'  moved: {src} -> {dst}')


if __name__ == '__main__':
    main()
