
import os


def check_config():
    config_path = "system_config.yaml"
    if not os.path.exists(config_path):
        print(f"Config file not found at {config_path}")
        return

    print(f"Reading {config_path} as raw text...")
    try:
        with open(config_path, 'rb') as f:
            content_bytes = f.read()

        # Try decoding with utf-8, replace errors
        content = content_bytes.decode('utf-8', errors='replace')

        lines = content.splitlines()
        found_key = False
        found_secret = False

        for i, line in enumerate(lines):
            if "binance_ro_api_key" in line:
                print(
                    f"Found 'binance_ro_api_key' on line {i+1}: {line.strip()}")
                found_key = True
            if "binance_ro_api_secret" in line:
                print(
                    f"Found 'binance_ro_api_secret' on line {i+1}: {line.strip()}")
                found_secret = True

        if not found_key:
            print("❌ 'binance_ro_api_key' NOT found in file.")
        if not found_secret:
            print("❌ 'binance_ro_api_secret' NOT found in file.")

        if found_key and found_secret:
            print("✅ Both keys keys found in file (text check).")

    except Exception as e:
        print(f"Error reading file: {e}")


if __name__ == "__main__":
    check_config()
