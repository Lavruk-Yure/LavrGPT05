# flake8_check.py
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        print("Використання: python flake8_check.py <файл.py> [--output report.txt]")
        sys.exit(1)

    filename = sys.argv[1]
    extra_args = sys.argv[2:]

    # Аргументи для flake8
    cmd = [
        "flake8",
        filename,
        "--show-source",
        "--statistics",
        "--count",
        "--max-line-length=88",
    ]

    output_file = None
    if "--output" in extra_args:
        idx = extra_args.index("--output")
        if idx + 1 < len(extra_args):
            output_file = extra_args[idx + 1]
            # Видаляємо параметри --output report.txt з виклику flake8
            extra_args = extra_args[:idx] + extra_args[idx + 2 :]

    cmd += extra_args
    print("▶ Виконую:", " ".join(cmd))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        # Виводимо на консоль
        print(result.stdout)
        print(result.stderr)

        # Якщо задано файл — зберігаємо туди
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result.stdout)
                f.write(result.stderr)
            print(f"📄 Лог збережено у файл: {output_file}")

    except FileNotFoundError:
        print("❌ flake8 не знайдено. Встанови його через: pip install flake8")


if __name__ == "__main__":
    main()
